# TODO 012 — Incidente de Ingestão: 29/04/2026 — 16 TLDs com falha + API 500 + Ciclo de 26h

> Incidente observado via análise de logs em 29/04/2026 (15:30 BRT).  
> Fonte: `docker service logs observador-ingestion_ingestion_worker` + `observador_backend`

---

## Resumo Executivo

O ciclo de ingestão de hoje (29/04/2026) resultou em **16 TLDs com falha** e em um **endpoint da API retornando 500 repetidamente** para qualquer usuário que abre o painel de ingestão na aba OpenINTEL.

Quatro problemas identificados — três de falha funcional, um de performance estrutural:

| # | Problema | Severidade | Impacto |
|---|----------|------------|---------|
| P01 | Queda de conexão Postgres durante carga paralela de shards (`net`, `org`) | Alta | Dados não carregados para 2 TLDs grandes |
| P02 | R2 marker ausente após Databricks — 9 TLDs não carregados | Alta | Dados não carregados para au, ca, de, es, eu, fr, it, nl, uk |
| P03 | `TldStatusItem` rejeita status `"partial"` — API `/tld-status?source=openintel` retorna 500 | Crítica (UX) | Painel de ingestão inoperante para source=openintel |
| P04 | Ciclo leva 26h por acúmulo de timeouts e falhas sem circuit breaker | Alta | Ciclo diário "engole" o dia seguinte; próxima run pulada |

---

## P01 — Queda de Conexão Postgres durante `_parallel_load_shards`

### Horário
- `2026-04-29T02:32 UTC` → TLD `net`
- `2026-04-29T09:58 UTC` → TLD `org`

### Erro
```
psycopg2.OperationalError: server closed the connection unexpectedly
    This probably means the server terminated abnormally
    before or while processing the request.
```

### Stack trace
`pipeline.py:401` → `delta_loader.py:270` → `delta_loader.py:213` → `delta_loader.py:153 _load_shard_worker` → `cur.execute()`

### Causa provável
O Postgres encerrou a conexão durante uma operação de `COPY` ou `INSERT` em paralelo (múltiplas threads abrindo conexões simultaneamente via `_parallel_load_shards`). Possíveis causas:
- Postgres reiniciou (OOM, manutenção, watchdog)
- `max_connections` atingido com conexões não liberadas de runs anteriores
- Timeout de conexão ociosa (idle_in_transaction_session_timeout)
- Sem pool de conexões — cada shard abre conexão direta

### Ações necessárias
- [ ] Verificar logs do Postgres (`observador_postgres`) nos horários 02:30 e 09:55 UTC para confirmar causa
- [ ] Verificar se houve reinício do container Postgres (exit code? restart_policy?)
- [ ] Implementar pool de conexões no loader (ex.: `psycopg2.pool.ThreadedConnectionPool`)
- [ ] Adicionar retry com backoff para `_load_shard_worker` em caso de `OperationalError`
- [ ] Verificar se os TLDs `net` e `org` tiveram rerun automático ou ficaram com gap de dados

---

## P02 — R2 Marker Ausente após Run Databricks (9 TLDs)

### Horário
`2026-04-29T09:58 UTC` (todos simultâneos, pós-aguardo do ciclo Databricks)

### TLDs afetados
`au`, `ca`, `de`, `es`, `eu`, `fr`, `it`, `nl`, `uk`

### Erro
```
RuntimeError: R2 marker missing after Databricks run — TLD likely failed in notebook
```

### Causa provável
O notebook Databricks finalizou mas não gravou o marker de conclusão no R2 para esses TLDs. Isso pode indicar:
- Falha silenciosa no notebook (erro capturado sem propagação)
- Timeout no job Databricks
- Falha na escrita do parquet/delta para esses TLDs no notebook
- Problema de configuração de credencial/bucket R2 para o run específico

### Ações necessárias
- [ ] Acessar os logs do Databricks para o run de 29/04/2026 e verificar os 9 TLDs afetados
- [ ] Confirmar se os notebooks finalizaram com `SUCCESS` ou `FAILED` no Databricks UI
- [ ] Verificar se o R2 contém artefatos parciais para esses TLDs (parquet sem marker)
- [ ] Avaliar se um rerun manual no Databricks para esses TLDs é seguro e necessário
- [ ] Adicionar alertas quando `errors > 0` no resumo final `run_cycle done`

---

## P03 — API 500: `TldStatusItem` não aceita status `"partial"`

### Endpoint afetado
`GET /v1/ingestion/tld-status?source=openintel` → **500 Internal Server Error**  
*(todas as chamadas, sem exceção — afeta diretamente o painel /admin/ingestion)*

### Erro
```
pydantic_core.ValidationError: 1 validation error for TldStatusItem
Input should be 'ok', 'running', 'failed' or 'never_run'
input_value='partial', input_type=str
```

### Causa raiz
O router (`ingestion.py`) atribui `status = "partial"` quando `last_reason_code == "partial_load_added_only"`:

```python
# backend/app/api/v1/routers/ingestion.py
elif row.last_status in ("success", "ok"):
    if row.last_reason_code == "partial_load_added_only":
        status = "partial"   # ← atribuído aqui
    else:
        status = "ok"
```

Mas o schema define:
```python
# backend/app/schemas/czds_ingestion.py
TldStatusCategory = Literal["ok", "running", "failed", "never_run"]  # ← "partial" ausente
```

Também existe `status = "never_attempted"` no router, que também não consta no `Literal`.

### Fix
Adicionar `"partial"` (e `"never_attempted"`) ao `TldStatusCategory`:

```python
TldStatusCategory = Literal["ok", "running", "failed", "never_run", "partial", "never_attempted"]
```

