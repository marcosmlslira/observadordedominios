# 007 - Plano Detalhado

## Tema

Seed-first candidate retrieval para ampliacao da cobertura de dominios suspeitos, com pausa temporaria da avaliacao granular por LLM.

Documento base complementar:
- `C:\PROJETOS\observadordedominios\.specs\todos\007\retrieavel.md`

---

## 1. Resumo executivo

O codebase ja possui uma base de coleta ampla o suficiente para uma primeira fase forte de brand protection:

- `backend/app/worker/czds_ingestor.py` cobre zone files em larga escala.
- `backend/app/worker/ct_ingestor.py` cobre CertStream + crt.sh.
- `backend/app/worker/openintel_ingestor.py` cobre OpenINTEL para ccTLDs.

O principal gargalo hoje nao e falta de dominio ingerido. O gargalo e **recall de retrieval** dentro do corpus ja existente.

O pipeline atual ainda depende demais de:

- poucos seeds derivados do perfil da marca;
- busca fuzzy via `trigram + substring + typo exact`;
- keyword/contexto usados mais para score do que para gerar candidatos.

Ao mesmo tempo, a camada de LLM granular por dominio esta gerando custo em dois pontos diferentes do fluxo, enquanto o foco imediato do negocio e aumentar a superficie descoberta via seeds.

### Decisao recomendada

1. Desativar temporariamente a avaliacao granular por LLM por dominio.
2. Concentrar a LLM apenas em **geracao de seeds por marca**, com baixo volume e alto reaproveitamento.
3. Evoluir o retrieval para um modelo **seed-first + hybrid retrieval**, em vez de depender quase exclusivamente de fuzzy scan.

---

## 2. O que existe hoje no codigo

### 2.1 Ingestao / corpus

O produto ja tem um corpus multi-fonte:

- CZDS para grande volume de gTLDs.
- CT logs em streaming e batch.
- OpenINTEL para cobertura adicional em ccTLDs.

Conclusao: a primeira iteracao nao precisa priorizar nova fonte externa. O maior retorno esta em extrair melhor sinal do corpus atual.

### 2.2 Perfil da marca e seeds

Arquivos centrais:

- `backend/app/services/monitoring_profile.py`
- `backend/app/services/use_cases/sync_monitoring_profile.py`
- `backend/app/models/monitored_brand_seed.py`

Hoje os seeds nascem de:

- dominio oficial;
- label do dominio oficial;
- hostname stem;
- brand_primary;
- brand_alias;
- brand_phrase;
- support_keyword.

Porem, no scan efetivo, `iter_scan_seeds()` aceita apenas:

- `domain_label`
- `brand_primary`
- `brand_alias`
- `brand_phrase`

Isto significa que `support_keyword` e persistido, mas **nao participa do retrieval do scan**.

### 2.3 Retrieval atual

Arquivos centrais:

- `backend/app/services/use_cases/run_similarity_scan.py`
- `backend/app/repositories/similarity_repository.py`
- `backend/app/services/use_cases/compute_similarity.py`

O scan atual funciona assim:

1. seleciona seeds elegiveis;
2. para cada seed gera typo candidates locais;
3. consulta candidatos por:
   - trigram (`label % :brand_label`);
   - substring (`label LIKE :brand_like`);
   - typo exact (`label = ANY(:typo_candidates)`);
4. calcula score composto;
5. persiste os melhores matches.

Pontos fortes atuais:

- pipeline incremental com watermark;
- bom score composto;
- typo/homograph ja existem como sinal;
- custo operacional controlado.

Pontos fracos atuais:

- homograph esta mais presente no score do que no retrieval;
- keywords da marca influenciam score, mas nao o universo de busca;
- combosquatting ainda e subexplorado;
- retrieval amplo por fuzzy em particoes grandes fica caro e nem sempre captura combinacoes criativas;
- o motor ainda pensa mais em "classificar o que apareceu" do que em "gerar hipoteses fortes de ataque".

### 2.4 LLM granular atual

Arquivos centrais:

- `backend/app/services/use_cases/generate_llm_assessment.py`
- `backend/app/services/use_cases/enrich_similarity_match.py`
- `backend/app/worker/assessment_worker.py`
- `backend/app/repositories/match_state_snapshot_repository.py`

Hoje a LLM granular aparece em **dois caminhos**:

1. durante `enrich_similarity_match()`;
2. no `assessment_worker`, via snapshots que precisam de reavaliacao.

Isso cria:

