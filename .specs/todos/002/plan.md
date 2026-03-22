# 002 — Plano de Implementação (NSEC Zone Walking)

## Escopo da fase

- Ingestão complementar via NSEC para TLDs walkable, iniciando em `br`.
- Execução em worker dedicado `nsec_walker` (separado de API e CZDS).
- Persistência raw em S3/MinIO e delta no PostgreSQL.
- Governança por `source='nsec'` e política por TLD.

## Fase A — Modelagem e base de dados

1. Criar modelo `nsec_tld_policy` em `backend/app/models/`.
2. Criar migração Alembic com:
   - tabela `nsec_tld_policy`;
   - índices por `walk_enabled` e `priority`;
   - seeds iniciais para `br`.
3. Validar compatibilidade com tabelas já usadas na ingestão CZDS:
   - `ingestion_run`
   - `ingestion_checkpoint`
   - `zone_file_artifact`
   - `domain`
   - `domain_observation`

## Fase B — Integrações externas e infra

1. Implementar cliente DNS NSEC em `backend/app/infra/external/dns_client.py` (dnspython).
2. Reusar storage S3 compatível em `backend/app/infra/external/s3_storage.py`.
3. Padronizar chave raw:
   - `zones/nsec/{tld}/{yyyy}/{mm}/{dd}/{run_id}/{tld}.txt.gz`.
4. Garantir rate limit e retry/backoff configuráveis por env/política.

## Fase C — Use cases e delta real

1. Implementar `walk_nsec_zone.py` com:
   - loop de owner/next owner;
   - checkpoint de progresso;
   - tolerância a timeout intermitente.
2. Implementar `sync_nsec_tld.py` com:
   - lock por `source+tld`;
   - validação de cooldown;
   - lifecycle de `ingestion_run`.
3. Implementar `apply_nsec_delta.py` com:
   - upsert de novos/reativados;
   - soft delete dos removidos;
   - persistência de métricas por run.

## Fase D — API e observabilidade

1. Criar router `backend/app/api/v1/routers/nsec_ingestion.py`.
2. Expor endpoints:
   - `POST /v1/nsec/trigger-walk`
   - `GET /v1/nsec/runs/{run_id}`
3. Criar schemas em `backend/app/schemas/nsec_ingestion.py`.
4. Incluir logs estruturados e métricas operacionais do walk.

## Fase E — Worker e stack

1. Criar entrypoint de worker NSEC com scheduler diário.
2. Atualizar `infra/stack.dev.yml` com serviço `nsec_walker` (replica 1).
3. Atualizar `infra/stack.yml` com serviço equivalente de produção.
4. Configurar variáveis `NSEC_*` em ambiente.

## Fase F — Validação técnica

1. Executar trigger manual para `br`.
2. Validar:
   - artefato raw no storage;
   - contadores em `ingestion_run`;
   - resultado de delta no banco.
3. Executar 2º ciclo para validar idempotência e remoções.
4. Atualizar `.specs/todos/002/status.md` e `_registry.md`.

## Entregáveis

- Refinamento técnico complementar NSEC documentado.
- Política de TLD NSEC modelada.
- Worker NSEC funcional no stack.
- Endpoints de trigger/status para operação controlada.
- Evidência de execução fim-a-fim com `br`.
