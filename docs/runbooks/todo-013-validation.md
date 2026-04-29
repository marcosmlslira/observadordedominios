# Roteiro de Validação — TODO-013 (Dual-fase R2↔PG + reprocessamento por TLD)

> Execução após deploy em produção. Siga a ordem dos blocos — cada bloco
> depende do anterior estar verde antes de avançar.

**Serviços envolvidos**
- Backend API: `http://localhost:8005` (dev) / `https://api.<domínio>` (prod)
- Frontend: `http://localhost:3005` (dev)
- Worker de ingestão: `ingestion_worker:8080` (interno à rede Docker)
- PostgreSQL: `obs:obs@postgres:5432/obs`

**Credenciais necessárias**
- Token JWT de admin (obtido via `/v1/auth/login`)
- Acesso ao container do worker: `docker ps | grep ingestion_worker`

---

## Bloco 0 — Pré-condições (infra)

| # | Verificação | Comando | Esperado |
|---|---|---|---|
| 0.1 | Migrations aplicadas | `docker exec <backend_container> alembic current` | head em `039_tld_daily_status_view` |
| 0.2 | View existe no banco | `docker exec <postgres_container> psql -U obs -d obs -c "\dv tld_daily_status_v"` | 1 linha com `tld_daily_status_v` |
| 0.3 | Coluna `phase` existe | `docker exec <postgres_container> psql -U obs -d obs -c "\d ingestion_run"` | coluna `phase text not null default 'full'` |
| 0.4 | Worker respondendo | `curl -s http://localhost:<worker_port>/health` ou via `docker exec <worker_container> curl -s localhost:8080/health` | `{"status":"ok"}` |
| 0.5 | Backend respondendo | `curl -s http://localhost:8005/health` | `{"status":"ok"}` |

---

## Bloco 1 — Fix P03: `TldStatusCategory` aceita `"partial"`

> Antes dessa fix, `GET /v1/ingestion/tld-status?source=openintel` retornava 500
> para TLDs com `status="partial"`.

| # | Verificação | Comando | Esperado |
|---|---|---|---|
| 1.1 | Endpoint responde 200 | `curl -s -H "Authorization: Bearer <TOKEN>" "http://localhost:8005/v1/ingestion/tld-status?source=openintel" \| jq '.status'` | `"ok"` — sem 500 |
| 1.2 | Endpoint responde para czds | `curl -s -H "Authorization: Bearer <TOKEN>" "http://localhost:8005/v1/ingestion/tld-status?source=czds" \| jq '.status'` | `"ok"` |
| 1.3 | Nenhum TLD causa 422 | Conferir que `items[]` não vazio e sem erro de validação Pydantic nos logs | logs sem `ValidationError` |

---

## Bloco 2 — Coluna `phase` gravada corretamente

> Valida que o pipeline grava `phase` nas novas runs, não apenas `'full'` para tudo.

| # | Verificação | Consulta SQL | Esperado |
|---|---|---|---|
| 2.1 | Runs anteriores mantêm `phase='full'` | `SELECT count(*) FROM ingestion_run WHERE phase IS NULL` | 0 (nenhuma nula) |
| 2.2 | Distribuição de phases | `SELECT phase, count(*) FROM ingestion_run GROUP BY phase ORDER BY 2 DESC` | `full` a maioria; `r2` e `pg` podem ser 0 se Databricks não rodou ainda |
| 2.3 | View retorna dados | `SELECT source, tld, day, r2_status, pg_status FROM tld_daily_status_v ORDER BY day DESC LIMIT 10` | Linhas com r2_status e pg_status preenchidos |

```sql
-- Consultas prontas para copiar no psql
SELECT phase, count(*) FROM ingestion_run GROUP BY phase ORDER BY 2 DESC;
SELECT source, tld, day, r2_status, pg_status, domains_inserted
  FROM tld_daily_status_v
  ORDER BY day DESC, domains_inserted DESC
  LIMIT 20;
```

---

## Bloco 3 — Endpoints novos da API

### 3.1 GET /heatmap

```bash
TOKEN="<seu_token>"
BASE="http://localhost:8005"

# Heatmap geral (últimos 14 dias)
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/v1/ingestion/heatmap?days=14" | jq '{
    source: .source,
    days_count: (.days | length),
    rows_count: (.rows | length),
    first_row: .rows[0]
  }'
```

**Esperado:**
- `rows_count` > 0 (deve ter TLDs registrados)
- `first_row.days` com objetos contendo `r2_status` e `pg_status`
- Status possíveis: `"ok"`, `"failed"`, `"pending"`, `"running"`, `"no_snapshot"`

```bash
# Filtrado por fonte
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/v1/ingestion/heatmap?source=czds&days=7" | jq '.rows | length'
```

