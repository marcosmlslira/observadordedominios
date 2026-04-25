# Relatório de Implementação: Homograph / IDN

Data: 2026-04-17

## Objetivo

Este relatório descreve o que foi implementado após a revisão técnica de homograph/IDN no escopo do todo `007`, com foco em:

- corrigir a recuperação de domínios homograph reais usando punycode
- corrigir o scoring de domínios `xn--...`
- estender a mesma lógica para a busca síncrona
- adicionar telemetria mínima para validação do `Ring C`

## Resumo executivo

Foram implementadas correções estruturais no backend para que o pipeline deixe de tratar homograph Unicode apenas como similaridade lexical comum.

O resultado prático é:

1. seeds de homograph agora geram valores de lookup em punycode reais
2. o scoring agora decodifica `xn--...` antes de comparar com a marca
3. a busca síncrona também passou a buscar e avaliar candidatos punycode
4. o fluxo de scan agora expõe telemetria do `Ring C`
5. o endpoint de regeneração de seeds passou a respeitar `include_llm`

## Escopo implementado

## 1. Correção da geração de seeds `homograph_base`

Arquivo:

- `backend/app/services/seed_generation.py`

Implementação:

1. passou a importar `encode_idna_label`
2. `homograph_base` agora ignora substituições ASCII simples
3. variantes Unicode confusable são convertidas para punycode antes de virarem seed
4. essas seeds deixam de passar pela sanitização que removeria `xn--`

Efeito:

- `bradesco` agora gera seeds como `xn--brdesco-3fg`
- `Ring A` passa a conseguir fazer lookup exato no formato real da base

## 2. Correção do pipeline de typo/homograph candidate generation

Arquivo:

- `backend/app/services/use_cases/compute_similarity.py`

Implementação:

1. adicionado `encode_idna_label()`
2. adicionado `decode_idna_label()`
3. `generate_typo_candidates()` agora converte variantes Unicode para punycode

Efeito:

- o fluxo de candidatos usado no Ring B deixa de gerar variantes Unicode impossíveis de recuperar na base
- variantes homograph com confusables passam a ser emitidas no formato armazenado em `domain.label`

## 3. Correção do scoring para labels `xn--...`

Arquivo:

- `backend/app/services/use_cases/compute_similarity.py`

Implementação:

1. `compute_scores()` agora decodifica punycode via `decode_idna_label()`
2. o cálculo usa:
   - label decodificado
   - label normalizado por confusables
   - marca normalizada por confusables
3. `brand containment` passou a usar a forma normalizada
4. `keyword risk` passou a operar sobre a forma normalizada
5. `score_homograph` passou a refletir a forma visual real do domínio
6. `_classify_seeded_risk()` agora promove melhor casos com `homograph_attack`

Efeito:

- `xn--brdesco-3fg` deixa de cair como mera similaridade lexical
- esse caso passa a gerar `homograph_attack`
- o `score_final` sobe acima do threshold padrão no fluxo seeded

## 4. Extensão do Ring C no scan assíncrono

Arquivos:

- `backend/app/repositories/similarity_repository.py`
- `backend/app/services/use_cases/run_similarity_scan.py`

Implementação:

1. `fetch_candidates_punycode()` passou de `limit=300` para `limit=1200`
2. a query passou a ter ordenação estável por recência/nome
3. o scan por TLD passou a usar limites diferenciados por TLD:
   - `com = 2000`
   - `net = 1500`
   - `org = 1500`
   - `com.br = 1200`
   - default = 1200

Efeito:

- melhora de recall do `Ring C`
- menor arbitrariedade na amostragem de candidatos `xn--`

## 5. Telemetria do Ring C no scan

Arquivos:

- `backend/app/services/use_cases/run_similarity_scan.py`
- `backend/app/repositories/similarity_repository.py`
- `backend/app/services/similarity_scan_jobs.py`
- `backend/app/schemas/similarity.py`

Implementação:

1. `_process_candidate()` passou a retornar se o candidato passou do threshold
2. `run_similarity_scan()` agora coleta:
   - `ring_c_candidates`
   - `ring_c_matches`
   - `ring_c_limit`
3. `update_scan_job_tld()` passou a aceitar `extra_metrics`
4. `create_scan_job()` inicializa os campos de telemetria
5. `ScanResultResponse` agora expõe:
   - `ring_c_candidates`
   - `ring_c_matches`
   - `ring_c_limit`
6. `serialize_scan_job()` passou a serializar esses campos

Efeito:

- agora dá para validar, por job e por TLD, se o Ring C realmente foi executado
- dá para comparar candidatos avaliados vs candidatos que viraram match

## 6. Extensão da busca síncrona (`/v1/similarity/search`)

Arquivos:

- `backend/app/repositories/similarity_repository.py`
- `backend/app/services/use_cases/search_similarity.py`
- `backend/app/schemas/similarity.py`

Implementação:

1. novo método `search_punycode_candidates()`
2. a busca síncrona agora faz:
   - busca lexical existente
   - busca punycode complementar
   - merge por domínio
   - score unificado usando o motor corrigido
