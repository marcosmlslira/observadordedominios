# 003 — Referências e Decisões

## Refinamento base

- Documento principal: `docs/similarity-service-refinement.md`
- Contexto arquitetural validado: separação de `similarity-service` e `enrichment-worker`.

## Decisões aprovadas

- S1: `similarity-service` será microserviço dedicado e read-heavy.
- S2: endpoint principal em `POST /v1/similarity/search`.
- S3: busca híbrida inicial (`typo`, `fuzzy`, `vector`) com score composto.
- S4: serviço não executa enrichment síncrono.
- S5: enriquecimento roda assíncrono em worker via fila.
- S6: filtros por `source` (`czds`/`nsec`) e por TLD são obrigatórios no contrato.

## Objetivo técnico

Entregar a especificação operacional da busca de similaridade com:

1. contrato HTTP estável e versionado,
2. semântica de score explicável por resultado,
3. paginação e filtros para domínios ingeridos,
4. isolamento de carga entre consulta e enrichment,
5. base para implementação FastAPI + PostgreSQL + pgvector.
