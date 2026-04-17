Perfeito — vou consolidar tudo em uma **especificação completa, coesa e pronta para virar backlog técnico**, incluindo:

* dor real do sistema atual
* redesign do retrieval
* camada de LLM
* combinação de keywords via LLM (seu ponto final)

---

# 📄 ESPECIFICAÇÃO COMPLETA

## Observador de Domínios — Evolução de Candidate Retrieval

### Tema: Cobertura de Homograph + Typosquatting + Combosquatting

---

# 1. 🎯 VISÃO GERAL

O Observador de Domínios possui hoje um motor robusto de:

* similaridade lexical (trigram, levenshtein)
* detecção de homograph
* enriquecimento (DNS, WHOIS, página)
* priorização (actionability)

Porém, há um gargalo crítico:

> **O sistema não está encontrando candidatos suficientes para que essas técnicas operem com máxima efetividade.**

---

# 2. 🚨 A DOR (PROBLEMA REAL)

## 2.1 Problema principal

O pipeline atual depende de:

* seeds limitados
* busca baseada em:

  * trigram (`pg_trgm`)
  * LIKE
  * typo candidates derivados localmente

Isso gera:

```text
Domínios globais → filtro lexical → subconjunto pequeno → scoring
```

---

## 2.2 Consequências

### ❌ Homograph

* não entra no pipeline se não parecer similar antes da normalização

### ❌ Typosquatting

* limitado a variações locais
* não cobre variações mais criativas

### ❌ Combosquatting

* praticamente subexplorado
* depende de substring simples

---

## 2.3 Sintoma

> **Alta precisão, baixo recall**

---

# 3. 🧠 DIAGNÓSTICO

## Problema estrutural

> O sistema trata **ataques como problema de classificação**, quando também são problema de **geração de candidatos**.

---

# 4. 🎯 OBJETIVO

Evoluir o pipeline para:

* ↑ Recall de candidatos
* ↑ Cobertura de:

  * homograph
  * typosquatting
  * combosquatting
* manter:

  * controle de custo
  * explicabilidade

---

# 5. 🧩 SOLUÇÃO — NOVO MODELO

## Novo fluxo

```text
Brand → Seed Generation (tradicional + LLM)
     → Candidate Retrieval (4 anéis)
     → União + Dedup
     → Scoring
     → Enrichment
```

---

# 6. 🔵 RETRIEVAL EM ANÉIS

---

## 🔵 Anel 1 — Alta precisão (existente)

* trigram alto
* LIKE
* match exato
* typo simples

---

## 🟡 Anel 2 — Typosquatting estruturado

### Famílias:

* single edit
* keyboard adjacency
* transposição
* duplicação
* omissão
* TLD swap
* prefix/suffix

---

## 🟣 Anel 3 — Homograph explícito

### Entrada:

* domínios com `xn--`
* Unicode
* script mixing

### Processamento:

```text
normalizar → comparar com marca
```

---

## 🟢 Anel 4 — Combo / Contextual

### Regras:

* brand + keyword
* keyword + brand
* core + keyword

---

# 7. 🧠 SEEDS — NOVA MODELAGEM

---

## 7.1 Seeds tradicionais

* brand_label
* aliases
* official domains

---

## 7.2 Seeds novos

### 🔹 Núcleo da marca

Ex:

```text
SindicoAI → sindico, sindicoai
```

---

### 🔹 Seeds contextuais

* login
* boleto
* suporte
* portal
* admin

---

# 8. 🤖 NOVA CAMADA — LLM SEED GENERATION

---

## 8.1 Objetivo

Simular comportamento real de atacantes para gerar seeds avançados.

---

## 8.2 Papel da LLM

A LLM atua como:

> **gerador de hipóteses de ataque**

---

# 9. 🧠 GERAÇÃO DE VARIAÇÕES VIA LLM

---

## Tipos de saída

```json
{
  "typo_variations": [],
  "homograph_patterns": [],
  "combo_domains": [],
  "prefix_suffix": [],
  "semantic_variations": []
}
```

---