- custo duplicado;
- complexidade operacional;
- dependencia desnecessaria para a fase atual do produto;
- baixa relacao custo/valor comparada a investir a mesma verba em cobertura de retrieval.

---

## 3. Diagnostico

### Diagnostico principal

O sistema ja pontua relativamente bem o que encontra, mas ainda encontra menos do que deveria para uma plataforma de brand protection de alto impacto.

### Gaps estruturais observados

1. `support_keyword` existe no perfil, mas nao e promovido a estrategia de retrieval.
2. Nao existe uma familia explicita de seed para:
   - combos realistas;
   - prefixos/sufixos agressivos;
   - variacoes semanticas;
   - hipoteses geradas por LLM.
3. O retrieval depende demais de buscar similaridade em massa no banco, em vez de tambem consultar **candidatos gerados** com lookup exato.
4. A LLM esta sendo consumida por match, quando o ponto de maior ROI imediato e por marca.

### Tese de produto

Para esta fase da empresa, o melhor uso da LLM nao e explicar melhor cada dominio encontrado. E **encontrar mais dominios certos**.

---

## 4. Objetivo da iniciativa

### Objetivo principal

Ampliar recall e cobertura de dominios potencialmente fraudulentos ou que usem a marca de forma indevida, com foco inicial em geracao de seeds.

### Objetivos secundarios

- reduzir custo operacional removendo a LLM granular do caminho critico;
- manter o pipeline atual funcional enquanto o novo motor entra por fases;
- aumentar previsibilidade e auditabilidade do retrieval;
- preparar o produto para reativar uma LLM mais inteligente no futuro, mas em ponto de maior ROI.

### Nao objetivos desta fase

- substituir todo o scoring atual;
- reescrever a modelagem completa de matches;
- adicionar varias fontes externas novas antes de provar ganho no corpus atual;
- voltar a investir em parecer LLM por dominio antes de medir ganho real de seeds.

---

## 5. Principio de arquitetura recomendado

### Nova direcao

Migrar de um modelo predominantemente `fuzzy-scan-first` para um modelo `seed-first candidate generation + hybrid retrieval`.

### Fluxo alvo

1. Marca e configurada ou atualizada.
2. O sistema gera seeds deterministicos.
3. A LLM gera seeds contextuais de baixo volume.
4. As familias de seeds geram candidatos plausiveis.
5. O sistema busca esses candidatos por lookup exato e fuzzy controlado.
6. Os resultados consolidados seguem para score e enrichment.
7. A LLM granular por dominio permanece desligada.

Representacao simplificada:

```text
Brand profile
  -> deterministic seeds
  -> LLM seeds
  -> candidate generation families
  -> exact retrieval + fuzzy retrieval
  -> dedup + ranking
  -> selective enrichment
  -> analyst triage
```

---

## 6. Seed strategy recomendada

### 6.1 Familias de seed

As familias abaixo devem existir explicitamente no dominio do produto, mesmo que no inicio sejam persistidas usando a tabela atual de seeds.

Familias recomendadas:

- `brand_core`
- `official_domain_label`
- `official_hostname_stem`
- `brand_alias`
- `brand_phrase`
- `combo_brand_keyword`
- `combo_keyword_brand`
- `semantic_brand`
- `typo_base`
- `homograph_base`
- `llm_combo`
- `llm_semantic`
- `llm_social_engineering`

### 6.2 Regras deterministicas

Deterministic seed generation deve cobrir:

- normalizacao forte do nome da marca;
- quebra do dominio oficial em label util;
- aliases curtos e aliases multi-palavra;
- combinacoes com keywords de negocio;
- combinacoes com keywords de abuso;
- prefixos/sufixos comuns de phishing;
- typo bases;
- homograph bases.

### 6.3 Regras importantes

- `support_keyword` sozinho nao deve virar seed de scan amplo.
- keyword so entra em retrieval quando estiver ancorada em brand/core/alias.
- termos genericos demais devem ser descartados ou rebaixados.
- seeds curtos demais devem ser bloqueados ou restritos.
- cada seed precisa de peso, familia e origem.

### 6.4 Como usar a LLM nesta fase

A LLM deve ser usada apenas para responder:

> "Quais formas realistas um atacante usaria para registrar dominios que parecam ligados a esta marca?"

Saida desejada da LLM:

- tokens e combos sem TLD obrigatorio;
- familias separadas;
- baixa cardinalidade;
- alta plausibilidade;
- foco em phishing, login, suporte, cobranca, portal, conta, reset, segunda via, onboarding, pagamento, atendimento.

Exemplo de saida ideal:

