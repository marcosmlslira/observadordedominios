# Runbook — Pipeline de Ingestão

> Procedimentos operacionais para o serviço `observador-ingestion`.
> Audiência: SRE / backend lead.

---

## Visão Geral

O worker de ingestão roda como serviço Docker Swarm isolado (`observador-ingestion`).
Ele executa um ciclo diário às **04:00 UTC (01:00 UTC-3)** em duas fases:

1. **OpenINTEL** — snapshots de zonas DNS via R2 (Cloudflare)
2. **CZDS** — zone files de gTLDs via ICANN CZDS (`.com` sempre por último via Databricks)

Endpoints internos do worker (porta 8080):

| Endpoint | Método | Descrição |
|---|---|---|
| `/health` | GET | Status do worker + último ciclo |
| `/run-now` | POST | Disparo manual (requer `X-Ingestion-Trigger-Token`) |

Endpoints do backend para observabilidade:

| Endpoint | Descrição |
|---|---|
| `GET /v1/ingestion/cycles` | Histórico de ciclos (`ingestion_cycle`) |
| `GET /v1/ingestion/tlds/health` | Último run por `(source, tld)` |
| `GET /v1/ingestion/incidents` | Falhas e recoveries das últimas N horas |
| `GET /v1/ingestion/summary` | Resumo por fonte |

---

## Diagnóstico Inicial

### 1. O worker está vivo?

```bash
# via docker swarm
docker service ps obs_ingestion --no-trunc

# via health endpoint (substitua o IP/porta)
curl http://<worker-host>:8080/health | jq .
```

Campos-chave na resposta:

- `run_in_progress` — `true` se um ciclo está rodando agora
- `shutting_down` — `true` se recebeu SIGTERM (não inicia novos ciclos)
- `last_cycle.status` — `succeeded | failed | interrupted | running`
- `last_cycle.last_heartbeat_at` — deve ser recente (< 2 min) durante ciclo ativo

### 2. Checar ciclos recentes no banco

```sql
SELECT cycle_id, started_at, finished_at, status, triggered_by,
       tld_success, tld_failed, tld_skipped, tld_load_only,
       last_heartbeat_at
FROM ingestion_cycle
ORDER BY started_at DESC
LIMIT 10;
```

### 3. Checar runs individuais com falha

```sql
SELECT id, source, tld, status, reason_code, error_message,
       started_at, finished_at
FROM ingestion_run
WHERE status = 'failed'
  AND started_at > now() - interval '48 hours'
ORDER BY started_at DESC
LIMIT 30;
```

---

## Cenários de Falha

### Ciclo travado (`status = 'running'` mas heartbeat stale)

**Sintomas:** `/health` mostra `run_in_progress: true` mas `last_heartbeat_at` está
parado há > 60 minutos.

**Causa comum:** OOM do container, SIGKILL sem SIGTERM, deadlock de rede.

**Ação:**

1. Verificar logs do container:
   ```bash
   docker service logs obs_ingestion --tail 200
   ```

2. O watchdog de stale runs (`_start_stale_watchdog`) recupera automaticamente ciclos
   e runs após 60 min de inatividade no heartbeat. Não é necessário intervenção manual
   se o watchdog está ativo.

3. Recuperação manual se necessário:
   ```sql
   -- Fechar ciclo stale
   UPDATE ingestion_cycle
   SET status = 'interrupted', finished_at = now(), last_heartbeat_at = now()
   WHERE status = 'running'
     AND COALESCE(last_heartbeat_at, started_at) < now() - interval '60 minutes';

   -- Fechar runs stale
   UPDATE ingestion_run
   SET status = 'failed', reason_code = 'stale_recovered',
       finished_at = now(), updated_at = now()
   WHERE status = 'running'
     AND updated_at < now() - interval '60 minutes';
   ```

4. Reiniciar o serviço:
   ```bash
   docker service update --force obs_ingestion
   ```

---

### TLD com falhas recorrentes

**Sintomas:** Mesmo TLD aparece com `status = 'failed'` nos últimos 3+ dias.

**Ação:**

1. Identificar reason_code:
   ```sql
   SELECT reason_code, error_message, COUNT(*) AS n
   FROM ingestion_run
   WHERE tld = 'exemplo' AND status = 'failed'
     AND started_at > now() - interval '7 days'
   GROUP BY reason_code, error_message
   ORDER BY n DESC;
   ```

