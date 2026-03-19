# 001 — Plano de Implementação (CZDS)

## Escopo da fase

- Ingestão de TLDs iniciais: `net`, `org`, `info`.
- Soft delete para domínios ausentes na zona (`deleted_at`).
- Execução via worker dedicado (`czds_ingestor`).
- Storage raw em MinIO no ambiente dev.

## Fase A — Modelagem e base de dados

1. Criar modelos SQLAlchemy em `backend/app/models/`:
   - `domain.py`
   - `domain_observation.py`
   - `ingestion_run.py`
   - `ingestion_checkpoint.py`
   - `zone_file_artifact.py`
   - `czds_tld_policy.py`
2. Criar migração Alembic com tabelas, FKs, constraints e índices.
3. Incluir dados seed de `czds_tld_policy` com:
   - `net`, `org`, `info` como habilitados;
   - prioridade incremental (`1,2,3`).

## Fase B — Infra de integração externa

1. Implementar cliente CZDS em `backend/app/infra/external/czds_client.py`.
2. Implementar storage S3 compatível (MinIO/AWS) em `backend/app/infra/external/s3_storage.py`.
3. Padronizar chave de objeto:
   - `zones/czds/{tld}/{yyyy}/{mm}/{dd}/{run_id}/{tld}.zone.gz`.
4. Persistir metadados do artefato em `zone_file_artifact`.

## Fase C — Use cases e delta real

1. Implementar use case `sync_czds_tld.py` com:
   - lock por TLD;
   - controle de cooldown;
   - criação/finalização de `ingestion_run`.
2. Implementar `apply_zone_delta.py`:
   - staging table temporária por run;
   - bulk insert dos domínios parseados;
   - upsert de novos/reativados;
   - soft delete dos removidos (`status='deleted'`, `deleted_at=now()`).
3. Registrar métricas (`seen`, `inserted`, `reactivated`, `deleted`).

## Fase D — API de controle e observabilidade

1. Criar router `backend/app/api/v1/routers/czds_ingestion.py`.
2. Expor endpoints:
   - `POST /v1/czds/trigger-sync`
   - `GET /v1/czds/runs/{run_id}`
3. Adicionar schema Pydantic para request/response.
4. Garantir logs estruturados por `run_id` e `tld`.

## Fase E — Worker e stack

1. Criar entrypoint do worker (scheduler + execução serial por prioridade).
2. Atualizar `infra/stack.dev.yml` com serviço `czds_ingestor` (replica 1).
3. Adicionar serviço equivalente em `infra/stack.yml`.
4. Incluir variáveis de ambiente para MinIO em dev.

## Fase F — Validação técnica

1. Executar sync manual para `net`.
2. Validar:
   - objeto raw no MinIO;
   - contadores de run;
   - soft delete em delta controlado.
3. Executar `org` e `info` na sequência.
4. Registrar resultado no `status.md` e atualizar `_registry.md`.

## Entregáveis

- Migração e modelos da ingestão CZDS.
- Worker dedicado funcional no stack.
- Endpoints de trigger/status.
- Evidência de execução fim-a-fim com MinIO (dev).
- Governança ativa em `.specs/todos/001`.