```json
{
  "brand_core": ["sindicoai", "sindico"],
  "combo_brand_keyword": ["sindico-login", "sindico-boleto", "sindico-admin"],
  "combo_keyword_brand": ["portal-sindico", "acesso-sindico"],
  "semantic_brand": ["gestaocondominio", "portalcondominio"],
  "social_engineering": ["meusindico", "paineldocliente-sindico"]
}
```

---

## 7. Retrieval strategy recomendada

### 7.1 O que deve continuar existindo

O scan atual por fuzzy continua util, mas deixa de ser o unico protagonista.

Manter:

- trigram;
- substring;
- typo exact;
- scoring atual;
- worker atual;
- watermark/delta.

### 7.2 O que precisa entrar

Adicionar retrieval em aneis, cada um com limite proprio.

#### Anel A - Exact generated candidates

Entrada:

- candidatos gerados a partir de seeds deterministicos e LLM.

Busca:

- lookup exato por `name` ou por `label + tld`.

Motivo:

- cobre melhor typo, homograph e combo sem depender de o banco "descobrir" a similaridade por fuzzy.

#### Anel B - Focused fuzzy retrieval

Entrada:

- seeds nucleares de alta confianca.

Busca:

- mecanismo atual de trigram + substring + typo exact.

Motivo:

- continua encontrando casos nao antecipados.

#### Anel C - Homograph retrieval

Entrada:

- seeds com mapa de confusables;
- dominios punycode e unicode.

Busca:

- lookup exato de labels normalizados;
- opcionalmente consulta dedicada para labels contendo `xn--`.

Motivo:

- homograph hoje esta subrepresentado na fase de busca.

#### Anel D - Combo/context retrieval

Entrada:

- combos brand+keyword;
- keyword+brand;
- semanticos relevantes.

Busca:

- exata primeiro;
- fuzzy curta e limitada depois.

Motivo:

- combosquatting e um dos vetores mais relevantes para uso indevido de marca.

### 7.3 Recomendacao de quotas iniciais

Sugestao inicial:

- Anel A: 500 a 2.000 candidatos gerados por marca
- Anel B: fuzzy atual com limite reduzido por seed
- Anel C: 100 a 300 variantes homograph controladas
- Anel D: 100 a 500 combos contextualizados

O numero final deve ser calibrado com telemetria, nao por intuicao.

---

## 8. Mudancas tecnicas recomendadas

### 8.1 Fase 1 sem migracao pesada

Esta fase deve reaproveitar o schema atual o maximo possivel.

Recomendacao:

- continuar usando `monitored_brand_seed`;
- adicionar novos `seed_type`;
- usar `source_ref_type` com novos valores como:
  - `system_rule`
  - `llm_seed`
  - `combo_generator`
- usar `base_weight` para priorizacao;
- manter `is_manual` e `is_active`.

Isto reduz risco e acelera entrega.

### 8.2 Fase 2 com auditabilidade maior

Se a primeira fase provar valor, adicionar modelagem de auditoria:

- `brand_seed_generation_run`
- `brand_seed_generation_artifact`

Campos recomendados:

- brand_id
- generation_source (`deterministic` / `llm`)
- prompt_hash
- model_name
- generated_count
- accepted_count
- rejected_count
- created_at

Nao e obrigatorio para a primeira entrega.

### 8.3 Novos servicos recomendados

Sugestao de novos modulos:

- `backend/app/services/seed_generation.py`
- `backend/app/services/seed_validation.py`
- `backend/app/services/candidate_generation.py`
- `backend/app/services/use_cases/generate_brand_seeds.py`

Responsabilidades:

- derivar seeds deterministicos;
- chamar LLM quando habilitada para seed generation;
- validar e deduplicar seeds;
- transformar seeds em candidatos consultaveis.

### 8.4 Mudancas nos servicos atuais

Arquivos que devem mudar:

- `backend/app/services/monitoring_profile.py`
  - ampliar taxonomia de seeds;
  - rever `iter_scan_seeds()`;
  - separar melhor seed de score vs seed de retrieval.

- `backend/app/services/use_cases/sync_monitoring_profile.py`
  - regenerar seeds novas ao criar/editar marca;
  - suportar pipeline deterministico + LLM.

- `backend/app/services/use_cases/run_similarity_scan.py`
  - incorporar aneis de retrieval;
  - unir exact generated candidates com fuzzy candidates.

