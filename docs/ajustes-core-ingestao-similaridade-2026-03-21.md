# Ajustes do Core de Ingestao e Similaridade

Data: 2026-03-21

## Escopo executado

Foram implementados os ajustes pedidos nos pontos 3, 4 e 5 da reavaliacao do core:

1. recalibracao do motor de similaridade;
2. implementacao do contrato de busca sincrona de similaridade;
3. recuperacao automatica de `ingestion_run` preso em `running`;
4. reprocessamento real de marcas para limpar ruido ja persistido.

## Decisao sobre subdominios

Nao foi adotada a estrategia de "descartar o dado". A decisao implementada foi:

- manter o corpus ingerido como esta, inclusive com labels que representam hostnames/subdominios;
- retirar esse tipo de item do stream principal de `similarity_match`, que e o fluxo de alerta/triagem;
- expor a analise segmentada via `POST /v1/similarity/search` com o campo `include_subdomains`.

Na pratica:

- o monitoramento principal fica muito mais preciso;
- a investigacao manual continua possivel quando fizer sentido explorar hostnames enganosos.

## Decisao sobre `domain_observation`

A decisao documentada de **nao popular `domain_observation` para fontes snapshot como CZDS faz sentido**.

Base documental revisada:

- `docs/domain-table-redesign-proposal.md`
- `docs/czds-ingestion-optimization-study.md`

Motivo:

- append-only por dominio por execucao explode custo de storage de forma insustentavel;
- para snapshot, o trilho operacional ja existe em `domain.first_seen_at`, `domain.last_seen_at`, `ingestion_run` e artefato bruto em storage.

O problema real nao era a decisao em si; era a falta de aderencia entre documentos antigos, o PRD original e residuos de implementacao.

## Mudancas implementadas

### Similaridade

- `compute_similarity.py`
  - match exato passou a gerar `exact_label_match` e risco `high`, nao `critical`;
  - `brand_hit` virou boundary-aware para evitar casos como `authority` acionando `itau`;
  - keywords curtas deixaram de usar substring cega;
  - `typosquatting` e `homograph_attack` ficaram mais restritivos.
- `run_similarity_scan.py`
  - `SCORE_THRESHOLD` elevado para `0.40`;
  - suporte a `force_full`;
  - reconciliacao do conjunto persistido por `brand/tld`;
  - limpeza automatica de matches antigos desqualificados;
  - remocao automatica de matches com `label` contendo `.`.
- `similarity_repository.py`
  - candidatos de scan e busca sincrona excluem subdominios por padrao;
  - novos metodos para reconciliar e remover matches antigos.

### API de busca

Implementado:

- `POST /v1/similarity/search`
- `GET /v1/similarity/health`

Capacidades:

- normalizacao de `query_domain`;
- filtros por algoritmo, `min_score`, `offset`, `tld_allowlist`, `sources`;
- extensao pragmatica `include_subdomains`;
- telemetria simples de latencia;
- exposicao explicita de `vector_enabled=false` no health atual.

Observacao:

- o contrato HTTP foi implementado;
- busca vetorial continua desabilitada nesta stack atual, por isso `vector_enabled=false`.

### Ingestao CZDS

- `ingestion_run_repository.py`
  - novo recovery automatico para runs `running` acima do timeout configurado.
- `config.py`
  - novo `CZDS_RUNNING_STALE_MINUTES`.
- `czds_ingestion.py` e `sync_czds_tld.py`
  - recovery executado antes do bloqueio por `has_running_run`.

## Validacao executada

### Testes automatizados

Executado com sucesso:

`python -m pytest -vv -s backend/tests/test_compute_similarity.py backend/tests/test_similarity_search_api.py backend/tests/test_czds_trigger_sync.py`

Resultado:

- 6 testes passando.

### Runtime real em `localhost:8005`

Validado:

- `GET /health` -> `200`
- `GET /v1/similarity/health` -> `200`
- `POST /v1/similarity/search` -> `200`

Resposta observada para `google.com`:

- retornou matches como `google.info`, `google.net`, `google.org`;
- todos com `reasons=["exact_label_match"]`;
- todos com `risk_level="high"`.

### Recovery do `org` preso

Estado anterior:

- run `26237990-66d1-4a58-8288-aa9204755a87`
- `tld=org`
- `status=running`
- iniciada em `2026-03-21T07:36:10Z`

Estado apos ajuste:

- a run acima foi marcada automaticamente como `failed` em `2026-03-22T02:53:39Z`;
- mensagem gravada: timeout automatico por stale run;
- uma nova run legitima de `org` foi aberta pelo worker: `12e5e672-8218-4600-839a-d13a93044ff9`.

Conclusao:

- o `409` atual no trigger manual de `org` ja nao e por run orfa;
- o `409` agora e legitimo, porque existe uma execucao nova e real em andamento.

### Rebuild real dos matches

Executado:

- `POST /v1/brands/d23a55d4-414b-4df4-b4ac-fb42d37a6213/scan?force_full=true`
- `POST /v1/brands/cecd5e61-2f43-4ef4-846e-ed1dedcda0ee/scan?force_full=true`

Resultados observados nos logs:

- Itau / `net`: `matched=77`, `removed=381`
- Itau / `org`: `matched=59`, `removed=364`
- Itau / `info`: `matched=39`, `removed=157`
- Google / `net`: `matched=1873`, `removed=605`
- Google / `org`: `matched=1521`, `removed=549`
- Google / `info`: `matched=724`, `removed=206`

### Checagem final no banco

Consulta validada apos os rescans:

- `google`: `subdomains=0`, `critical_below_05=0`, `total=4118`
- `itau`: `subdomains=0`, `critical_below_05=0`, `total=175`

Falsos positivos antigos removidos:

- `ns1.ads-google.net` -> nao existe mais em `similarity_match`
- `ns.google0.org` -> nao existe mais em `similarity_match`

Casos de fronteira:

- `itauthority.net` e `itauthority.info` continuam aparecendo, mas agora como `low` com `score_final=0.4196`
- `mckinneyavenuetransitauthority.org` nao permaneceu no conjunto final de matches de `Itau`

## Leitura executiva

O core ficou mais aderente em tres pontos que mudam resultado real:

- o fluxo principal de alertas deixou de ser contaminado por subdominios/hostnames;
- o score deixou de classificar match exato como `critical/typosquatting`;
- o bloqueio operacional por `running` orfao deixou de travar indefinidamente um TLD.

## Proximo passo recomendado

Se quiser endurecer ainda mais o caso `itauthority.*`, o proximo ajuste natural e criar uma regra separando:

- `brand_prefix_suffix_only`
- `embedded_brand_inside_long_token`

Hoje esses casos ja nao escalam para `critical`, mas ainda entram como `low` quando o brand aparece de forma literal.
