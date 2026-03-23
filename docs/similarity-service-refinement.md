# Similarity Service — Refinamento Técnico

## Objetivo

Definir o microserviço `similarity-service` responsável por busca de similaridade de domínios, usando apenas dados já ingeridos no banco, com baixa latência e isolamento de carga em relação ao enriquecimento.

## Boundary de domínio

- **Domínio:** monitoring
- **Subdomínio:** domain-similarity
- **Responsabilidade primária:** consulta read-heavy por candidatos semelhantes a um domínio de entrada.
- **Fora de escopo:** ingestão CZDS, execução de enrichment, publicação em fila.

## Endpoint principal

- **Método/rota:** `POST /v1/similarity/search`
- **Motivo do POST:** filtros compostos e opções de algoritmo não triviais para query string.

### Request

```json
{
  "query_domain": "g00gle.com",
  "algorithms": ["hybrid"],
  "min_score": 0.72,
  "max_results": 50,
  "include_deleted": false,
  "tld_allowlist": ["com", "net", "org", "br"],
  "sources": ["czds"],
  "offset": 0
}
```

### Regras de validação

- `query_domain` obrigatório, formato FQDN válido e normalizado para lowercase/punycode.
- `algorithms` permitido: `fuzzy`, `typo`, `vector`, `hybrid`.
- `hybrid` executa combinação ponderada (fuzzy + typo + vector).
- `min_score` intervalo `[0.0, 1.0]`.
- `max_results` intervalo `[1, 200]`.
- `offset` mínimo `0`.

### Response 200

```json
{
  "query": {
    "domain": "g00gle.com",
    "normalized": "g00gle.com",
    "algorithms": ["hybrid"],
    "min_score": 0.72
  },
  "pagination": {
    "offset": 0,
    "limit": 50,
    "returned": 3,
    "has_more": false
  },
  "results": [
    {
      "domain": "google.com",
      "tld": "com",
      "source": "czds",
      "status": "active",
      "score": 0.96,
      "scores": {
        "fuzzy": 0.91,
        "typo": 0.98,
        "vector": 0.99
      },
      "reasons": ["keyboard_substitution", "high_lexical_similarity"],
      "observed_at": "2026-02-28T10:20:00Z"
    }
  ]
}
```

### Ordenação

1. `score DESC`
2. `observed_at DESC`
3. `domain ASC`

### Códigos de erro

- `400`: payload inválido (`invalid_request`).
- `422`: domínio não normalizável (`invalid_domain`).
- `429`: limite de taxa do serviço (`rate_limited`).
- `500`: erro interno (`internal_error`).

## Endpoint complementar (opcional, diagnóstico)

- `GET /v1/similarity/health`
- Retorna status, versão e latência média da busca (janela curta).

## Modelo de score (v1)

Para `hybrid`, calcular:

$$
score_{final} = 0.45 \cdot typo + 0.35 \cdot fuzzy + 0.20 \cdot vector
$$

- Ajustável por configuração de serviço.
- Filtrar por `score_final >= min_score`.

## Persistência e índices (PostgreSQL + pgvector)

Tabela `domain` (ou tabela especializada de leitura) deve suportar:

- `domain_name` normalizado (`citext` ou `text` + normalização consistente)
- `tld`
- `source` (`czds`)
- `status` (`active`, `deleted`, etc.)
- `deleted_at`
- `embedding vector(384)`

Índices recomendados:

- B-tree: `(tld, status, source)`
- Trigram (`pg_trgm`) em `domain_name` para fuzzy
- Vetorial (`ivfflat` ou `hnsw`) em `embedding`

## Dependências entre serviços

- O `similarity-service` **não** chama RDAP/WHOIS diretamente.
- Usa somente dados persistidos por ingestores e `enrichment-worker`.
- `enrichment-worker` segue assíncrono via fila (`DomainNeedsEnrichment`).

## SLO inicial

- p95 `< 250ms` com dataset de até 10M domínios.
- disponibilidade mensal alvo `99.5%`.
