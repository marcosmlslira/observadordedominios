# 008 — Referências

## Motor canônico: `ingestion/` package

> Tudo fora de `ingestion/` relacionado a ingestão é **legado** e será deprecado.

### Código do pipeline novo
- `ingestion/ingestion/cli.py` — CLI entry point, subcomandos `czds`, `openintel`, `load`, `submit`
- `ingestion/ingestion/runners/czds_runner.py` — pipeline CZDS: auth → download → diff → R2
- `ingestion/ingestion/runners/openintel_runner.py` — pipeline OpenINTEL: S3/web → diff → R2
- `ingestion/ingestion/loader/delta_loader.py` — bulk load R2 → PostgreSQL (ON CONFLICT DO NOTHING)
- `ingestion/ingestion/databricks/submitter.py` — submete notebook ao Databricks e aguarda resultado
- `ingestion/ingestion/databricks/notebooks/czds_ingestion.py` — notebook CZDS (3-cell pattern)
- `ingestion/ingestion/databricks/notebooks/openintel_ingestion.py` — notebook OpenINTEL
- `ingestion/ingestion/observability/run_log.py` — log de execução gravado no R2
- `ingestion/ingestion/config/settings.py` — todas as configurações via env vars

### Código legado (a deprecar na Fase 0)
- `backend/app/services/use_cases/sync_czds_tld.py` — pipeline CZDS legado (download + apply direto no PG)
- `backend/app/services/use_cases/sync_openintel_tld.py` — pipeline OpenINTEL legado
- Endpoints da API que chamam estes use cases

### Backend (compartilhado — usado por ambos)
- `backend/app/models/ingestion_run.py` — ORM model da tabela `ingestion_run`
- `backend/app/models/ingestion_tld_policy.py` — ORM model com `priority`, `is_enabled`
- `backend/app/models/domain.py` — Domain model (ADR-001: name, tld, label, added_day)
- `backend/app/models/domain_removed.py` — DomainRemoved model (ADR-001: name, tld, removed_day)
- `backend/app/repositories/ingestion_run_repository.py` — repositório de runs (create_run, finish_run)
- `backend/app/repositories/ingestion_config_repository.py` — `list_tld_policies()` por source
- `backend/app/repositories/domain_repository.py` — `bulk_insert()` com ON CONFLICT DO NOTHING
- `backend/app/api/v1/routers/ingestion.py` — endpoints de observabilidade

### Similarity (impactado pela ingestão)
- `backend/app/services/use_cases/run_similarity_scan.py` — scan que usa `added_day >= watermark_day`
- `backend/app/repositories/similarity_repository.py` — queries com GIN trigram + watermark
- `backend/app/models/similarity_scan_cursor.py` — cursor com `watermark_day` INTEGER (YYYYMMDD)
- `backend/app/services/similarity_scan_jobs.py` — job queue para similarity scans

### Frontend
- `frontend/app/admin/ingestion/page.tsx` — página principal de monitoramento
- `frontend/app/admin/ingestion/[source]/page.tsx` — configuração por fonte
- `frontend/hooks/use-ingestion-data.ts` — hook de dados de ingestão

## Documentação de referência
- `docs/adr/001-domain-table-redesign.md` — schema canônico (append-only, added_day, domain_removed)
- `infra/stack.yml` — stack de produção (referência para adicionar obs_ingestion_worker)
- `infra/stack.dev.yml` — stack de desenvolvimento

## Constantes importantes
- **LARGE_TLDS** (obrigatório Databricks): `com, net, org, de, uk, br, info, biz, nl, cn, ru, au, fr, it, es, pl, ca, jp, in, eu, app`
- **OpenINTEL cctlds-web**: ~200 TLDs (ac, ad, ae... zw) + IDNs
- **CZDS**: ~1.400+ gTLDs (aaa, aarp... zuerich) + com, net, org, biz, info, etc.

## Infraestrutura
- Produção: `ssh ubuntu@158.69.211.109`
- PostgreSQL tunnel: `ssh -N -L 5433:localhost:15432 ubuntu@158.69.211.109` → localhost:5433
- DATABASE_URL: `postgresql://obs:<senha>@postgres:5432/obs` (credenciais via Docker secrets)
- CI/CD: `.github/workflows/build-push.yml` → GHCR → `docker-stack-infra` repo dispatch
- **NUNCA** deploy manual do `infra/stack.yml` em produção