### Ações necessárias
- [ ] Corrigir `TldStatusCategory` no schema `czds_ingestion.py`
- [ ] Verificar se o frontend trata e exibe `"partial"` e `"never_attempted"` adequadamente
- [ ] Fazer deploy do fix (requer build + push + `docker service update`)

---

## P04 — Ciclo de 26h: Gargalo de Performance por Timeouts Acumulados

### Descrição

O ciclo de ingestão CZDS de 28/04 levou **~26 horas** para concluir, causando:
- O disparo das 08:00 UTC de 29/04 ser **ignorado** (ciclo anterior ainda em andamento)
- Próxima execução agendada somente para **30/04 às 08:00 UTC**
- Gap de dados: nenhuma ingestão nova será capturada para 29/04

### Análise de duração por resultado

| Resultado | TLDs | Duração média | Duração máx |
|-----------|------|---------------|-------------|
| `success` | 647 | ~0 min | 31 min (`com`) |
| `r2_marker_missing` | 9 | **885 min** | 885 min |
| `pg_load_error` | 3 | 484 min | 885 min (`org`) |
| `unexpected_error` | 4 | 138 min | 174 min (`top`) |

### Insight chave

> **`com` — o maior TLD do mundo — completa em 31 minutos.**  
> O ciclo de 26h **não é causado por volume de dados**, mas por **falhas com timeouts longos e sem circuit breaker**.

O ciclo é dominado por 16 TLDs problemáticos que somam ~130+ horas de espera acumulada:

```
08:00  início do ciclo
       ↓ 647 TLDs pequenos → avg ~0 min  ✅
       ↓ shop, top, xyz, app → ~130 min cada ❌ unexpected_error
       ↓ biz, com → 2–31 min ✅
19:13  batch dos TLDs tier-1 (gigantes)
       ↓ net → 439 min ❌ pg_load_error
       ↓ org → 885 min ❌ pg_load_error
       ↓ uk, ca, de, es, eu, fr, it, nl, au → 885 min CADA ❌ r2_marker_missing
09:58  fim do ciclo (+26h)
```

### Causa raiz

1. **Timeout de r2_marker é ~885 min (~14,75h)** — o pipeline aguarda esse tempo antes de desistir. São 9 TLDs que somam ~132h de espera ociosa no ciclo.
2. **Sem circuit breaker** — um TLD travado não libera o pipeline para os seguintes.
3. **Falhas repetidas sem rerun automático** — TLDs que falham não são reprocessados na mesma execução.

### Impacto se corrigido

| Cenário | Duração estimada do ciclo |
|---------|--------------------------|
| Atual (sem correção) | ~26h |
| Só reduzir timeout r2_marker para 2h | ~8h |
| Corrigir r2_marker_missing (P02) | ~3–4h |
| Corrigir todos os erros (P01+P02) | **~1–2h** |

### Ações necessárias

- [ ] Reduzir timeout de espera do R2 marker (atualmente ~885 min → proposta: 90–120 min)
- [ ] Investigar por que `shop`, `top`, `xyz`, `app` falham com `unexpected_error` (~130 min cada) — checar logs do worker para stack trace específico
- [ ] Avaliar implementação de **dead-letter queue**: TLDs que falham são enfileirados para rerun ao final do ciclo, sem bloquear os demais
- [ ] Avaliar separação de fila por "peso" do TLD: TLDs grandes (net, org, com, de, uk) em fila dedicada com workers independentes
- [ ] Adicionar **métrica de duração do ciclo** no painel de monitoramento com alerta se exceder 12h
- [ ] Revisar lógica do scheduler: ciclo em andamento deve reter o próximo slot ao invés de pulá-lo

---

## Informações em Falta / Pontos Cegos

As seguintes informações **não estavam disponíveis** no momento da análise e são necessárias para diagnóstico completo:

| Item | Por que é necessário |
|------|----------------------|
| Logs do container `observador_postgres` em 02:30 e 09:55 UTC | Confirmar se houve reinício, OOM ou saturação de `max_connections` |
| Histórico de restart do container Postgres no dia | Saber se o DB reiniciou e causou as quedas de conexão |
| Logs do Databricks para o run de 29/04/2026 | Confirmar causa da falha nos 9 TLDs (timeout, erro de notebook, credencial) |
| Status atual dos TLDs `net` e `org` no banco | Verificar se há gap de dados real ou se houve rerun automático bem-sucedido |
| Quantos domínios deixaram de ser carregados | Medir impacto real nos dados (TLDs grandes como `net`, `org`, `de` têm milhões de registros) |
| Se `partial_load_added_only` é estado persistente ou transitório | Entender se o `"partial"` será frequente ou era caso isolado |
| Stack trace completo de `unexpected_error` para `shop`, `top`, `xyz`, `app` | Identificar a causa raiz do erro que trava por ~130 min |
| Valor atual do timeout de espera do R2 marker no código | Confirmar o valor exato para propor redução segura |

---

## Contexto Técnico

- **Worker de ingestão**: `observador-ingestion_ingestion_worker` (imagem `observador-ingestion:latest`)
- **Backend**: `observador_backend` (imagem `observador-backend:latest`)
- **Resumo final do ciclo CZDS**: `ok=647 skipped=462 errors=16`
- **Início do ciclo**: `2026-04-28T08:00:00 UTC`
- **Fim do ciclo**: `2026-04-29T10:00:10 UTC` (~26h de duração)
- **Arquivos relevantes**:
  - `backend/app/schemas/czds_ingestion.py` — `TldStatusCategory`
  - `backend/app/api/v1/routers/ingestion.py` — `get_tld_status()` (linha ~852)
  - `ingestion/orchestrator/pipeline.py` — `_load_tld_from_r2()` (linha 376, 401)
  - `ingestion/loader/delta_loader.py` — `_parallel_load_shards()` / `_load_shard_worker()`
