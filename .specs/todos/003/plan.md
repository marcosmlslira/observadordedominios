# 003 — Plano de Implementação (Similarity Service)

## Escopo da fase

- Criar microserviço `similarity-service` para busca de domínios semelhantes.
- Operar apenas sobre domínios já ingeridos (`source=czds|nsec`).
- Expor endpoint HTTP versionado e orientado a leitura.
- Manter enrichment desacoplado por fila/worker.

## Fase A — Modelagem de consulta

1. Definir contrato de request/response em schemas Pydantic.
2. Definir normalização do domínio de entrada (lowercase/punycode).
3. Definir score híbrido v1 e regras de corte (`min_score`).
4. Definir paginação (`offset` + `max_results`) e ordenação estável.

## Fase B — Persistência e performance

1. Garantir campo `embedding vector(384)` no armazenamento consultado.
2. Garantir índices para leitura:
   - B-tree (`tld`, `status`, `source`),
   - trigram para fuzzy,
   - índice vetorial para ANN.
3. Definir fallback de busca quando embedding ausente.

## Fase C — API FastAPI

1. Criar router `backend/app/api/v1/routers/similarity.py`.
2. Expor endpoint:
   - `POST /v1/similarity/search`
3. Expor endpoint de saúde:
   - `GET /v1/similarity/health`
4. Mapear erros de validação e rate limit para respostas explícitas.

## Fase D — Serviço e repositório

1. Implementar service `search_similar_domains`.
2. Implementar repositório com estratégias:
   - typo/lexical,
   - fuzzy trigram,
   - vector ANN.
3. Implementar agregação e rank final por score composto.
4. Garantir resposta com `reasons` e sub-scores por item.

## Fase E — Operação e observabilidade

1. Instrumentar latência p50/p95 e volume de consultas.
2. Registrar logs estruturados (`query_domain`, `algorithms`, `result_count`).
3. Definir limites de rate por cliente/chave.

## Fase F — Validação técnica

1. Validar busca com domínios reais ingeridos em `com/net/org/br`.
2. Verificar precisão básica para casos de typosquatting comuns.
3. Verificar p95 abaixo da meta inicial em carga controlada.
4. Atualizar `.specs/todos/003/status.md` e `_registry.md`.

## Entregáveis

- Especificação de endpoint do `similarity-service` aprovada.
- Contrato versionado para implementação backend.
- Plano executável de implementação por fases.
- Critérios iniciais de performance e observabilidade.
