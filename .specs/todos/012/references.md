# TODO 012 — References

## Logs de produção (coletados em 29/04/2026 ~15:30 BRT)

### Ingestion Worker — Erros
```
observador-ingestion_ingestion_worker @ 2026-04-29T02:32:21 UTC
  ERROR ingestion.orchestrator.pipeline — post-databricks pg load failed tld=net
  psycopg2.OperationalError: server closed the connection unexpectedly

observador-ingestion_ingestion_worker @ 2026-04-29T09:58:00 UTC
  ERROR ingestion.orchestrator.pipeline — post-databricks pg load failed tld=org
  psycopg2.OperationalError: server closed the connection unexpectedly

observador-ingestion_ingestion_worker @ 2026-04-29T09:58:01–04 UTC
  ERROR ingestion.orchestrator.pipeline — post-databricks pg load failed tld={au,ca,de,es,eu,fr,it,nl,uk}
  RuntimeError: R2 marker missing after Databricks run — TLD likely failed in notebook

observador-ingestion_ingestion_worker @ 2026-04-29T09:58:04 UTC
  INFO run_cycle done source=czds ok=647 skipped=462 errors=16

observador-ingestion_ingestion_worker @ 2026-04-29T10:00:10 UTC
  INFO czds recovery done: {total:1125, ok:647, skipped:462, errors:16}
  INFO === czds recovery cycle complete === {trigger: schedule_czds_recovery, started_at: 2026-04-28T08:00:00 UTC, finished_at: 2026-04-29T10:00:10 UTC}
```

### Backend — Erro de API
```
observador_backend @ (múltiplas ocorrências ao longo do dia)
  GET /v1/ingestion/tld-status?source=openintel → 500 Internal Server Error
  pydantic_core.ValidationError: 1 validation error for TldStatusItem
  Input should be 'ok', 'running', 'failed' or 'never_run' [type=literal_error, input_value='partial']
```

## Arquivos de código relevantes

| Arquivo | Relevância |
|---------|------------|
| `backend/app/schemas/czds_ingestion.py` | Define `TldStatusCategory` (Literal sem `"partial"`) |
| `backend/app/api/v1/routers/ingestion.py` linha ~852 | `get_tld_status()` — atribui `status = "partial"` |
| `ingestion/orchestrator/pipeline.py` linha 376, 401 | `_load_tld_from_r2()` — ponto de falha P01 e P02 |
| `ingestion/loader/delta_loader.py` linha 153, 213, 270 | `_load_shard_worker()` / `_parallel_load_shards()` — conexão caída |

## TODOs relacionados

- **TODO 009** — Correções de Confiabilidade no Monitoramento de Ingestão (status `partial` e semântica de saúde)
- **TODO 010** — Catálogo de Problemas: Ciclo de Ingestão em Produção (incidentes anteriores)
- **TODO 011** — Ingestão "Boring": estabilização estrutural do ciclo diário
