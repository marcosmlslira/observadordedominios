# 014 — Handoff: Trabalho Realizado e Pendências

> Documento gerado em **2026-05-01** ao final da sessão de implementação da
> Parte B (código). A Parte A (operação manual em produção) permanece como
> hand-off para o time de operação.

---

## TL;DR

- **Parte B (código)**: ✅ concluída. 5 grupos de mudanças (M1+M6, M2, M3, M5),
  2 migrations Alembic novas, 6 arquivos novos, 11 arquivos modificados.
- **Parte A (ops em produção)**: ⏳ pendente. Requer SSH em
  `158.69.211.109`; runbook completo em [`plan.md`](plan.md), seção "Parte A".
- **Status do incidente**: `in_progress` até a Parte A ser executada e
  validada — a corrupção em `pg_catalog.pg_class` continua ativa em produção
  enquanto este documento é escrito.

---

## ✅ O que foi feito

### Tabela-resumo

| Item | Descrição | Migration | Status |
|------|-----------|-----------|--------|
| M1 | Retry com backoff exponencial + jitter no `delta_loader` | — | ✅ |
| M6 | Cancelamento de futures pendentes em `_parallel_load_shards` | — | ✅ |
| M2 | Timeout do stale watchdog configurável por TLD | `044_tld_policy_stale_timeout.py` | ✅ |
| M3 | Checkpoint por shard com retomada cross-run | `045_ingestion_shard_checkpoint.py` | ✅ |
| M5 | Probe de saúde do autovacuum + script auxiliar | — | ✅ |

### Mudanças por arquivo

**Modificados:**

- [`ingestion/ingestion/loader/delta_loader.py`](../../../ingestion/ingestion/loader/delta_loader.py)
  - `_SHARD_MAX_RETRIES`: 3 → 6
  - `_SHARD_RETRY_BACKOFF`: `(2, 5, 15)` → `(5, 30, 60, 120, 300, 600)` segundos
  - Novo `_SHARD_RETRY_JITTER = 0.25` (±25%)
  - Detecção explícita de "server closed the connection" / "connection reset" via `_CONNECTION_LOSS_MARKERS`
  - `_parallel_load_shards`: cancela futures pendentes via `pool.shutdown(cancel_futures=True)` + `future.cancel()` em caso de exceção; loga `completed`/`cancelled`/`total`
  - Nova função `_completed_shard_keys` consulta `ingestion_shard_checkpoint`
  - `_load_shard_worker` grava checkpoint na **mesma transação** do `INSERT` na partição (atomicidade)
  - `load_delta` aceita `run_id` opcional e propaga
- [`ingestion/ingestion/orchestrator/pipeline.py`](../../../ingestion/ingestion/orchestrator/pipeline.py)
  - Duas chamadas a `load_delta` (linhas ~311 e ~459) agora passam `run_id`
- [`ingestion/ingestion/observability/run_recorder.py`](../../../ingestion/ingestion/observability/run_recorder.py)
  - `recover_stale_running_runs`: query agora usa `COALESCE((SELECT stale_timeout_seconds FROM ingestion_tld_policy ...), default_seconds)` para suportar override por TLD
- [`ingestion/scheduler.py`](../../../ingestion/scheduler.py)
  - `_start_stale_watchdog`: `stale_minutes` agora é opcional e lê de `settings.ingestion_stale_timeout_minutes` quando não fornecido (eliminado hardcode 60)
  - `recover_stale_running_cycles`: também migrado para `cfg.ingestion_stale_timeout_minutes`
- [`backend/app/models/ingestion_tld_policy.py`](../../../backend/app/models/ingestion_tld_policy.py)
  - Nova coluna `stale_timeout_seconds INTEGER NULL`
- [`backend/app/models/__init__.py`](../../../backend/app/models/__init__.py)
  - Registra `IngestionShardCheckpoint`
- [`backend/app/schemas/ingestion_config.py`](../../../backend/app/schemas/ingestion_config.py)
  - `TldPolicyPatchRequest` e `TldPolicyResponse` ganham `stale_timeout_seconds: int | None`
- [`backend/app/repositories/ingestion_config_repository.py`](../../../backend/app/repositories/ingestion_config_repository.py)
  - `patch_tld` aceita `stale_timeout_seconds` e flag `clear_stale_timeout`