- `backend/app/repositories/similarity_repository.py`
  - adicionar metodos para exact lookup de candidatos gerados;
  - manter `fetch_candidates()` para fuzzy retrieval;
  - idealmente expor consulta dedicada por lista de nomes/labels.

---

## 9. Pausa temporaria da LLM granular

### 9.1 Objetivo

Eliminar custo por dominio enquanto o investimento de IA e redirecionado para geracao de seeds por marca.

### 9.2 Recomendacao tecnica

Adicionar uma feature flag explicita:

- `MATCH_LLM_ASSESSMENT_ENABLED=false`

Opcionalmente separar:

- `SEED_LLM_GENERATION_ENABLED=true|false`

Assim o produto consegue:

- desligar parecer por dominio;
- manter IA disponivel para seed generation.

### 9.3 Pontos de corte obrigatorios

Os dois caminhos abaixo precisam respeitar a mesma flag:

1. `backend/app/services/use_cases/enrich_similarity_match.py`
2. `backend/app/worker/assessment_worker.py`

### 9.4 Forma mais segura de desligar

Recomendacao em duas camadas:

Camada 1:

- `generate_llm_assessment()` retorna `None` imediatamente quando a flag estiver desligada.

Camada 2:

- `assessment_worker` nao processa snapshots quando a flag estiver desligada.
- opcionalmente remover o servico do stack ou deixar replica 0.

### 9.5 Efeito esperado

- `llm_assessment` passa a ficar `null`;
- snapshots continuam existindo;
- enrichment continua funcionando;
- UI nao quebra, desde que trate ausencia de parecer como estado valido;
- custo OpenRouter cai drasticamente.

### 9.6 Observacao importante

Hoje ha duas escritas relacionadas a LLM:

- em `similarity_match.llm_assessment`
- em `match_state_snapshot.llm_assessment`

A pausa deve afetar ambas, mas sem migracao destrutiva.

---

## 10. API e UX recomendadas

### 10.1 Endpoints novos ou ajustados

Recomendados:

- `POST /v1/brands/{id}/seeds/regenerate`
- `GET /v1/brands/{id}/seeds/preview`
- `GET /v1/brands/{id}/seeds`
  - agrupar por familia e origem

### 10.2 Comportamento no onboarding

Ao criar ou editar uma marca:

1. normaliza perfil;
2. gera seeds deterministicos;
3. opcionalmente gera seeds LLM;
4. persiste;
5. dispara scan inicial.

### 10.3 UI minima recomendada

Na tela da marca:

- mostrar seeds por familia;
- mostrar quantas vieram de regras vs LLM;
- permitir desativar seed especifica;
- permitir regeneracao manual;
- mostrar observacao de que o parecer LLM por dominio esta temporariamente pausado para priorizar cobertura.

---

## 11. Instrumentacao e metricas

Sem observabilidade, a feature vira intuicao. Esta iniciativa precisa nascer com metricas.

### Metricas obrigatorias

- seeds_total_por_marca
- seeds_ativas_para_scan
- seeds_por_familia
- candidatos_gerados_por_familia
- candidatos_encontrados_por_familia
- hit_rate_por_familia
- scan_duration_ms_por_anel
- matches_novos_por_marca
- recall_proxy_por_marca
- custo_llm_seed_generation_por_marca
- custo_llm_match_assessment

### Sinais de sucesso

- aumento de matches relevantes por marca;
- aumento de `immediate_attention` e `defensive_gap` com qualidade aceitavel;
- aumento de dominios combo e typo realmente encontrados;
- queda do custo de LLM por match;
- menor dependencia de fuzzy scan amplo em particoes grandes.

---

## 12. Sequenciamento recomendado

### Fase 0 - Desligamento controlado da LLM granular

Objetivo:

- cortar custo rapido sem quebrar fluxo.

Entregas:

- feature flag em config;
- gate unico em `generate_llm_assessment()`;
- `assessment_worker` respeitando flag;
- stack sem dependencia operacional da avaliacao granular.

### Fase 1 - Seed-first deterministic retrieval

Objetivo:

- gerar mais candidatos relevantes sem depender de LLM.

Entregas:

- novas familias de seeds;
- candidate generation deterministica;
- exact lookup para candidatos gerados;
- preservacao do fuzzy retrieval atual como complemento;
- telemetria por familia.

### Fase 2 - LLM seed generation

Objetivo:

- ampliar cobertura contextual com baixo custo.

Entregas:

- prompt de geracao por marca;
- validacao e deduplicacao;
- seeds LLM persistidas na mesma tabela;
- quotas por marca;
- cache/regeneration controlado.