2. Por reason_code:

   | `reason_code` | Ação |
   |---|---|
   | `no_snapshot` | Snapshot não disponível — verificar CZDS/OpenINTEL; aguardar próximo ciclo |
   | `databricks_submit_error` | Verificar credenciais Databricks e quota |
   | `databricks_run_error` | Verificar notebook Databricks; logs em `ingestion_run.error_message` |
   | `pg_load_error` | Verificar conectividade PG; verificar locks em `pg_stat_activity` |
   | `r2_marker_missing` | Marker R2 ausente após Databricks — notebook não gravou dados |
   | `unexpected_error` | Ver `error_message`; checar logs do container |

3. Desabilitar TLD temporariamente se necessário:
   ```sql
   UPDATE ingestion_tld_policy
   SET is_enabled = false
   WHERE source = 'czds' AND tld = 'exemplo';
   ```

---

### Worker com OOM (Out of Memory)

**Sintomas:** Container reinicia frequentemente; logs mostram `Killed`.

**Ação imediata:**

1. Verificar uso de memória:
   ```bash
   docker stats obs_ingestion
   ```

2. Aumentar limite de memória em `docker-stack-infra` (coordenar com deploy manual):
   ```yaml
   resources:
     limits:
       memory: 4g   # aumentar conforme necessário
   ```

3. TLDs grandes (`.com`, `.net`, `.org`) processam via Databricks — se o problema é
   num TLD pequeno, investigar o snapshot (arquivo corrompido, encoding inesperado).

4. Verificar log de memória por TLD (nível DEBUG):
   ```
   mem[start] tld=example source=czds phase=full_run rss_kb=...
   mem[end]   tld=example source=czds phase=full_run rss_kb=... delta_kb=...
   ```
   O campo `delta_kb` indica crescimento de memória por TLD.

---

### Disparo manual de ciclo

**Via API do backend (recomendado):**

```bash
curl -X POST https://api.observadordedominios.com.br/v1/ingestion/trigger/daily-cycle \
  -H "Authorization: Bearer <admin_token>"
```

**Via worker diretamente:**

```bash
curl -X POST http://<worker-host>:8080/run-now \
  -H "X-Ingestion-Trigger-Token: <OBSERVADOR_INGESTION_TRIGGER_TOKEN>"
```

Respostas:

- `202 accepted` — ciclo iniciado em background
- `409 already_running` — ciclo já em andamento; aguardar conclusão
- `503 shutting_down` — worker em shutdown; reiniciar o serviço primeiro
- `401 unauthorized` — token inválido

---

### Deploy da stack de ingestão

A stack de ingestão (`observador-ingestion`) é deployada **manualmente e de forma
coordenada**, separada do CI/CD do backend/frontend. Isso evita que um push no
backend reinicie o worker no meio de um ciclo de ingestão.

**Passos:**

1. Aguardar o ciclo atual terminar (`run_in_progress: false` no `/health`)
2. Fazer o deploy via `docker-stack-infra`:
   ```bash
   docker stack deploy -c observador-ingestion.yml obs
   ```
3. Verificar que o novo container subiu:
   ```bash
   docker service ps obs_ingestion
   curl http://<worker-host>:8080/health | jq .status
   ```

---

## Monitoramento Proativo

### Alertas recomendados

| Condição | Threshold | Ação |
|---|---|---|
| Nenhum ciclo concluído em 26h | `ingestion_cycle.status != 'succeeded' AND started_at < now() - 26h` | Investigar worker |
| Ciclo com > 10% de TLDs falhando | `tld_failed / (tld_success + tld_failed) > 0.1` | Investigar por reason_code |
| Heartbeat stale > 60min durante ciclo | `status = 'running' AND last_heartbeat_at < now() - 60m` | Worker provavelmente morto |
| R2 com > 5 TLDs em `delayed` | `openintel_tld_status.status = 'delayed' COUNT > 5` | Verificar OpenINTEL upstream |

### Métricas de duração (log)

O scheduler emite esta linha ao final de cada ciclo:

```
metric ingestion_cycle_duration_seconds=<N> status=<status> trigger=<trigger>
  tld_success=<N> tld_failed=<N> tld_skipped=<N> tld_load_only=<N>
```

Use para baseline de duração esperada e detecção de regressões.

---

## Histórico de Decisões

- **ADR-002** — Separação da stack de ingestão do backend
- **TODO 010** — Diagnóstico forense do pipeline original
- **TODO 011** — Refatoração de resiliência (Sprint 1-5)

Tabelas-chave: `ingestion_cycle`, `ingestion_run`, `ingestion_tld_policy`,
`openintel_tld_status`, `tld_health_v`.