**Novos:**

- [`backend/alembic/versions/044_tld_policy_stale_timeout.py`](../../../backend/alembic/versions/044_tld_policy_stale_timeout.py)
  - Adiciona coluna + seeds: `czds/xyz=28800s`, `czds/info=28800s`, `czds/org=21600s`
- [`backend/alembic/versions/045_ingestion_shard_checkpoint.py`](../../../backend/alembic/versions/045_ingestion_shard_checkpoint.py)
  - Cria tabela `ingestion_shard_checkpoint` + 2 índices + UNIQUE `(run_id, shard_key, partition)`
- [`backend/app/models/ingestion_shard_checkpoint.py`](../../../backend/app/models/ingestion_shard_checkpoint.py)
  - Modelo SQLAlchemy correspondente
- [`backend/app/services/postgres_health_service.py`](../../../backend/app/services/postgres_health_service.py)
  - 3 probes: autovacuum travado, bloat alto, idle-in-tx longo
  - Retorna `PostgresHealthFindings` estruturado e loga em WARNING/ERROR
  - Não envia notificação — delivery channel (Resend/webhook) deve ser plugado externamente
- [`backend/app/debug_scripts/check_pg_autovacuum.sh`](../../../backend/app/debug_scripts/check_pg_autovacuum.sh)
  - Bash cron-friendly: `docker logs --since` + grep dos padrões de erro de autovacuum
  - Exit codes: 0 = ok, 2 = alerta, 1 = não rodou

### Cadeia de migrations validada

```
041_tld_daily_policy_status_view
 └─ 042_drop_legacy_zone_file_artifact
     └─ 043_drop_legacy_czds_tld_policy
         └─ 044_tld_policy_stale_timeout            ← NOVA
             └─ 045_ingestion_shard_checkpoint       ← NOVA
```

Todos os arquivos passaram em `python -m ast` (parse OK).

### Decisões de design relevantes

- **Atomicidade do checkpoint**: gravação em `ingestion_shard_checkpoint` está
  dentro da mesma transação do `INSERT` da partição. Uma linha de checkpoint
  *garante* que o bulk insert também commitou.
- **Tolerância à ausência da tabela**: `_completed_shard_keys` engole erro de
  "relation does not exist" e devolve `set()` vazio. Permite rodar o código
  novo num ambiente sem migration 045 ainda — o pior caso é "sem otimização
  de skip", não "falha de ingestão".
- **Skip cross-run**: a retomada não reaproveita `run_id` da run falhada — em
  vez disso, uma nova run consulta checkpoints de qualquer run anterior do
  mesmo `(source, tld, snapshot_date, partition)` nas últimas 24h. Mais
  simples e não invade o contrato existente de `ingestion_run`.
- **Override de timeout opt-in**: TLDs sem `stale_timeout_seconds` mantêm o
  default global (`INGESTION_STALE_TIMEOUT_MINUTES = 45`). Sem regressão para
  TLDs pequenos.

---

## ⏳ O que precisa ser feito

### Pendência crítica (Parte A — runbook em [`plan.md`](plan.md))

Executar **na ordem**, no host `158.69.211.109`:

1. **Confirmar que a corrupção ainda está ativa**
   ```bash
   docker logs e41fef3d8211 --since 10m 2>&1 | grep "xmin.*relfrozenxid" | tail -5
   ```

2. **Corrigir corrupção em `pg_catalog.pg_class`**
   ```bash
   docker exec -it e41fef3d8211 psql -U obs -d obs <<'SQL'
   SET zero_damaged_pages = on;
   VACUUM FREEZE VERBOSE pg_catalog.pg_class;
   RESET zero_damaged_pages;
   SELECT relname, relfrozenxid, age(relfrozenxid)
     FROM pg_catalog.pg_class WHERE relname='pg_class';
   SQL
   ```
   Se o `VACUUM FREEZE` falhar mesmo com `zero_damaged_pages`: usar fallback
   A.6 do `plan.md` (`pg_dumpall` + recriar volume + restore).

