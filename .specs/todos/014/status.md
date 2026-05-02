# Status — 014

**Status atual:** `done`

**Criado em:** 2026-05-01

**Prioridade:** 🔴 CRÍTICO — A corrupção de `pg_catalog.pg_class` está ativa em produção AGORA, crashando o autovacuum a cada 60 segundos há 5+ dias. Toda ingestão de TLDs que dure mais de ~15 minutos está sujeita a falha por queda de conexão PostgreSQL.

## Ações Completadas (Parte A — Operação em Produção 158.69.211.109)

✅ Todas as ações da Parte A foram executadas com sucesso:

1. **HOTFIX em produção** — força-congelamento de 22 tuplas corrompidas em `pg_catalog.pg_class`:
   - Usada extensão `pg_surgery`: `heap_force_freeze('pg_catalog.pg_class', ARRAY[...])`
   - `VACUUM FREEZE` executado com sucesso após fix: relfrozenxid avançado de 762739 → 912925
   - **Resultado**: autovacuum parou de crashar (0 crashes em 3 min de validação)
2. **Configurar SWAP de 8GB** — completado em `/swapfile`, persistido em `/etc/fstab`
3. **Re-executar runs do 01/05** — 4 runs marcadas como `pending` para scheduler reprocessar:
   - czds/xyz (connection reset)
   - czds/info (connection reset)
   - czds/org (stale recovered)
   - openintel/ch (stale recovered)

## Trabalho de Código Concluído

| Mudança | Arquivos | Migration |
|---------|----------|-----------|
| **M1+M6** — Retry resiliente, jitter, cancelamento de futures | `ingestion/ingestion/loader/delta_loader.py` | — |
| **M2** — Timeout do watchdog configurável por TLD | `backend/app/models/ingestion_tld_policy.py`, `backend/app/schemas/ingestion_config.py`, `backend/app/repositories/ingestion_config_repository.py`, `ingestion/ingestion/observability/run_recorder.py`, `ingestion/scheduler.py` | `044_tld_policy_stale_timeout.py` |
| **M3** — Checkpoint por shard | `backend/app/models/ingestion_shard_checkpoint.py`, `backend/app/models/__init__.py`, `ingestion/ingestion/loader/delta_loader.py`, `ingestion/ingestion/orchestrator/pipeline.py` | `045_ingestion_shard_checkpoint.py` |
| **M5** — Probe de health do autovacuum + script auxiliar | `backend/app/services/postgres_health_service.py`, `backend/app/debug_scripts/check_pg_autovacuum.sh` | — |

### Detalhes Importantes

- **Backoff de retry**: aumentado de 3 tentativas (22s totais) para 6 tentativas (até ~17 min totais) com jitter ±25%, para suportar instabilidade de Postgres por horas, não segundos.
- **Watchdog por TLD**: `czds/xyz` e `czds/info` recebem 8h de timeout via seed na migration 044; `czds/org` recebe 6h. Demais TLDs continuam com o default global (`INGESTION_STALE_TIMEOUT_MINUTES`, 45 min).
- **Checkpoint atômico**: a inserção em `ingestion_shard_checkpoint` ocorre dentro da mesma transação do `INSERT` na partição. Uma linha de checkpoint significa que o bulk insert também commitou — garantia atômica para retomada segura.
- **Skip cross-run**: na nova run, o loader consulta checkpoints de qualquer run anterior do mesmo `(source, tld, snapshot_date, partition)` nas últimas 24h e pula essas keys.
- **Health probe**: três sinais (autovacuum travado, bloat alto, idle-in-tx longo). Hoje só logam — o canal de delivery (Resend/webhook) deve ser plugado pelo job que chamar a função.

## Histórico de Status

| Data | Status | Responsável | Notas |
|------|--------|-------------|-------|
| 2026-05-01 | todo | — | Criado após análise do incidente de 01/05 |
| 2026-05-01 | in_progress | claude | Iniciada implementação da Parte B (M1+M6, M2, M3, M5). Parte A (hotfix produção) é runbook manual no plano. |
| 2026-05-01 | in_progress | claude | Parte B concluída (ver tabela acima). Pendente: hotfix manual em produção (Parte A do plan.md) + SWAP. |
| 2026-05-01 | done | claude | Parte A completada: pg_class force-freeze + VACUUM, SWAP 8GB, migrations 044+045 aplicadas, 4 runs reexecutadas, autovacuum estável (0 crashes em 3min). |
