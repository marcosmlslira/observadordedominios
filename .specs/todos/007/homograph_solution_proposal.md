# Proposta de Solução: Detecção de Homograph Unicode em Produção

Data: 2026-04-17

## Objetivo

Esta proposta consolida a solução para o problema confirmado na produção atual:

1. domínios `xn--...` com caracteres cirílicos/grecos existem na base global
2. esses domínios não entram nas ameaças das brands monitoradas
3. o bloqueio acontece no pipeline de geração de seeds, recuperação de candidatos e scoring

Casos reais já confirmados na base:

- `xn--gogle-jye.com` -> `g\u043eogle`
- `xn--gogle-rce.com` -> `g\u03bfogle`
- `xn--pypal-4ve.com` -> `p\u0430ypal`

## Resumo Executivo

A solução recomendada é manter a base global no formato atual (`label` em ASCII/punycode) e corrigir o pipeline em três pontos:

1. gerar `homograph_base` em punycode real
2. decodificar `xn--...` antes de pontuar homograph/brand match
3. ampliar e instrumentar o Ring C para que ele não dependa de amostragem arbitrária em `.com`

Isso resolve o problema sem exigir migração estrutural da tabela `domain`.

## Diagnóstico resumido

Na produção atual:

1. `homograph_base` é normalizado para ASCII e perde o caractere Unicode confusable
2. o Ring A nunca procura o punycode real do homograph
3. o Ring B gera variantes Unicode, mas a base persiste o label em punycode
4. o Ring C encontra `xn--...`, mas pontua o punycode bruto
5. a `.com` ainda sofre com custo alto de scan e baixa observabilidade

Consequência:

- o domínio existe na base
- mas não vira match da brand

## Princípio da solução

Escolha arquitetural recomendada:

- manter `domain.label` como está hoje, em ASCII/punycode
- adaptar geração, recuperação e scoring para trabalhar corretamente com esse formato

Motivo:

1. menor risco de migração
2. menor impacto no modelo de dados
3. reaproveita o pipeline atual
4. resolve o problema real com mudança localizada

## Solução Proposta

## 1. Seed generation

### Problema atual

`homograph_base` perde a forma Unicode e vira ASCII degradado.

### Solução

Para `homograph_base`:

1. gerar a variante Unicode confusable
2. converter a variante para IDNA/punycode
3. persistir o punycode como `seed_value`
4. não passar essa família por sanitização ASCII que remova `xn--`

### Resultado esperado

Exemplos:

- `google` deve gerar `xn--gogle-jye` e `xn--gogle-rce`
- `paypal` deve gerar `xn--pypal-4ve`
- `bradesco` deve gerar `xn--brdesco-3fg` e `xn--brdesco-2lf`

## 2. Typo/homograph candidate generation

### Problema atual

`generate_typo_candidates()` gera variantes Unicode que não correspondem ao formato persistido no banco.

### Solução

1. quando a variante usar confusable Unicode, convertê-la para punycode antes de devolvê-la
2. manter as variantes ASCII comuns para typosquatting tradicional

### Resultado esperado

O Ring B deixa de produzir candidatos impossíveis de recuperar na base.

## 3. Scoring de punycode

### Problema atual

`compute_scores()` compara `xn--gogle-jye` com `google`, em vez de comparar `g\u043eogle` com `google`.

### Solução

1. decodificar `xn--...` para Unicode logo no início do scoring
2. aplicar `normalize_homograph()` sobre a forma Unicode decodificada
3. calcular:
   - `score_levenshtein`
   - `score_brand_hit`
   - `score_keyword`
   - `score_homograph`
   usando a forma visual real do domínio

### Resultado esperado

Casos como:

- `xn--gogle-jye`
- `xn--gogle-rce`
- `xn--pypal-4ve`

devem gerar `homograph_attack`.

## 4. Ring C

### Problema atual

O Ring C:

1. usa `limit=300`
2. não tem ordenação forte por relevância
3. sofre na `.com`

### Solução

1. aumentar limite por TLD
2. usar limites específicos por partição:
   - `com`: maior
   - `net`, `org`: intermediário
   - `com.br`: intermediário
3. adicionar telemetria por TLD:
   - `ring_c_candidates`
   - `ring_c_matches`
   - `ring_c_limit`
4. serializar isso nas respostas de job

### Resultado esperado

1. menor chance de perder um `xn--...` relevante por amostragem arbitrária
2. maior capacidade de depuração operacional

## 5. Busca síncrona

### Problema atual

O endpoint síncrono não é suficiente para validar `xn--...` do mesmo modo que o scan assíncrono.

### Solução

1. adicionar busca punycode complementar no fluxo síncrono
2. reaproveitar o mesmo scoring corrigido
3. expor telemetria de avaliação punycode

### Resultado esperado

O time consegue validar manualmente um caso real sem depender só do worker.

## 6. Operação em produção

### Problema atual

Mesmo corrigindo a lógica, as brands antigas continuam com seeds antigas até serem regeneradas.

### Solução

Após o deploy:

1. regenerar seeds das brands prioritárias
2. executar full scan para brands prioritárias
3. acompanhar jobs de `.com` com telemetria do Ring C

Prioridade inicial:

1. `Google`
2. `PayPal`
3. `Bradesco`
4. `Microsoft`
5. `Itaú`

## Revisão pós-implementação local (2026-04-17)

### O que já está correto