### 3.2 GET /daily-summary

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/v1/ingestion/daily-summary" | jq '.items[:3]'
```

**Esperado:**
- Array de itens com `date`, `pg_ok`, `pg_failed`, `pg_complete_pct`, `domains_inserted`
- `pg_complete_pct` entre 0.0 e 1.0

```bash
# Verificar que pg_complete_pct faz sentido
curl -s -H "Authorization: Bearer $TOKEN" \
  "$BASE/v1/ingestion/daily-summary?days=7" | \
  jq '.items[] | {date, pct: (.pg_complete_pct * 100 | round), pg_ok, pg_failed}'
```

### 3.3 POST /tld/{source}/{tld}/reload

```bash
# Testar com TLD pequeno de baixo risco (ex: um TLD que tenha r2_status=ok hoje)
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/v1/ingestion/tld/czds/app/reload" | jq .
```

**Esperado:**
- `{"status": "accepted", "message": "...", "run_id": "<uuid>"}` — worker aceitou
- OU `{"status": "not_configured", ...}` — se `INGESTION_TRIGGER_URLS` não estiver configurado no backend

> Se retornar `502`, o backend não consegue alcançar o worker. Verificar:
> 1. Worker está rodando: `docker service ls | grep ingestion`
> 2. URL correta: `INGESTION_TRIGGER_URLS=http://ingestion_worker:8080/run-now,...`

### 3.4 POST /tld/{source}/{tld}/run

```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/v1/ingestion/tld/czds/app/run" | jq .
```

**Esperado:** mesmo formato de `reload` acima.

### 3.5 POST /tld/{source}/{tld}/dismiss

```bash
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/v1/ingestion/tld/czds/nonexistent999/dismiss?reason=test_validation" | jq .
```

**Esperado:** `{"status": "accepted", ...}` — dispatch para worker.

---

## Bloco 4 — Worker: recebe e executa ação por TLD

> Estes testes confirmam que o worker HTTP na porta 8080 aceita os novos paths.

```bash
# Acesso direto ao worker (via exec no container)
WORKER=$(docker ps --filter name=ingestion_worker --format "{{.ID}}" | head -1)

# Health check
docker exec $WORKER curl -s localhost:8080/health | jq .

# Simular reload de um TLD (sem token se INGESTION_MANUAL_TRIGGER_TOKEN não configurado)
docker exec $WORKER curl -s -X POST localhost:8080/tld/reload \
  -H "Content-Type: application/json" \
  -d '{"source":"czds","tld":"app"}' | jq .
```

**Esperado:**
- `{"status": "accepted", "message": "TLD app reload enqueued"}`
- Logs do worker devem mostrar `single_tld action=reload source=czds tld=app`

```bash
# Conferir logs do worker
docker service logs obs_ingestion_worker --tail 30 2>/dev/null || \
  docker logs $WORKER --tail 30
```

---

## Bloco 5 — Fix P01: retry em OperationalError

> Não há como forçar um `OperationalError` facilmente em produção, mas podemos
> confirmar que o código está ativo e monitorar o próximo ciclo.

| # | Verificação | Como checar |
|---|---|---|
| 5.1 | Constantes existem no código | `docker exec $WORKER grep -n "_SHARD_MAX_RETRIES" /app/ingestion/loader/delta_loader.py` |
| 5.2 | Logs de retry aparecem se ocorrer | No próximo ciclo, grep por: `docker service logs obs_ingestion_worker 2>&1 \| grep "loader shard retry"` |
| 5.3 | Nenhum TLD `net`/`org` com `reason_code='unexpected_error'` hoje | `SELECT tld, reason_code FROM ingestion_run WHERE tld IN ('net','org') AND started_at::date = CURRENT_DATE ORDER BY started_at DESC LIMIT 5` |

---

## Bloco 6 — Frontend: heatmap dual-fase

| # | Verificação | O que olhar |
|---|---|---|
| 6.1 | Página carrega sem erro | Abrir `http://localhost:3005/admin/ingestion` — sem tela branca ou erro de fetch |
| 6.2 | Cards de contagem presentes | "PG ok hoje", "PG falhou hoje", "R2 falhou hoje", "PG pendente", "Executando", "Domínios inseridos" |
| 6.3 | Heatmap exibe duas bolinhas por célula | Cada célula deve ter dois dots: o da esquerda (R2, verde claro) e o da direita (PG, verde escuro) |
| 6.4 | Cabeçalho de coluna com agregados | Datas recentes devem mostrar `%` de cobertura PG, duração (ex: `3m`), e contagem de domínios inseridos |
| 6.5 | Legenda visível | Canto superior direito do heatmap: "Ok (R2·PG)", "R2 ok, PG pendente", etc. |
| 6.6 | Clique em célula abre painel de ação | Clicar em célula não-vazia deve mostrar seção "Ações — .{tld} · {data}" |
| 6.7 | Botão "Reload PG" aparece só se R2 ok | Deve aparecer apenas quando `r2_status === "ok"` |
| 6.8 | Filtro "R2 ok, PG pendente" funciona | Selecionar filtro → deve mostrar apenas TLDs nesse estado |
| 6.9 | Ordenação "Atenção primeiro" funciona | Mudar sort → TLDs com mais falhas sobem |
| 6.10 | Auto-refresh a cada 60s | Aguardar 1 min e observar `Loader2` girando no título |

