# References — TODO 010

## Arquivos do Worker

- `ingestion/scheduler.py` — Entry point, HTTP server porta 8080, `_run_daily_cycle()`
- `ingestion/ingestion/orchestrator/pipeline.py` — `run_cycle()`, idempotência SKIP/LOAD_ONLY/FULL_RUN
- `ingestion/ingestion/loader/delta_loader.py` — DETACH/ATTACH partition, bulk load parquet
- `ingestion/ingestion/observability/run_recorder.py` — `recover_stale_running_runs()`, heartbeat watchdog
- `backend/app/api/v1/routers/ingestion.py` — proxy triggers via `INGESTION_TRIGGER_URLS`

## Tabelas do Banco

- `ingestion_run` — registro de cada run por (source, tld, date)
- `ingestion_tld_policy` — políticas por TLD (priority, enabled)
- `domain` — tabela pai particionada por LIST(tld)
- `domain_{tld}` — partições por TLD

## Catálogo PostgreSQL Relevante

- `pg_class` — `relispartition` flag
- `pg_inherits` — relação pai-filho de partições
- `pg_constraint` — `coninhcount`, `conislocal`, `conparentid`
- `pg_index` — flags do índice
- `pg_attribute` — colunas da tabela (corrupção em `domain_xn__yfro4i67o`)

## Serviços de Produção

- Servidor: `158.69.211.109`
- Worker container: `observador_ingestion_worker.1.*`
- Postgres container: `observador_postgres.1.*`
- Worker HTTP: `http://localhost:8080/health`, `http://localhost:8080/run-now`

## Imagens Docker

- Imagem antiga (problemática): `9896fe` — sem `ON CONFLICT DO NOTHING`
- Imagem atual (corrigida): `d3e44f` — tem `ON CONFLICT DO NOTHING`