### Fase 3 - Tunagem e consolidacao

Objetivo:

- controlar ruido e estabilizar ROI.

Entregas:

- calibracao de pesos;
- quotas por familia;
- ajustes de seeds curtas e genericas;
- comparacao de performance antes/depois.

---

## 13. Backlog tecnico sugerido

### Bloco A - Custo / controle

1. Adicionar `MATCH_LLM_ASSESSMENT_ENABLED` em `backend/app/core/config.py`.
2. Gatear `generate_llm_assessment()` pela nova flag.
3. Fazer `assessment_worker` sair sem processar quando a flag estiver desligada.
4. Ajustar `infra/stack.yml` e `infra/stack.dev.yml` para a nova flag.

### Bloco B - Seed domain model

1. Expandir `seed_type` aceitos pelo dominio.
2. Revisar `iter_scan_seeds()` para permitir familias novas, mas nao permitir keyword pura.
3. Criar servico de geracao deterministica.
4. Garantir deduplicacao forte entre seeds equivalentes.

### Bloco C - Retrieval

1. Adicionar metodos de exact lookup no repository.
2. Adicionar candidate generation por familia.
3. Integrar o novo retrieval em `run_similarity_scan.py`.
4. Manter compatibilidade com watermark, dedup e upsert atual.

### Bloco D - LLM seed generation

1. Criar gerador de prompt por marca.
2. Adicionar quotas e validacao.
3. Persistir seeds LLM com origem clara.
4. Expor regeneracao manual por API.

### Bloco E - UX / observabilidade

1. Expor seeds por familia no endpoint atual.
2. Adicionar preview e regenerate.
3. Medir hit rate por familia.
4. Mostrar no admin quando o parecer por dominio estiver pausado.

---

## 14. Riscos e mitigacoes

### Risco 1 - Explosao de ruido

Causa:

- combos genericos demais;
- keyword sem ancora;
- seeds curtas.

Mitigacao:

- whitelist/blacklist de familias;
- minimo de comprimento;
- quota por familia;
- scores e pesos conservadores no inicio.

### Risco 2 - Explosao de volume de candidatos

Causa:

- gerar variantes demais por marca.

Mitigacao:

- exact lookup primeiro;
- caps por familia;
- caps por TLD;
- amostragem orientada por risco.

### Risco 3 - LLM gerar lixo semantico

Causa:

- prompt solto;
- falta de validacao.

Mitigacao:

- prompt estrito;
- JSON controlado;
- filtros de stopwords e genericidade;
- aprovacao automatica limitada por regras.

### Risco 4 - Perder contexto analitico ao desligar a LLM granular

Causa:

- time acostumado com parecer pronto por dominio.

Mitigacao:

- manter enrichment e sinais tecnicos;
- deixar claro que a pausa e temporaria e orientada a ROI;
- reavaliar retorno da LLM granular depois que o recall melhorar.

---

## 15. Criterios de aceite

### Criterios obrigatorios da fase inicial

- a LLM granular por dominio nao e mais executada quando a flag estiver desligada;
- `assessment_worker` nao gera custo quando a flag estiver desligada;
- a geracao de seeds passa a produzir familias novas relevantes;
- retrieval passa a encontrar candidatos por exact generated lookup;
- keywords deixam de ser apenas score helper e passam a gerar seeds ancoradas;
- a marca pode listar e regenerar seeds;
- o pipeline continua compativel com scan assinado e enrichment atual.

### Criterios de sucesso de negocio

- aumento claro de cobertura em typo/homograph/combo;
- maior volume de matches relevantes por marca sem crescimento descontrolado de ruido;
- reducao perceptivel de custo com LLM;
- time consegue argumentar que o produto esta encontrando mais dominios realmente perigosos.

---

## 16. Recomendacao final

Se a prioridade real e defender o futuro da empresa, a aposta correta agora e:

- **menos LLM por dominio**
- **mais inteligencia na geracao de seeds**
- **mais retrieval orientado a hipoteses**

O corpus ja existe. O que falta e transformar melhor a marca em superficie de busca.

Em termos praticos, a melhor primeira entrega e:

1. desligar a LLM granular;
2. introduzir feature flag separando `match assessment` de `seed generation`;
3. criar seed generation deterministic + LLM;
4. adicionar exact generated retrieval;
5. medir ganho de recall antes de qualquer nova sofisticacao de parecer.

Essa sequencia entrega:

- economia imediata;
- ganho real de cobertura;
- menor risco tecnico;
- uma base muito mais forte para futuras camadas de IA.