3. adicionada telemetria na resposta:
   - `punycode_candidates_evaluated`
   - `punycode_candidates_matched`
   - `punycode_scan_enabled`
4. adicionada telemetria no endpoint de health:
   - `average_punycode_candidates_evaluated`
   - `punycode_search_samples`

Efeito:

- a busca síncrona agora também consegue retornar homograph em formato `xn--...`
- a validação não fica restrita ao worker assíncrono

## 7. Correção do parâmetro `include_llm`

Arquivos:

- `backend/app/services/use_cases/sync_monitoring_profile.py`
- `backend/app/api/v1/routers/monitored_brands.py`

Implementação:

1. `regenerate_seeds_for_brand()` agora recebe `run_llm`
2. o endpoint `/brands/{brand_id}/seeds/regenerate` passa `run_llm=include_llm`

Efeito:

- o contrato do endpoint agora reflete o comportamento real
- facilita validação deterministic-only vs deterministic+LLM

## Evidência funcional

Após a implementação:

### Seed generation

`generate_deterministic_seeds("bradesco", [], [])` passou a gerar:

```text
xn--brdesco-3fg
xn--brdesco-2lf
xn--bradsco-bhg
xn--bradsco-1mf
xn--bradeso-3jg
xn--bradesc-gjg
xn--bradesc-fpf
```

### Scoring base

`compute_scores(label="xn--brdesco-3fg", brand_label="bradesco", ...)` passou a retornar:

```text
score_final = 0.55
score_levenshtein = 1.0
score_brand_hit = 1.0
score_homograph = 1.0
reasons = ["brand_containment", "homograph_attack"]
risk_level = "medium"
```

### Scoring seeded

`compute_seeded_scores(...)` para o mesmo caso passou a retornar:

```text
score_final = 0.655
risk_level = "high"
reasons = ["brand_containment", "homograph_attack"]
```

Isso significa que o caso agora passa no threshold padrão do scan.

## Testes adicionados/ajustados

Arquivos:

- `backend/tests/test_homograph_detection.py`
- `backend/tests/test_similarity_search_api.py`
- `backend/tests/test_similarity_scan_jobs_api.py`

Cobertura adicionada:

1. seed punycode real para homograph
2. typo candidates com punycode confusable
3. `compute_scores()` com `xn--brdesco-3fg`
4. `compute_seeded_scores()` acima do threshold
5. busca síncrona retornando homograph punycode
6. endpoint de health com telemetria de punycode
7. job de scan serializando `ring_c_limit`
8. regeneração de seeds respeitando `include_llm`

## Resultado dos testes executados

Executado:

```text
pytest backend/tests/test_homograph_detection.py backend/tests/test_similarity_search_api.py backend/tests/test_similarity_scan_jobs_api.py backend/tests/test_monitoring_profile.py
```

Resultado:

```text
14 passed
```

## Migração de banco

Nenhuma migração Alembic foi necessária.

Motivo:

- a telemetria nova foi armazenada dentro de `tld_results` JSONB já existente
- a resposta síncrona usa apenas schema/API, sem alteração de tabela

## Como validar manualmente

## Validação 1: Preview de seeds

Para uma brand como `bradesco`, o preview/regeneração deve produzir seeds `homograph_base` em formato `xn--...`.

Esperado:

- não aparecerem seeds degradadas como `brdesco`
- aparecerem seeds punycode válidas

## Validação 2: Busca síncrona

Consultar:

- `/v1/similarity/search`

Com algo como:

- `query_domain = bradesco.com.br`

Esperado:

1. se existir um candidato `xn--...` correspondente na base, ele deve aparecer no resultado
2. `reasons` deve incluir `homograph_attack`
3. `telemetry.punycode_candidates_evaluated` deve ser maior que zero quando houver scan punycode

## Validação 3: Scan assíncrono

Disparar um scan manual da brand e inspecionar o job.

Esperado por TLD:

1. `ring_c_limit` preenchido
2. `ring_c_candidates >= 0`
3. `ring_c_matches >= 0`
4. quando houver `xn--...` relevantes, `ring_c_matches` deve refletir essa participação

## Limitações atuais

Ainda não foi implementado:

1. coluna derivada Unicode no corpus
2. explainability completa com label decodificado persistido no match
3. paginação específica e otimizada do Ring C para TLDs extremamente grandes

O que foi implementado resolve o principal problema funcional com o menor impacto estrutural, mas ainda existe espaço para uma versão posterior mais sofisticada.

## Conclusão

O backend agora passou a tratar homograph/IDN de forma coerente com o formato real da base global.

Antes:

- as seeds eram geradas em um formato incompatível
- o scoring lia punycode bruto
- a busca síncrona não fazia cobertura equivalente

Agora:

1. o lookup usa punycode real
2. o score entende a forma visual do domínio
3. o scan e a busca síncrona compartilham a mesma lógica essencial
4. existe telemetria suficiente para validar a cobertura do Ring C