# 10. 🔥 NOVO COMPONENTE CRÍTICO

## 🧠 COMBINAÇÃO DE KEYWORDS VIA LLM

---

## 10.1 Problema atual

Hoje keywords:

* existem
* mas não são exploradas na geração de candidatos

---

## 10.2 Nova abordagem

A LLM deve gerar:

> **combinações realistas de palavras que um atacante usaria**

---

## 10.3 Exemplos

Dado:

```text
Marca: SindicoAI
Contexto: condomínio
```

LLM gera:

### Combos diretos

* sindico-login
* portal-sindico
* sindico-boleto
* sindico-admin

### Engenharia social

* meusindico
* acessosindico
* paineldosindico
* areadocliente-sindico

### Semânticos

* gestaocondominio
* administradorcondominio

---

## 10.4 Regra de uso

Esses combos viram:

* seeds novos
* entradas no anel 4

---

# 11. 🧾 PROMPT LLM (FINAL)

```text
Você é um especialista em phishing e criação de domínios maliciosos.

Gere variações de domínio para enganar usuários.

Marca: {brand}
Domínio: {domain}
Segmento: {segment}
Idioma: {language}

Gere usando:

1. Typosquatting
2. Homograph (conceitual)
3. Combo squatting
4. Prefixos/sufixos maliciosos
5. Engenharia social
6. Variações semânticas

IMPORTANTE:
- Combine palavras de forma realista
- Gere nomes plausíveis
- Simule comportamento humano malicioso

Retorne apenas nomes de domínio (sem TLD obrigatório).
```

---

# 12. 🧠 SINAIS TÉCNICOS (NOVOS)

---

## Homograph

* uses_idn
* has_punycode
* mixed_scripts
* confusable_count
* match_after_normalization

---

## Typosquatting

* single_edit
* transposition
* keyboard_adjacent
* duplication
* omission
* tld_swap
* prefix_suffix

---

## Retrieval

```json
["trigram", "typo", "homograph", "combo"]
```

---

# 13. ⚖️ CONTROLE DE CUSTO

---

## Limite por anel

| Anel | Limite |
| ---- | ------ |
| 1    | 300    |
| 2    | 200    |
| 3    | 150    |
| 4    | 100    |

---

## Regras

* limitar seeds LLM (50–200)
* deduplicar
* cache por brand
* limitar fragmentos fracos

---

# 14. 🔁 NOVO FLUXO

```text
Brand criada
 ↓
Seed tradicional
 ↓
Seed LLM (novo)
 ↓
Merge
 ↓
Anel 1 (lexical)
Anel 2 (typo)
Anel 3 (homograph)
Anel 4 (combo)
 ↓
União
 ↓
Dedup
 ↓
Scoring
 ↓
Enrichment
```

---

# 15. 📊 IMPACTO ESPERADO

---

## Ganhos

* ↑ Recall
* ↑ Detecção de ataques reais
* ↑ Cobertura de phishing
* ↑ Valor percebido

---

## Riscos

| Risco          | Mitigação        |
| -------------- | ---------------- |
| Ruído          | limites por anel |
| custo          | cache + limites  |
| overgeneration | dedup + ranking  |

---

# 16. 🚀 ROADMAP

---

## Fase 1 — Observabilidade

* retrieval_sources
* sinais técnicos

---

## Fase 2 — Retrieval novo

* anel typo
* anel homograph

---

## Fase 3 — LLM

* seed generation
* keyword combos

---

## Fase 4 — Calibração

* medir recall
* ajustar limites

---

# 17. 🧠 PRINCÍPIO DE PRODUTO

Seguindo **Getting Real**:

* não reescrever tudo
* evoluir incrementalmente
* focar no que gera valor imediato

👉 

---

# 18. 🧩 TL;DR FINAL

> O problema não está em como você classifica ataques, mas em quantos candidatos chegam até essa classificação.
>
> A solução é expandir o balde inicial usando:
>
> * múltiplos caminhos de retrieval
> * geração estruturada de typo/homograph
> * e LLM para simular ataques reais, incluindo combinações inteligentes de palavras-chave