1. **Seed generation** — `seed_generation.py` gera corretamente seeds punycode com `encode_idna_label()` e `normalize=False`
2. **Typo candidates** — `generate_typo_candidates()` converte confusables para punycode via `_add_candidate()`
3. **Scoring engine** — `compute_scores()` decodifica punycode com `decode_idna_label()` e normaliza com `normalize_homograph()` antes de pontuar
4. **Busca síncrona** — `search_similarity.py` pontua punycode candidates contra o brand label corretamente
5. **Limites do Ring C** — aumentados para 2000/1500/1200 por TLD
6. **Telemetria** — `ring_c_candidates`, `ring_c_matches`, `ring_c_limit` expostos nos metrics do job
7. **Testes unitários** — 8 testes passando, cobrindo scoring, seed generation e API

### Bug pendente: seleção de seed no Ring C (run_similarity_scan.py:332-337)

**Severidade: alta — anula a eficácia do Ring C quando existem seeds homograph_base**

Código atual:

```python
homograph_seeds = [s for s in exact_seeds if s.seed_type == "homograph_base"]
punycode_seed = (
    max(homograph_seeds, key=lambda s: s.base_weight)
    if homograph_seeds
    else (max(fuzzy_seeds, key=lambda s: s.base_weight) if fuzzy_seeds else scan_seeds[0])
)
```

O Ring C busca TODOS os domínios `xn--...` de uma TLD e pontua cada um contra `punycode_seed.seed_value`. Quando `homograph_seeds` existe, o `seed_value` será algo como `xn--gogle-jye` — e a comparação fica `xn--gogle-jye` vs `xn--gogle-jye` (auto-match sem sentido: score 0.35, "low").

O correto é pontuar contra o **brand label** (`google`), não contra outra string punycode. Isso já funciona no branch `else` (quando não há homograph seeds, usa o fuzzy seed cujo `seed_value` é o brand label).

**Correção proposta:**

O Ring C deve SEMPRE usar o fuzzy seed (brand label) para scoring, não um homograph_base seed. Os homograph_base seeds devem ser usados apenas no Ring A (exact lookup).

```python
punycode_seed = (
    max(fuzzy_seeds, key=lambda s: s.base_weight) if fuzzy_seeds else scan_seeds[0]
)
```

Evidência numérica:

- `xn--gogle-jye` vs seed `xn--gogle-jye` → score 0.35, risk "low", sem `homograph_attack`
- `xn--gogle-jye` vs seed `google` → score 0.66, risk "high", com `homograph_attack`

### Melhoria pendente: ordenação do Ring C (similarity_repository.py:299)

O Ring C ordena por `first_seen_at DESC` — cronológico, não por relevância. Para TLDs grandes como `.com`, isso retorna os IDN mais recentes, não os mais similares à brand. Embora `similarity()` e `levenshtein()` sejam calculados no SQL, não são usados na ordenação.

Sugestão: ordenar por `similarity(label, :brand_label) DESC` ou por `levenshtein(label, :brand_label) ASC` para priorizar domínios mais próximos da brand.

## Plano de Implementação (atualizado)

## Fase 1: correção lógica

Escopo:

1. `seed_generation.py`
2. `compute_similarity.py`
3. `run_similarity_scan.py`
4. `similarity_repository.py`
5. `search_similarity.py`

Entrega:

1. seeds punycode reais ✅
2. scoring com decode IDNA ✅
3. Ring C com limites melhores ✅
4. telemetria ✅
5. corrigir seleção de seed no Ring C ✅
6. melhorar ordenação do Ring C ✅

Status:

- fase implementada localmente

## Fase 2: testes automatizados

Adicionar e manter testes para:

1. `xn--gogle-jye` -> `g\u043eogle`
2. `xn--gogle-rce` -> `g\u03bfogle`
3. `xn--pypal-4ve` -> `p\u0430ypal`
4. geração de seeds de `google`
5. geração de seeds de `paypal`
6. score seeded acima do threshold

Status:

- testes unitários implementados e passando (8/8)
- falta teste de integração cobrindo o fluxo Ring C end-to-end

## Fase 3: deploy

Checklist:

1. publicar backend corrigido
2. confirmar versão efetiva no container de produção
3. verificar que seeds novas da brand usam `xn--...`
4. reexecutar scans de brands críticas

## Fase 4: validação pós-deploy

Critérios de aceite mínimos:

1. `google.com` deve encontrar:
   - `xn--gogle-jye.com`
   - `xn--gogle-rce.com`
2. `paypal.com` deve encontrar:
   - `xn--pypal-4ve.com`
3. esses domínios devem aparecer com:
   - `score_homograph = 1.0` ou muito próximo
   - `homograph_attack` em `reasons`
4. o job deve expor telemetria do Ring C

## Critérios de Sucesso

O problema será considerado resolvido quando:

1. as brands gerarem seeds `homograph_base` em punycode
2. os casos reais confirmados na base entrarem em `similarity_match`
3. o motivo da classificação incluir `homograph_attack`
4. a análise síncrona e a assíncrona forem coerentes entre si

## Riscos e Mitigações

## Risco 1: aumento de custo na `.com`

Mitigação:

1. limites por TLD
2. telemetria
3. ajuste progressivo em produção

## Risco 2: falso positivo em IDN latino com acento

Mitigação:

1. diferenciar score homograph de mero IDN latino
2. usar a combinação:
   - `match só após normalização`
   - `script mixing`
   - `score_homograph`

## Risco 3: brands antigas continuarem com seeds antigas

Mitigação:

1. rodar regeneração de seeds após deploy
2. priorizar full scan das brands mais sensíveis

## Recomendação Final

A recomendação é:

1. promover para produção a implementação local já corrigida
2. regenerar seeds das brands prioritárias
3. repetir o teste com:
   - `google.com`
   - `paypal.com`
4. usar os três domínios reais já confirmados como critério de aceite do deploy

Os três casos de validação recomendados são:

- `xn--gogle-jye.com`
- `xn--gogle-rce.com`
- `xn--pypal-4ve.com`

Se esses três passarem no pós-deploy, o problema principal estará resolvido de forma comprovável.
