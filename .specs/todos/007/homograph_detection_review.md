# Revisão Técnica: Detecção de Homograph e IDN no escopo do Todo 007

Data: 2026-04-17

## Objetivo

Este relatório documenta os problemas identificados na implementação entregue no escopo do todo `007` para detecção de domínios com homograph attack na base global de domínios.

O foco aqui é responder, com base no código implementado, se o produto consegue detectar de forma confiável casos como:

- `bradesco` vs `brаdesco` com `а` cirílico
- marcas com caracteres gregos/cirílicos visualmente equivalentes
- domínios IDN que entram na base em formato punycode (`xn--...`)

## Resumo Executivo

O todo `007` melhorou a arquitetura do pipeline de busca ao introduzir:

- seed expansion determinística
- recuperação em anéis (`Ring A/B/C/D`)
- varredura específica para domínios `xn--`
- endpoints para preview/regeneração de seeds
- flags para pausar partes baseadas em LLM

O problema é que a implementação atual não fecha o ciclo de homograph de ponta a ponta.

Hoje, o sistema:

- encontra bem similaridade lexical, typo e combinações de marca + keyword
- possui estrutura para buscar IDN
- mas não detecta de forma confiável homograph real baseado em Unicode confusable

Em termos práticos: cadastrar uma marca como `bradesco` hoje **não é suficiente** para garantir retorno consistente de domínios homograph com caracteres cirílicos/grecos na base global.

## Escopo analisado

Arquivos principais revisados:

- `backend/app/services/seed_generation.py`
- `backend/app/services/monitoring_profile.py`
- `backend/app/services/use_cases/run_similarity_scan.py`
- `backend/app/repositories/similarity_repository.py`
- `backend/app/services/use_cases/compute_similarity.py`
- `backend/app/services/domain_normalizer.py`
- `backend/app/repositories/domain_repository.py`
- `backend/app/api/v1/routers/monitored_brands.py`
- `backend/app/services/use_cases/sync_monitoring_profile.py`

## O que o 007 implementou

### 1. Expansão determinística de seeds

Implementado em `backend/app/services/seed_generation.py`.

Novas famílias:

- `typo_base`
- `homograph_base`
- `combo_brand_keyword`
- `combo_keyword_brand`

### 2. Estratégia de busca por anéis

Implementado em `backend/app/services/use_cases/run_similarity_scan.py`.

- `Ring A`: lookup exato para `typo_base` / `homograph_base`
- `Ring B`: fuzzy/trigram para seeds tradicionais
- `Ring C`: scan de labels `xn--`
- `Ring D`: lookup exato para combos

### 3. Integração com criação/atualização/regeneração de brands

Implementado em `backend/app/services/use_cases/sync_monitoring_profile.py`.

### 4. Feature flags para LLM

Implementado em `backend/app/core/config.py` e workers relacionados.

Isso tudo está implementado. O problema está na coerência entre geração do seed, forma como a base armazena o label, e forma como o score é calculado para IDN.

## Achados

## 1. `homograph_base` não preserva homographs Unicode reais

### O que acontece

`generate_deterministic_seeds()` cria variantes usando `HOMOGRAPH_REVERSE`, mas toda seed passa por `normalize_brand_text()` dentro de `_add()`.

Referências:

- `backend/app/services/seed_generation.py:62`
- `backend/app/services/seed_generation.py:130`
- `backend/app/services/monitoring_profile.py:72`

`normalize_brand_text()` remove qualquer caractere fora de `[a-z0-9]`.

Na prática, isso destrói caracteres cirílicos/grecos em vez de preservá-los.

### Exemplo concreto

Para `bradesco`, os `homograph_base` gerados localmente hoje são:

```text
8radesco
br4desco
brdesco
brad3sco
bradsco
brade5co
bradeco
bradeso
bradesc0
bradesc
```

Isso mostra que a seed de homograph virou uma mistura de:

- leetspeak
- deleções acidentais
- substituições ASCII

mas não uma representação fiel de homograph Unicode.

### Por que isso é problemático

O objetivo de `homograph_base` era criar uma família especializada para ataques visuais. Hoje ela não representa isso.