---

## Bloco 7 — Ciclo completo (smoke test end-to-end)

> Executar após confirmar que blocos 0–6 estão verdes.

```bash
# 1. Disparar ciclo manual via API
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/v1/ingestion/trigger/daily-cycle" | jq .

# 2. Acompanhar criação de runs
docker exec <postgres_container> psql -U obs -d obs -c "
  SELECT source, tld, phase, status, started_at
  FROM ingestion_run
  WHERE started_at > now() - interval '5 minutes'
  ORDER BY started_at DESC
  LIMIT 20
"

# 3. Checar view atualizada após conclusão
docker exec <postgres_container> psql -U obs -d obs -c "
  SELECT source, tld, r2_status, pg_status, domains_inserted
  FROM tld_daily_status_v
  WHERE day = CURRENT_DATE
  ORDER BY domains_inserted DESC
  LIMIT 10
"
```

**Esperado:**
- Runs com `phase='full'` para TLDs locais (CZDS pequenos, OpenINTEL zonefile)
- `r2_status='ok'` e `pg_status='ok'` para TLDs que concluíram
- `domains_inserted` > 0 para pelo menos um TLD

---

## Bloco 8 — Reprocessamento de TLD com falha (cenário real)

> Usar um TLD que tenha `pg_status='failed'` ou `pg_status='pending'` no heatmap.

```bash
# 1. Encontrar TLD candidato
docker exec <postgres_container> psql -U obs -d obs -c "
  SELECT source, tld, r2_status, pg_status
  FROM tld_daily_status_v
  WHERE day = CURRENT_DATE
    AND r2_status = 'success'
    AND pg_status != 'success'
  LIMIT 5
"

# 2. Disparar reload via API (substitua source e tld)
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/v1/ingestion/tld/czds/<tld>/reload" | jq .

# 3. Monitorar a run criada
docker exec <postgres_container> psql -U obs -d obs -c "
  SELECT id, tld, phase, status, started_at, finished_at, reason_code
  FROM ingestion_run
  WHERE tld = '<tld>'
    AND started_at > now() - interval '10 minutes'
  ORDER BY started_at DESC
"

# 4. Checar view após conclusão
docker exec <postgres_container> psql -U obs -d obs -c "
  SELECT r2_status, pg_status, domains_inserted, duration_seconds
  FROM tld_daily_status_v
  WHERE tld = '<tld>' AND day = CURRENT_DATE
"
```

**Esperado:**
- Nova `ingestion_run` com `phase='pg'` e `status='running'` imediatamente
- Após conclusão: `status='success'` e `pg_status='ok'` na view
- Frontend atualiza automaticamente no próximo refresh (60s)

---

## Resultados esperados por bloco

| Bloco | Verde se... |
|---|---|
| 0 | Migrations `038` e `039` em `alembic current`; view visível no psql |
| 1 | `/tld-status` retorna 200 para ambas as fontes |
| 2 | Nenhuma `phase IS NULL`; view retorna dados |
| 3 | Todos os 5 endpoints respondem com body JSON válido |
| 4 | Worker aceita `POST /tld/reload` e `POST /tld/run`; logs confirmam execução |
| 5 | Código compilado com `_SHARD_MAX_RETRIES=3`; sem `unexpected_error` em `net`/`org` |
| 6 | Heatmap com dois dots por célula; painel de ação abre ao clicar |
| 7 | Ciclo manual cria runs com `phase` correto; view reflete após conclusão |
| 8 | Reload de TLD falho cria `phase='pg'` run e corrige `pg_status` na view |

---

## O que fazer se algo falhar

### Heatmap vazio (`rows: []`)
```sql
-- Verificar se há dados na view
SELECT count(*) FROM tld_daily_status_v WHERE day >= CURRENT_DATE - 7;
-- Se 0, nenhum ciclo rodou ainda ou a migration não foi aplicada
```

### Reload retorna 502
- Verificar `INGESTION_TRIGGER_URLS` no backend: deve ser `http://ingestion_worker:8080/run-now,...`
- Confirmar que worker está na mesma rede Docker: `docker inspect <worker_container> | grep NetworkMode`
- Testar conectividade: `docker exec <backend_container> curl -s http://ingestion_worker:8080/health`

### `phase` ainda `NULL` em rows novas
- A migration 038 não foi aplicada — executar `alembic upgrade head` dentro do container do backend

### Frontend sem dots duplos nas células
- Limpar cache do browser (hard refresh `Ctrl+Shift+R`)
- Verificar console do browser por erro de fetch em `/v1/ingestion/heatmap`
