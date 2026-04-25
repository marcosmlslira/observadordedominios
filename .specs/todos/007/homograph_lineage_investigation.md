# Investigação de Lineage: Google / PayPal Homograph em Produção

Data: 2026-04-17

## Escopo

Objetivo desta investigação:

1. cadastrar brands reais de teste em produção
2. acompanhar o fluxo completo de busca de ameaças
3. verificar se domínios com caracteres cirílicos/grecos entram como ameaça
4. identificar, ponto a ponto, onde esses domínios ficam represados no pipeline atual

Brands de teste criadas em produção:

- Google: `795504f1-aaab-4be6-91c7-6df5fb2c3244`
- PayPal: `acc3c273-4181-4d12-a558-ab6652b7e384`

Domínios reais confirmados na base global `.com`:

- `xn--gogle-jye.com` -> `g\u043eogle` (`о` cirílico)
- `xn--gogle-rce.com` -> `g\u03bfogle` (`ο` grego)
- `xn--pypal-4ve.com` -> `p\u0430ypal` (`а` cirílico)

## Resultado do teste em produção

Os domínios acima existem na base global, mas não apareceram como ameaça para as brands de teste.

Evidência observada:

1. `/v1/brands/{brand_id}/matches` permaneceu com `total = 0`
2. consulta direta em `similarity_match` para os `brand_id + domain_name` retornou `0` linhas
3. o job de `google.com` ficou longamente em `running` na TLD `.com`, sem materializar candidatos nem matches
4. o job de `paypal.com` permaneceu em `queued`, aguardando o worker liberar a fila

## Lineage do pipeline atual

## 1. Cadastro da brand

No cadastro da brand, o backend cria o perfil de monitoramento e gera seeds determinísticas.

Arquivos envolvidos:

- `backend/app/api/v1/routers/monitored_brands.py`
- `backend/app/services/use_cases/sync_monitoring_profile.py`
- `backend/app/services/seed_generation.py`

Comportamento observado na produção:

Para `google.com`, os `homograph_base` gerados em produção são ASCII:

- `gogle`
- `go0gle`
- `goog1e`
- `googl`
- `googe`

Para `paypal.com`, os `homograph_base` gerados em produção também são ASCII:

- `pypal`
- `paypl`
- `aypal`
- `payal`
- `papal`
- `paypa1`
- `p4ypal`

Isso prova que a produção atual não está gerando `xn--...` para homograph Unicode.

## 2. Primeiro ponto de represamento: geração de seeds

Arquivo produtivo confirmado via `docker exec`:

- `app/services/seed_generation.py`

Trecho relevante da produção:

- `_add()` sempre passa por `normalize_brand_text(seed_value)`
- no bloco de `homograph_base`, a variante Unicode é enviada diretamente para `_add()`

Efeito:

1. a variante Unicode confusable é reduzida para ASCII sanitizado
2. o punycode real não é preservado
3. `brаdesco` vira algo como `bradesco`, `gοogle` vira `gogle`, `pаypal` vira `pypal`

Impacto direto nos três domínios testados:

- `xn--gogle-jye.com`
- `xn--gogle-rce.com`
- `xn--pypal-4ve.com`

Nenhum deles entra no Ring A por igualdade, porque a brand não possui seeds `xn--gogle-jye`, `xn--gogle-rce` ou `xn--pypal-4ve`.

## 3. Ring A: exact lookup falha antes de começar

Arquivo produtivo confirmado:

- `app/services/use_cases/run_similarity_scan.py`

Ring A usa:

- `fetch_candidates_exact(candidate_labels=exact_labels, ...)`

Como `exact_labels` na produção contém apenas seeds ASCII, o lookup exato nunca procura os punycodes reais.

Consequência:

- `xn--gogle-jye.com` não é sequer candidato no Ring A
- `xn--gogle-rce.com` não é sequer candidato no Ring A
- `xn--pypal-4ve.com` não é sequer candidato no Ring A

## 4. Ring B: fuzzy também nasce enviesado para ASCII

Arquivos produtivos confirmados:

- `app/services/use_cases/run_similarity_scan.py`
- `app/services/use_cases/compute_similarity.py`

No pipeline produtivo:

1. Ring B usa `generate_typo_candidates(seed.seed_value)`
2. `generate_typo_candidates()` devolve variantes com confusable Unicode, mas sem converter para IDNA punycode
3. o banco global armazena o label em ASCII/punycode (`xn--...`)

Efeito:

- variantes Unicode geradas em memória não casam por igualdade com o formato persistido no banco
- para o caminho fuzzy, o label persistido `xn--gogle-jye` ainda é comparado contra `google` como texto bruto, não como Unicode decodificado

Consequência prática:

o Ring B fica dependente de trigram/Levenshtein entre:

- `xn--gogle-jye` vs `google`
- `xn--gogle-rce` vs `google`
- `xn--pypal-4ve` vs `paypal`

Isso é lexicalmente fraco demais.

## 5. Ring C: encontra punycode, mas pontua o punycode bruto

Arquivos produtivos confirmados:

- `app/repositories/similarity_repository.py`
- `app/services/use_cases/compute_similarity.py`
- `app/services/use_cases/run_similarity_scan.py`

Comportamento do Ring C em produção:

1. `fetch_candidates_punycode()` faz `label LIKE 'xn--%'`
2. calcula `similarity(label, :brand_label)` e `levenshtein(label, :brand_label)` sobre o valor bruto do label
3. retorna no máximo `300` linhas por TLD
4. `compute_scores()` também trabalha com o label bruto recebido, sem `decode_idna_label()`

Efeito:

- `xn--gogle-jye` é comparado com `google`, não com `gоogle`
- `xn--gogle-rce` é comparado com `google`, não com `gοogle`
- `xn--pypal-4ve` é comparado com `paypal`, não com `pаypal`

Isso derruba:

- `score_trigram`
- `score_levenshtein`
- `score_brand_hit`

Mesmo que `normalize_homograph()` exista, ela é aplicada em cima do punycode bruto, não da forma Unicode visual.

Resultado:

- o sinal real de homograph não é recuperado
- o domínio tende a cair como ruído lexical ou nem passar do threshold

## 6. Quarto ponto de represamento: limite fixo de 300 no Ring C

Arquivo produtivo confirmado:

- `app/repositories/similarity_repository.py`

Na produção atual:

- `fetch_candidates_punycode(..., limit=300)`

Sem ordenação útil por proximidade à marca.

Impacto:

Mesmo que o Ring C fosse conceitualmente correto, ele ainda estaria amostrando um subconjunto arbitrário de `xn--...` em `.com`.

Isso cria duas falhas independentes:

1. pode não trazer o domínio certo para scoring
2. se trouxer, o scoring ainda está errado porque usa o punycode bruto

## 7. Evidência operacional do worker

Logs observados do `observador_scan_worker`:

- job do Google entrou em `running`
- TLD `.com` iniciou scan
- o worker permaneceu vários minutos preso nessa execução
- o scheduler passou a logar `maximum number of running instances reached (1)`

Interpretação:

- a varredura da `.com` é pesada
- o scan ocupa o worker por muito tempo
- enquanto isso, o `paypal.com` fica represado em fila

Isso não é a causa raiz da não detecção, mas piora a observabilidade e o tempo de validação.

## Conclusão: onde os domínios ficam represados

Para os domínios:

- `xn--gogle-jye.com`
- `xn--gogle-rce.com`
- `xn--pypal-4ve.com`

os bloqueios acontecem nesta ordem:

1. Seed generation
- o sistema gera `homograph_base` ASCII em vez de punycode real
- esses domínios já ficam fora do Ring A

2. Fuzzy candidate generation
- as variantes Unicode não são convertidas para o formato persistido na base
- o Ring B continua enviesado para ASCII

3. Punycode scoring
- quando o Ring C encontra `xn--...`, ele pontua o label bruto
- não decodifica para Unicode antes de aplicar homograph/brand match

4. Ring C sampling
- o `LIMIT 300` em `.com` pode nem trazer o domínio certo

5. Worker throughput
- a TLD `.com` pode segurar o worker por vários minutos
- jobs seguintes ficam represados em fila

## Estado dos testes locais após a correção

O código local corrigido já cobre o comportamento esperado desses casos.

Testes adicionados:

- `xn--gogle-jye` deve detectar `homograph_attack` para `google`
- `xn--gogle-rce` deve detectar `homograph_attack` para `google`
- `xn--pypal-4ve` deve detectar `homograph_attack` para `paypal`
- a geração de seeds deve emitir esses punycodes reais

## Veredito

Na produção atual, os domínios com cirílico/grego não entram como ameaça para essas brands porque:

1. a seed gerada está errada
2. o scoring de punycode está errado
3. a busca do Ring C ainda é curta e arbitrária para `.com`

Ou seja, o problema não está na inexistência dos domínios na base global.

O problema está no pipeline produtivo atual de recuperação e classificação.