Ou seja, o nome da família sugere uma cobertura que o dado real não entrega.

### Impacto

- falso senso de cobertura para homograph
- falsos negativos para ataques com Unicode confusable
- `Ring A` perde utilidade para homograph real
- debugging fica enganoso, porque o sistema aparenta ter uma família especializada, mas ela não corresponde ao tipo de ameaça que deveria cobrir

### Sugestão de correção

Separar duas responsabilidades que hoje estão misturadas:

1. `seed_value_display`
   - versão semântica da seed, podendo conter Unicode confusable
2. `seed_lookup_value`
   - versão usada para query no banco

Para `homograph_base`, a recomendação é:

1. preservar a variante Unicode gerada
2. converter essa variante para punycode quando o alvo da busca for a tabela `domain`
3. persistir o punycode como valor de lookup exato
4. usar a forma Unicode apenas para explicação/auditoria e eventualmente scoring

Se não quiser introduzir dois campos agora, a alternativa mínima aceitável é:

1. não usar `normalize_brand_text()` para `homograph_base`
2. gerar diretamente a forma punycode dessa seed e persisti-la como `seed_value`

## 1b. O Ring B também falha para homograph Unicode (mesmo problema estrutural)

### O que acontece

`generate_typo_candidates()` em `compute_similarity.py:109-112` já gera variantes homograph via `HOMOGRAPH_REVERSE` como parte das suas substituições. Essas variantes são usadas no Ring B para busca fuzzy via trigram no SQL.

Porém, os labels na base estão em ASCII/punycode. Uma variante Unicode gerada por `generate_typo_candidates()` (ex: `brаdesco` com `а` cirílico) nunca terá trigram match útil contra `xn--brdesco-3fg` armazenado na base.

### Impacto

- o Ring B, assim como o Ring A, é estruturalmente incapaz de recuperar homograph Unicode
- a cobertura do `generate_typo_candidates()` para confusables Unicode é ilusória — os candidatos são gerados mas nunca encontram match

### Relação com os outros achados

Este é o mesmo problema estrutural do Achado 1 e 2: formato da seed (Unicode) vs formato do storage (ASCII/punycode). Corrigir o Achado 1 (gerar seeds em punycode) resolve este ponto automaticamente, desde que `generate_typo_candidates()` também passe a gerar variantes punycode quando lida com confusables.

## 2. Há incompatibilidade estrutural entre o desenho do `Ring A` e o formato real da base global

### O que acontece

A base global armazena `domain.label` apenas em ASCII.

Isso é visível na ingestão:

- `backend/app/services/domain_normalizer.py:22`
- `backend/app/services/domain_normalizer.py:146`
- `backend/app/repositories/domain_repository.py:210`

O normalizador de domínio aceita labels que respeitam regex ASCII. Para IDN, o caminho prático é armazenar o label em punycode (`xn--...`), não em Unicode decodificado.

### Por que isso é problemático

Mesmo que `homograph_base` preservasse Unicode corretamente, o `Ring A` faz lookup exato em `domain.label`.

Se `domain.label` estiver em punycode, e a seed estiver em Unicode, nunca haverá igualdade exata.

Portanto, hoje existe um desalinhamento entre:

- o formato da seed
- o formato do armazenamento
- a estratégia de busca exata

### Impacto

- `Ring A` não consegue cumprir o papel prometido para homograph Unicode
- qualquer correção parcial na geração da seed ainda falhará se não corrigir o formato de lookup
- risco de futuras correções superficiais que "parecem" resolver, mas continuam sem fechar a recuperação

### Sugestão de correção

Escolher explicitamente uma das duas arquiteturas abaixo:

### Opção A: manter a base em punycode e adaptar o pipeline

1. armazenar `domain.label` como está hoje
2. gerar `homograph_base` já em punycode para lookup
3. decodificar punycode apenas na etapa de scoring e apresentação

Vantagem:

- menor impacto estrutural
- menor custo de migração

### Opção B: adicionar coluna derivada para label Unicode decodificado

1. manter `label` atual
2. adicionar `label_unicode` ou `label_idna_decoded`
3. consultar e pontuar usando essa coluna nos fluxos de homograph

Vantagem:

- modelo conceitualmente mais limpo
- facilita score, auditoria e explainability

Para curto prazo, a Opção A é a mais pragmática.

## 3. O `Ring C` busca punycode, mas pontua o punycode bruto

### O que acontece

`fetch_candidates_punycode()` recupera labels com prefixo `xn--`:

- `backend/app/repositories/similarity_repository.py:273`

Depois esses candidatos são enviados para `_process_candidate()`, que chama `compute_seeded_scores()` com o `label` ainda em punycode:

- `backend/app/services/use_cases/run_similarity_scan.py:308`
- `backend/app/services/use_cases/run_similarity_scan.py:326`
- `backend/app/services/use_cases/compute_similarity.py:239`

`compute_scores()` compara esse `label` com a marca ASCII sem decodificar IDNA antes.

### Exemplo concreto

`brаdesco` com `а` cirílico vira:

```text
xn--brdesco-3fg
```

No cálculo atual, esse caso resultou localmente em:

```text
score_final = 0.368
risk_level = low
reasons = ['lexical_similarity']
```

Ou seja, um homograph clássico não chega nem perto de ser classificado como `homograph_attack`.

### Por que isso é problemático

O `Ring C` foi introduzido justamente para capturar IDN homograph.

Se a pontuação tratar `xn--brdesco-3fg` como texto literal, o motor perde o sinal visual do ataque.

O pipeline até encontra candidatos `xn--`, mas não entende o que eles significam.

### Impacto

- falso negativo em homographs reais
- `Ring C` passa a ser muito menos efetivo do que o desenho do 007 sugere
- casos mais perigosos continuam caindo como `lexical_similarity`
- marcas críticas podem parecer “protegidas” quando não estão

### Sugestão de correção

Antes de chamar `compute_seeded_scores()`:

1. detectar se o label começa com `xn--`
2. reconstruir o label Unicode com `idna.decode()`
3. calcular score sobre a forma decodificada
4. opcionalmente manter as duas formas:
   - `label_raw = xn--...`
   - `label_decoded = brаdesco`

Depois, em `compute_scores()`:

1. aplicar `normalize_homograph()` no label decodificado
2. comparar o resultado com a marca ASCII normalizada

Isso faz o score refletir a intenção visual do domínio, não a codificação técnica usada no DNS.

### Nota de implementação: `idna.decode()` pode falhar

Nem todo label com prefixo `xn--` é um punycode válido. Labels malformados, truncados ou registrados intencionalmente com prefixo `xn--` sem ser IDNA legítimo causarão exceção em `idna.decode()`.

A implementação deve:

1. envolver `idna.decode()` em try/except
2. em caso de falha, manter o label raw e pontuar normalmente (sem boost de homograph)
3. registrar o erro em log para auditoria

## 3b. O `HOMOGRAPH_MAP` é insuficiente para cobertura real em produção

### O que acontece

O mapa de confusables em `compute_similarity.py:17-38` contém ~20 entradas: leet speak, alguns cirílicos, alguns gregos e poucos visuais (`ı`, `ł`).

O Unicode Confusables database oficial do Unicode Consortium (`confusables.txt`) contém **milhares** de mapeamentos. Exemplos de confusables comuns que estão ausentes:

- `ɑ` (U+0251, Latin alpha) → `a`
- `ꮪ` (U+ABA) → `s` (Cherokee)
- `ℯ` (U+212F, script e) → `e`
- `ⅰ` (U+2170, Roman numeral) → `i`
- `Ꭱ` (U+AB31, Cherokee) → visual similar a vários ASCII
- dezenas de variantes de `o`, `a`, `e`, `i`, `l` em blocos Armenian, Georgian, Cherokee, etc.

### Impacto

Mesmo com todas as correções dos achados 1-3 implementadas, a cobertura de confusables ficará limitada ao subconjunto pequeno do mapa atual. Atacantes mais sofisticados usam caracteres de blocos menos óbvios (Cherokee, Armenian, Georgian) que não estão mapeados.

Para a filosofia de recall alto no balde inicial, isso limita a capacidade de gerar seeds abrangentes e de pontuar corretamente labels decodificados que usam confusables fora do mapa.