3. **Validar (aguardar 3 min e checar logs)**
   ```bash
   sleep 180
   docker logs e41fef3d8211 --since 3m 2>&1 | grep -c "xmin.*relfrozenxid"
   # Esperado: 0
   ```

4. **Configurar SWAP de 8GB**
   ```bash
   sudo fallocate -l 8G /swapfile
   sudo chmod 600 /swapfile
   sudo mkswap /swapfile
   sudo swapon /swapfile
   echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
   ```

5. **Aplicar migrations 044 e 045 no banco de produção**
   ```bash
   docker exec -it <obs_backend_container> alembic upgrade head
   ```
   Esperado: aplicar 044 e 045 sem erro.

6. **Re-executar runs falhadas de 01/05** (via API admin):
   - czds/xyz (unexpected_error)
   - czds/info (unexpected_error)
   - czds/org (stale_recovered)
   - openintel/ch (stale_recovered)

7. **Plugar o probe de health no scheduler ou em cron**
   - Opção A: `backend/app/debug_scripts/check_pg_autovacuum.sh` em cron a
     cada 5 min com `||` para curl em webhook de alerta.
   - Opção B: chamar `check_postgres_autovacuum_health()` de um job no
     `apscheduler` do `ingestion/scheduler.py`.
   - O canal de delivery (Resend, webhook) ainda precisa ser definido — ver
     "Pendências de plumbing" abaixo.

8. **Atualizar este todo**
   - Marcar `_registry.md` como `done`
   - Última linha de `status.md` com data/responsável

### Pendências de plumbing (não bloqueantes)

- **Wire-up do canal de alerta**: `postgres_health_service.py` hoje só loga.
  Precisa ser conectado a um canal real (Resend transacional ou webhook
  configurável). Ver skill `email-best-practices` se for via Resend.
- **Cleanup de `ingestion_shard_checkpoint`**: a tabela cresce com o tempo.
  Sugestão: job que deleta `WHERE loaded_at < now() - interval '30 days'`.
  Pode virar TODO 015 se não for crítico.
- **Frontend**: a coluna `stale_timeout_seconds` aparece em
  `TldPolicyResponse` mas o `frontend/components/ingestion/source-config-page.tsx`
  ainda não permite editar. Pode ser uma melhoria futura — não é blocker.
- **Testes de integração**: o plano sugere testes end-to-end (simular
  `psycopg2.OperationalError` no shard 5 de 10, etc.). Ainda não
  implementados — criar quando o time tiver bandwidth.

### Verificação pós-deploy

Depois que a Parte A rodar, validar com:

```bash
# 1. Autovacuum parou de crashar
docker logs e41fef3d8211 --since 1h 2>&1 | grep -c "xmin.*relfrozenxid"  # esperado: 0

# 2. Migrations aplicadas
docker exec -it <obs_backend> alembic current  # esperado: 045_ingestion_shard_checkpoint

# 3. Seeds da policy aplicados
docker exec -it <postgres> psql -U obs -d obs -c \
  "SELECT source, tld, stale_timeout_seconds FROM ingestion_tld_policy
    WHERE stale_timeout_seconds IS NOT NULL ORDER BY tld;"
# Esperado: czds/xyz=28800, czds/info=28800, czds/org=21600

# 4. Runs reexecutadas com sucesso
curl $API/v1/ingestion/runs?date=$(date -u +%Y-%m-%d) | jq '.runs[] | {tld,status}'

# 5. Checkpoints sendo gravados
docker exec -it <postgres> psql -U obs -d obs -c \
  "SELECT count(*) FROM ingestion_shard_checkpoint
    WHERE loaded_at > now() - interval '1 day';"

# 6. SWAP ativo
ssh obs@158.69.211.109 'free -h' | grep -i swap
```

---

## Referências

- Plano original: [`plan.md`](plan.md)
- Status do incidente: [`status.md`](status.md)
- Logs e artefatos do incidente: [`references.md`](references.md)
- Registro mestre: [`../_registry.md`](../_registry.md)
- Issues relacionadas:
  - `.specs/todos/009/plan.md` — Confiabilidade do monitoramento de ingestão
  - `.specs/todos/010/plan.md` — Catálogo de problemas do ciclo
  - `.specs/todos/012/plan.md` — Incidente 29/04 (16 TLDs com falha)