### Sugestão de correção

Fase 2 — após corrigir o pipeline mínimo:

1. importar ou gerar o mapa a partir do `confusables.txt` oficial do Unicode Consortium
2. filtrar para os subsets relevantes (Latin confusables — mapeamentos que resultam em caracteres `[a-z0-9]`)
3. expandir `HOMOGRAPH_MAP` e `HOMOGRAPH_REVERSE` com esse dataset
4. manter o mapa atual como subset garantido e adicionar os novos como extensão

Alternativamente, usar a biblioteca `confusable_homoglyphs` do PyPI que já encapsula o dataset oficial.

## 4. O `Ring C` tem recall limitado por `LIMIT 300` sem ordenação semântica

### O que acontece

A query de punycode faz:

- filtro por `label LIKE 'xn--%'`
- `LIMIT 300`
- sem `ORDER BY`

Referência:

- `backend/app/repositories/similarity_repository.py:290`

### Por que isso é problemático

Em TLDs grandes, pode haver muitos labels `xn--`.

Sem ordenação por um critério relevante, o banco pode devolver uma amostra arbitrária. O domínio correto pode simplesmente não entrar no lote avaliado.

### Impacto

- perda de recall em `.com`, `.net`, `.org` e outros TLDs grandes
- comportamento inconsistente entre execuções
- dificuldade de explicar por que um domínio óbvio não foi avaliado

### Sugestão de correção

Trocar a estratégia de coleta do `Ring C`.

Caminhos possíveis:

1. buscar em lotes paginados até um teto por TLD
2. usar um pré-filtro por comprimento/proximidade com a marca
3. ordenar por uma heurística minimamente útil
4. se houver `label_decoded`, ordenar por similaridade sobre a forma decodificada

A correção mínima:

1. remover a amostra arbitrária
2. aplicar pelo menos batching estável
3. registrar quantos `xn--` existiam no TLD e quantos foram efetivamente avaliados

### Observação adicional: combinar Ring C genérico com lookup dirigido

A abordagem de "scan genérico de todos os `xn--`" é inerentemente frágil porque depende de amostragem. Se o Achado 1 for corrigido e seeds punycode forem geradas, o Ring A passa a capturar os homographs **conhecidos** por exact match — o que é determinístico e performante.

Nesse cenário, o Ring C pode ser reduzido a um papel complementar: capturar variantes **inesperadas** que não foram antecipadas pelas seeds. Para esse papel, filtros adicionais são mais úteis que aumentar o LIMIT:

1. filtrar por comprimento similar ao da marca em punycode: `WHERE LENGTH(label) BETWEEN LENGTH(:brand_punycode) - 3 AND LENGTH(:brand_punycode) + 5`
2. ou usar `similarity(label, :brand_punycode) > 0.15` como pré-filtro leve no SQL antes de trazer os candidatos

A combinação das duas abordagens (exact match para homographs conhecidos via Ring A + scan filtrado para variantes inesperadas via Ring C) é mais robusta e confiável do que depender apenas do scan genérico.

## 5. A API de regeneração expõe `include_llm`, mas hoje ignora esse controle

### O que acontece

O endpoint:

- `backend/app/api/v1/routers/monitored_brands.py:436`

recebe `include_llm`, mas chama:

- `regenerate_seeds_for_brand(repo, brand)`

sem propagar esse parâmetro.

E `regenerate_seeds_for_brand()` força `run_llm=True`:

- `backend/app/services/use_cases/sync_monitoring_profile.py:149`
- `backend/app/services/use_cases/sync_monitoring_profile.py:168`

### Por que isso é problemático

O contrato da API sugere um controle operacional que não existe de verdade.

Isso não quebra diretamente homograph, mas afeta previsibilidade e dificulta operação/debug do pipeline de seeds.

### Impacto

- comportamento inconsistente com a documentação/contrato
- dificuldade de comparar deterministic-only vs deterministic+LLM
- troubleshooting mais caro

### Sugestão de correção

Propagar `include_llm` do endpoint até `_apply_profile_components()`:

1. adicionar parâmetro explícito em `regenerate_seeds_for_brand()`
2. passar `run_llm=include_llm`
3. manter a flag global `SEED_LLM_GENERATION_ENABLED` como segunda condição

## 6. Faltam testes para as partes críticas de homograph/IDN introduzidas no 007

### O que acontece

Os testes encontrados cobrem:

- helpers antigos de monitoring profile
- contrato de jobs de scan
- contrato da search API

Referências:

- `backend/tests/test_monitoring_profile.py`
- `backend/tests/test_similarity_scan_jobs_api.py`
- `backend/tests/test_similarity_search_api.py`

Não foi encontrada cobertura específica para:

- `generate_deterministic_seeds()`
- `homograph_base`
- `fetch_candidates_punycode()`
- `Ring C`
- regressão com `xn--...`
- preview/regeneração de seeds do 007

### Por que isso é problemático

Os problemas acima passaram justamente porque o fluxo novo não está protegido por teste focado no comportamento esperado.

### Impacto

- regressões silenciosas
- risco de corrigir um ponto e quebrar outro
- baixo nível de confiança para evoluir a detecção de homograph

### Sugestão de correção

Adicionar ao menos:

### Testes unitários

1. `generate_deterministic_seeds('bradesco', ...)` deve gerar representação válida para homograph
2. seeds `homograph_base` não podem ser degradadas por sanitização indevida
3. `compute_scores()` deve reconhecer homograph real ao receber label decodificado

### Testes de integração

1. candidato `xn--brdesco-3fg` deve ser classificado com sinal de homograph quando associado a `bradesco`
2. `Ring C` deve persistir match para esse caso
3. `/seeds/regenerate?include_llm=false` deve realmente impedir execução do bloco LLM

## Recomendação de implementação

## Ordem sugerida

### Fase 1: corrigir o pipeline mínimo para homograph real

1. corrigir geração de `homograph_base`
2. gerar lookup em punycode
3. decodificar `xn--` antes do score
4. adicionar testes unitários e integração para `bradesco -> xn--brdesco-3fg`

### Fase 2: melhorar recall e auditabilidade

1. revisar estratégia do `Ring C` — combinar lookup dirigido (Ring A com seeds punycode) + scan filtrado para variantes inesperadas
2. remover `LIMIT 300` arbitrário ou substituir por filtros de comprimento/similaridade mínima
3. expandir `HOMOGRAPH_MAP` com dataset do Unicode Confusables (`confusables.txt`) ou biblioteca `confusable_homoglyphs`
4. garantir que `generate_typo_candidates()` também gere variantes punycode quando lida com confusables
5. adicionar telemetria de cobertura do anel

### Fase 3: limpar inconsistências operacionais

1. corrigir `include_llm`
2. alinhar endpoint, serviço e documentação

## Critério de sucesso sugerido

O pipeline deve ser considerado correto para homograph quando, no mínimo:

1. uma marca ASCII como `bradesco` gerar mecanismo de lookup capaz de recuperar `xn--brdesco-3fg`
2. esse candidato, ao ser pontuado, produzir razão `homograph_attack` ou classificação equivalente de alto risco
3. o sistema conseguir explicar:
   - label bruto
   - label decodificado
   - seed usada
   - score homograph
   - motivo da classificação

## Conclusão

O todo `007` acertou a direção arquitetural, mas a implementação atual ainda não fecha a detecção de homograph real na base global.

Os pontos mais críticos são:

1. `homograph_base` hoje não representa Unicode confusable de forma útil — seeds são destruídas pela sanitização ASCII
2. o `Ring C` encontra punycode, mas o score trata punycode bruto como se fosse o domínio visual — perdendo o sinal do ataque
3. o Ring B também é afetado pelo mesmo desalinhamento de formato (Unicode seed vs ASCII storage)
4. o `HOMOGRAPH_MAP` atual cobre ~20 confusables quando o dataset Unicode oficial tem milhares — limitando a cobertura mesmo após as correções estruturais

Enquanto (1) e (2) não forem corrigidos, a cobertura de homograph para marcas como `bradesco` deve ser tratada como **parcial e não confiável para produção**. Os pontos (3) e (4) limitam o recall em cenários mais sofisticados e devem ser tratados em sequência.
