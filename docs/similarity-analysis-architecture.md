# Arquitetura de Análise de Similaridade — Estudo Técnico

> Data: 2026-03-21 | Status: Proposta para validação
> Contexto: Este documento define a arquitetura para o core do produto — detecção de domínios
> suspeitos por similaridade, abuso de marca e risco. Complementa `domain-table-redesign-proposal.md`.

---

## 1. O Problema Real

O Observador de Domínios não é um buscador de "strings parecidas". É um **detector de abuso de marca baseado em múltiplos sinais**:

| Ataque | Exemplo | Técnica de detecção |
|---|---|---|
| Typosquatting | `goggle.com`, `gogle.com` | Levenshtein, trigram |
| Homograph (unicode) | `gοogle.com` (ο grego) | Normalização + tabela de substituição |
| Brand abuse / combo | `google-login-secure.com` | Substring + keyword scoring |
| Semantic combo | `meu-banco-oficial.net` | Keyword + (futuro) embedding |
| Leet speak | `g00gle.com`, `go0g1e.com` | Normalização + Levenshtein |
| TLD swap | `google.co` (vs `.com`) | Cross-TLD matching |

**Para cada domínio ou marca monitorada**, o sistema precisa varrer a base global de domínios, encontrar candidatos suspeitos, computar scores e notificar.

---

## 2. Restrição Fundamental: Custo do pgvector

Antes de qualquer decisão arquitetural, os números:

### Custo de embedding (vector(384)) na tabela domain

| Escala | Dados vector | Index HNSW (~1.5x) | Total | RAM mínimo para ANN |
|---|---|---|---|---|
| 31M rows (hoje) | 44 GB | 66 GB | **110 GB** | ~30 GB |
| 200M rows (.com) | 286 GB | 429 GB | **715 GB** | ~200 GB |

**Veredicto: pgvector na tabela domain inteira é inviável.** Nem em custo de storage, nem em RAM, nem em tempo de computação dos embeddings (200M × inferência = dias de GPU).

### Custo de pg_trgm (GIN trigram index) na tabela domain

| Escala | Coluna label | GIN index | Total |
|---|---|---|---|
| 31M rows | 414 MB | ~1.6 GB | **~2 GB** |
| 200M rows | 2.7 GB | ~10.5 GB | **~13 GB** |

**Veredicto: pg_trgm é viável e suficiente para 90%+ dos casos de uso.**

### Teste real: performance sem índice GIN (pior caso)

Executado no banco atual (31M rows, sample de 1%):

| Query | Tempo (1% = 310k rows) | Projeção 100% sem GIN |
|---|---|---|
| Trigram `% 'google'` | 4.306 ms | ~7 min (seq scan) |
| `LIKE '%google%'` | 443 ms | ~44 s (seq scan) |
| Levenshtein `<= 2` | 3.975 ms | ~6.5 min (seq scan) |

**Com GIN trigram index:** trigram e LIKE caem para **< 100 ms** (index scan). Levenshtein pode usar GIN como pré-filtro.

---

## 3. Decisão Arquitetural: Duas Camadas

```
┌─────────────────────────────────────────────────────────┐
│                    CAMADA 1: INGESTÃO                    │
│                                                         │
│   domain (partitioned by TLD)                           │
│   ┌─────────────────────────────────────────────┐       │
│   │ name | tld | label | first_seen_at | last_   │       │
│   │                                     seen_at │       │
│   └─────────────────────────────────────────────┘       │
│   Índices: PK(name,tld) + GIN trigram(label)            │
│   + ix(tld, first_seen_at DESC)                         │
│                                                         │
│   Escrita: CZDS/NSEC upsert em batch                    │
│   Leitura: Similarity worker lê novos domínios          │
└─────────────────────────┬───────────────────────────────┘
                          │ lê
┌─────────────────────────▼───────────────────────────────┐
│                 CAMADA 2: ANÁLISE                        │
│                                                         │
│   monitored_brand ──► similarity_scan_cursor             │
│        │                    │                            │
│        │                    ▼                            │
│        └──────────► similarity_match                     │
│                                                         │
│   Worker: varre novos domínios por brand/TLD            │
│   Checkpoint: sabe onde parou, continua na falha        │
│   Resultado: matches com score e razões                 │
└─────────────────────────────────────────────────────────┘
```

**Princípio:** A tabela `domain` é leve e otimizada para ingestão. A análise de similaridade é um **consumidor** que lê `domain` e escreve resultados em tabelas próprias. As duas camadas não se misturam.

---

## 4. Schema da Tabela `domain` (revisado para similaridade)

```sql
CREATE TABLE domain (
    name          VARCHAR(253) NOT NULL,
    tld           VARCHAR(24)  NOT NULL,
    label         VARCHAR(228) NOT NULL,   -- name sem TLD (ex: "google" de "google.com")
    first_seen_at TIMESTAMPTZ  NOT NULL,
    last_seen_at  TIMESTAMPTZ  NOT NULL,
    PRIMARY KEY (name, tld)
) PARTITION BY LIST (tld);

-- Partições
CREATE TABLE domain_net  PARTITION OF domain FOR VALUES IN ('net');
CREATE TABLE domain_org  PARTITION OF domain FOR VALUES IN ('org');
CREATE TABLE domain_info PARTITION OF domain FOR VALUES IN ('info');
```

### Índices

```sql
-- Obrigatório: trigram para buscas de similaridade e LIKE
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;

CREATE INDEX ix_domain_label_trgm ON domain USING gin (label gin_trgm_ops);

-- Para queries de novos domínios (delta para similarity worker)
CREATE INDEX ix_domain_first_seen ON domain (tld, first_seen_at DESC);

-- Para queries temporais gerais
CREATE INDEX ix_domain_last_seen ON domain (tld, last_seen_at DESC);
```

### Coluna `label` — justificativa

| Sem label (computado on-the-fly) | Com label (stored) |
|---|---|
| `left(name, length(name)-length(tld)-1)` em cada query | Coluna direta |
| Não pode ter GIN index funcional eficiente | GIN index direto no label |
| Seq scan para trigram: ~7 min em 31M | Index scan: < 100ms |
| Economiza ~414 MB | Custa ~414 MB |

**O GIN trigram index no `label` é o coração da busca de similaridade.** Sem ele, cada busca por marca seria um sequential scan de minutos. Com ele, é sub-segundo.

### Computação do label na ingestão

```python
# No bulk_upsert, compute label em Python antes do SQL:
labels = [name[:-(len(tld) + 1)] for name in domain_names]

# SQL:
INSERT INTO domain (name, tld, label, first_seen_at, last_seen_at)
SELECT
    unnest(:names),
    :tld,
    unnest(:labels),
    :ts, :ts
ON CONFLICT (name, tld) DO UPDATE
SET last_seen_at = GREATEST(domain.last_seen_at, EXCLUDED.last_seen_at)
```

### Tamanho estimado com label

| Métrica | Sem label | Com label |
|---|---|---|
| Bytes/row | ~42 | ~56 |
| 31M rows (dados) | ~1.2 GB | ~1.7 GB |
| GIN trigram index | — | ~1.6 GB |
| Outros índices | ~1.2 GB | ~1.8 GB |
| **Total 31M** | **~2.4 GB** | **~5.1 GB** |
| **Total 200M** | **~14 GB** | **~33 GB** |

Os ~33 GB para 200M rows com similaridade é **viável** e **2.3x menor** que o schema atual (que não tem capacidade de similaridade nenhuma).

---

## 5. Estratégias de Busca — Sem pgvector

### 5.1. Trigram Similarity (principal)

Encontra domínios com labels "parecidos" com a marca.

```sql
-- Buscar domínios similares a "meubanco"
SELECT name, label,
       similarity(label, 'meubanco') AS sim_score
FROM domain
WHERE label % 'meubanco'                         -- GIN index pre-filter
  AND similarity(label, 'meubanco') > 0.3        -- threshold
ORDER BY sim_score DESC
LIMIT 500;
```

**Performance com GIN index:** < 100ms para qualquer marca, qualquer escala.

**Detecta:** typosquatting, trocas de caractere, inserções/omissões.

### 5.2. Substring / Brand Containment

Encontra domínios que **contêm** a marca (combo-squatting).

```sql
-- Domínios que contêm "meubanco"
SELECT name, label
FROM domain
WHERE label LIKE '%meubanco%'     -- GIN trigram também acelera LIKE
ORDER BY length(label) ASC        -- mais curtos primeiro (mais suspeitos)
LIMIT 500;
```

**Performance com GIN index:** < 100ms.

**Detecta:** `meubanco-login.com`, `seguromeubanco.net`, `meubancodigital.org`.

### 5.3. Keyword Risk Scoring

Domínios que contêm a marca + palavras de risco.

```python
RISK_KEYWORDS = [
    'login', 'secure', 'verify', 'update', 'account',
    'bank', 'password', 'confirm', 'auth', 'signin',
    'support', 'help', 'official', 'alert', 'recover',
]

# Gerar query: marca + qualquer keyword de risco
# SQL:
SELECT name, label
FROM domain
WHERE label LIKE '%meubanco%'
  AND (
    label LIKE '%login%' OR label LIKE '%secure%' OR label LIKE '%verify%'
    OR label LIKE '%account%' OR label LIKE '%password%'
    -- ... demais keywords
  )
```

**Performance:** < 200ms (múltiplos LIKE com GIN).

**Detecta:** `meubanco-login-seguro.com`, `verify-meubanco.net`.

### 5.4. Levenshtein Distance

Edit distance exata para typosquatting preciso.

```sql
-- Domínios com edit distance <= 2 do label da marca
SELECT name, label,
       levenshtein(label, 'meubanco') AS edit_dist
FROM domain
WHERE label % 'meubanco'                           -- GIN pré-filtra (CRUCIAL)
  AND levenshtein(label, 'meubanco') <= 2
ORDER BY edit_dist ASC;
```

**Nota:** Levenshtein sozinho é O(n) (seq scan). **Sempre usar trigram como pré-filtro** para reduzir o candidato set de milhões para centenas.

**Detecta:** `meubamco`, `meubanc0`, `neubanco`.

### 5.5. Homograph / Leet Speak Detection

Normalizar o label antes de comparar, usando tabela de substituição.

```python
HOMOGRAPH_MAP = {
    '0': 'o', '1': 'l', '3': 'e', '4': 'a', '5': 's',
    '7': 't', '8': 'b', '@': 'a', '$': 's',
    # Unicode confusables (subset)
    'ο': 'o',  # Greek omicron
    'а': 'a',  # Cyrillic a
    'е': 'e',  # Cyrillic e
    'і': 'i',  # Cyrillic i
    # ... tabela completa de confusables
}

def normalize_homograph(label: str) -> str:
    return ''.join(HOMOGRAPH_MAP.get(c, c) for c in label)
```

**Estratégia de busca:**
1. Normalizar o label da marca: `normalize_homograph("meubanco")` → `"meubanco"`
2. Para candidatos do trigram, normalizar e comparar
3. Ou: gerar variações homograph da marca e buscar por exact match

```sql
-- Checar se variações homograph existem
SELECT name FROM domain
WHERE name IN ('meubanc0.com', 'meub4nco.com', 'meubanc0.net', ...)
```

**Performance:** O(variações) = microsegundos (PK lookup).

### 5.6. Typosquatting Candidate Generation

Gerar todas as variações possíveis da marca e verificar existência.

```python
def generate_typo_candidates(brand: str) -> set[str]:
    """Gera variações de typosquatting para uma marca."""
    candidates = set()
    # 1. Character omission: "meubanco" → "meubaco", "meubano", ...
    for i in range(len(brand)):
        candidates.add(brand[:i] + brand[i+1:])
    # 2. Character duplication: "meubanco" → "meeubanco", "meuubanco", ...
    for i in range(len(brand)):
        candidates.add(brand[:i] + brand[i] + brand[i:])
    # 3. Character swap: "meubanco" → "emubanco", "muebanco", ...
    for i in range(len(brand) - 1):
        candidates.add(brand[:i] + brand[i+1] + brand[i] + brand[i+2:])
    # 4. Adjacent key substitution (QWERTY layout):
    QWERTY_ADJACENT = {
        'a': 'sqwz', 'b': 'vghn', 'c': 'xdfv', 'd': 'sfcxer',
        'e': 'wrsdf', 'f': 'dgcvrt', 'g': 'fhbvty', 'h': 'gjbnyu',
        # ... complete map
    }
    for i, c in enumerate(brand):
        for adj in QWERTY_ADJACENT.get(c, ''):
            candidates.add(brand[:i] + adj + brand[i+1:])
    # 5. Homograph substitutions
    for i, c in enumerate(brand):
        for variant in HOMOGRAPH_REVERSE_MAP.get(c, []):
            candidates.add(brand[:i] + variant + brand[i+1:])
    return candidates
```

```sql
-- Verificar quais variações existem na base
SELECT name FROM domain WHERE label IN (:candidates)
```

**Performance:** O(candidates × TLDs). Com ~500 candidatos × 10 TLDs = 5000 PK lookups = < 50ms.

**Detecta:** os typosquats mais clássicos com certeza.

### 5.7. Cross-TLD Detection

Uma marca em `.com` pode ser atacada via `.net`, `.org`, etc.

```sql
-- Para brand "meubanco.com.br", verificar em todos TLDs
SELECT name, tld, label
FROM domain
WHERE label = 'meubanco'
  AND tld != 'com.br'
ORDER BY tld;
```

**Performance:** PK index, microsegundos.

---

## 6. Quando (e como) usar pgvector

### Quando NÃO usar

- **Full table embedding:** 200M × 1.5KB = 715 GB. Não.
- **Busca de similaridade lexical:** trigram é mais rápido e mais barato.
- **Typosquatting/homograph:** candidato generation + exact match é mais preciso.

### Quando SIM usar (futuro, V2+)

| Caso | Exemplo | Por que trigram não pega |
|---|---|---|
| Tradução | "mybank" vs "meubanco" | Strings completamente diferentes |
| Sinônimos | "financeiro" vs "banking" | Sem overlap lexical |
| Semantic combos | "banco-digital" vs "meubanco" | Substring parcial |

### Como usar sem explodir o custo

**Opção A — Embedding on-the-fly no candidato set (recomendada para V2):**

```
1. Trigram + LIKE + Levenshtein → retorna ~10k candidatos
2. Compute embedding para os ~10k candidatos (batch inference)
3. Compare com embedding da marca monitorada
4. Score e rank
```

Custo: 10k × inferência = ~1-2 segundos com modelo local (MiniLM).
Storage: zero (embeddings não persistidos).

**Opção B — Embedding apenas para novos domínios (delta diário):**

```sql
CREATE TABLE domain_embedding (
    domain_name VARCHAR(253) PRIMARY KEY,
    embedding   vector(384) NOT NULL,
    computed_at TIMESTAMPTZ NOT NULL
);

-- Rotação: manter últimos 30 dias
-- 200k novos/dia × 1.5KB × 30 dias = ~9 GB
```

Worker diário:
1. Selecionar domínios com `first_seen_at > ontem`
2. Computar embeddings em batch
3. Inserir em `domain_embedding`
4. Buscar via pgvector ANN

**Opção C — Tabela de "domínios interessantes" (candidatos):**

Após a análise trigram/Levenshtein, domínios que tiveram score acima de um threshold mínimo ganham embedding:

```sql
-- Somente domínios que são candidatos para alguma marca
CREATE TABLE domain_enriched (
    domain_name VARCHAR(253) PRIMARY KEY,
    label_normalized VARCHAR(228),      -- homograph-normalized
    embedding   vector(384),
    entropy     FLOAT,                  -- label entropy score
    token_count SMALLINT,               -- number of words in label
    computed_at TIMESTAMPTZ NOT NULL
);
```

Volume estimado: ~1-5M domínios (os "suspeitos"). Storage: ~2-8 GB. **Viável.**

### Recomendação de faseamento

| Fase | Técnica | Cobertura | Custo |
|---|---|---|---|
| **V1 (MVP)** | Trigram + Levenshtein + LIKE + Typo generation + Homograph | ~90% dos ataques reais | ~2 GB de GIN index |
| **V2** | + Embedding on-the-fly para candidatos | +5% (semantic) | Custo de inferência (CPU) |
| **V3** | + Embedding persistido para delta diário | +3% (proativo) | ~9 GB storage |
| **V4** | + ML classifier para scoring avançado | +2% (reduz FP) | Modelo treinado |

---

## 7. Processamento Incremental — Watermark e Checkpoint

### O problema

Para uma marca monitorada, a **primeira varredura** precisa checar todos os ~200M domínios. As varreduras seguintes precisam checar apenas domínios **novos** desde a última vez.

### Modelo de watermark

```
Brand "meubanco" + TLD "net":
  watermark_at = 2026-03-19T00:00:00Z
  → Significa: todos domínios de .net com first_seen_at <= 2026-03-19 já foram verificados
  → Próxima varredura: somente WHERE first_seen_at > 2026-03-19
```

### Schema de controle

```sql
-- O que está sendo monitorado
CREATE TABLE monitored_brand (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL,          -- multi-tenant
    brand_name      VARCHAR(253) NOT NULL,  -- "MeuBanco"
    brand_label     VARCHAR(228) NOT NULL,  -- "meubanco" (normalized)
    keywords        TEXT[] NOT NULL DEFAULT '{}',  -- ["banco", "financeiro", "pix"]
    tld_scope       TEXT[] NOT NULL DEFAULT '{}',  -- TLDs a monitorar (vazio = todos)
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL,
    UNIQUE (organization_id, brand_name)
);

-- Cursor de progresso: onde o scan parou por brand × TLD
CREATE TABLE similarity_scan_cursor (
    brand_id        UUID NOT NULL REFERENCES monitored_brand(id) ON DELETE CASCADE,
    tld             VARCHAR(24) NOT NULL,
    scan_phase      VARCHAR(16) NOT NULL DEFAULT 'initial',
                    -- 'initial' = primeira varredura completa
                    -- 'delta'   = varreduras incrementais
    status          VARCHAR(16) NOT NULL DEFAULT 'pending',
                    -- 'pending' | 'running' | 'complete' | 'failed'
    watermark_at    TIMESTAMPTZ,
                    -- domínios com first_seen_at <= watermark_at já foram varridos
    resume_after    VARCHAR(253),
                    -- para retomada: último domain name processado no batch
    domains_scanned BIGINT NOT NULL DEFAULT 0,
    domains_matched BIGINT NOT NULL DEFAULT 0,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    error_message   TEXT,
    updated_at      TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (brand_id, tld)
);

-- Resultados: matches detectados
CREATE TABLE similarity_match (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brand_id          UUID NOT NULL REFERENCES monitored_brand(id) ON DELETE CASCADE,
    domain_name       VARCHAR(253) NOT NULL,
    tld               VARCHAR(24) NOT NULL,
    label             VARCHAR(228) NOT NULL,
    -- Scores
    score_final       FLOAT NOT NULL,          -- score composto
    score_trigram     FLOAT,                   -- pg_trgm similarity
    score_levenshtein FLOAT,                   -- 1 - (edit_dist / max_len)
    score_brand_hit   FLOAT,                   -- substring match? 0 ou 1
    score_keyword     FLOAT,                   -- keyword risk scoring
    score_homograph   FLOAT,                   -- homograph similarity
    -- Metadata
    reasons           TEXT[] NOT NULL,          -- ['typosquatting', 'brand_containment', ...]
    risk_level        VARCHAR(16) NOT NULL,     -- 'low' | 'medium' | 'high' | 'critical'
    first_detected_at TIMESTAMPTZ NOT NULL,
    domain_first_seen TIMESTAMPTZ NOT NULL,    -- quando o domínio apareceu na base
    -- Review workflow
    status            VARCHAR(16) NOT NULL DEFAULT 'new',
                      -- 'new' | 'reviewing' | 'dismissed' | 'confirmed_threat'
    reviewed_by       UUID,
    reviewed_at       TIMESTAMPTZ,
    notes             TEXT,
    UNIQUE (brand_id, domain_name)
);

CREATE INDEX ix_match_brand_risk ON similarity_match (brand_id, risk_level, score_final DESC);
CREATE INDEX ix_match_brand_status ON similarity_match (brand_id, status);
```

---

## 8. Fluxo do Similarity Worker

### 8.1. Scan Inicial (primeira vez para uma brand × TLD)

```
Para brand "meubanco", TLD "net":

1. SET cursor.status = 'running', cursor.scan_phase = 'initial'

2. SEARCH PHASE (usando GIN trigram index):
   a. Trigram:      SELECT * FROM domain WHERE tld='net' AND label % 'meubanco'
   b. Substring:    SELECT * FROM domain WHERE tld='net' AND label LIKE '%meubanco%'
   c. Levenshtein:  SELECT * FROM domain WHERE tld='net' AND label % 'meubanco'
                      AND levenshtein(label, 'meubanco') <= 3
   d. Typo check:   SELECT * FROM domain WHERE tld='net'
                      AND label IN (:generated_typo_candidates)
   e. Homograph:    SELECT * FROM domain WHERE tld='net'
                      AND label IN (:generated_homograph_candidates)
   f. Keyword:      SELECT * FROM domain WHERE tld='net'
                      AND label LIKE '%meubanco%'
                      AND (label LIKE '%login%' OR label LIKE '%secure%' OR ...)

3. UNION ALL results, deduplicate by domain_name

4. SCORE each candidate:
   score_final = 0.30 * trigram
               + 0.25 * levenshtein_norm
               + 0.20 * brand_hit
               + 0.15 * keyword_risk
               + 0.10 * homograph

5. FILTER: score_final >= 0.3 (configurable threshold)

6. INSERT INTO similarity_match (upsert: ON CONFLICT DO UPDATE scores)

7. UPDATE cursor:
   watermark_at = MAX(first_seen_at) from domain WHERE tld='net'
   status = 'complete'
   scan_phase = 'delta'  -- próxima vez será incremental
```

**Tempo estimado do scan inicial:** < 5 segundos por brand × TLD (com GIN index).

### 8.2. Scan Incremental (delta — diário)

```
Para brand "meubanco", TLD "net" (watermark_at = 2026-03-19):

1. SET cursor.status = 'running'

2. SAME SEARCHES as initial, BUT with additional filter:
   AND first_seen_at > :watermark_at

3. Volume: somente domínios novos desde o último scan
   ~0.1-0.5% do total = ~13k-65k para .net

4. SCORE, FILTER, INSERT (same logic)

5. UPDATE cursor:
   watermark_at = MAX(first_seen_at) from new domains
   domains_scanned += count
   status = 'complete'
```

**Tempo estimado do scan delta:** < 1 segundo por brand × TLD.

### 8.3. Resume após falha

Se o worker crashar durante o scan:

```python
# No início do scan, verificar se há cursor com status='running'
cursor = get_cursor(brand_id, tld)

if cursor.status == 'running':
    # Retomar de onde parou
    if cursor.scan_phase == 'initial':
        # O scan inicial com GIN index é tão rápido que é mais eficiente
        # refazer inteiro do que manter checkpoints parciais
        # Simplesmente reiniciar o scan
        pass
    elif cursor.scan_phase == 'delta':
        # Delta é sempre rápido, refazer
        pass

# SET status = 'running' e prosseguir
```

**Decisão pragmática:** Tanto o scan inicial (~5s) quanto o delta (~1s) são rápidos o suficiente para que **reiniciar do zero** em caso de falha seja mais simples e seguro que manter checkpoints parciais. O cursor rastreia o **watermark** (quais domínios já foram processados entre runs), não o progresso **dentro** de um run.

Se no futuro o volume justificar checkpoints intra-scan (ex: .com com 160M domains e query mais complexa), adicionar o campo `resume_after` ao cursor para paginação.

### 8.4. Scheduler do Worker

```python
# Pseudocódigo do similarity worker

def run_similarity_scan():
    brands = get_active_brands()
    tlds = get_all_tlds()  # ou brand.tld_scope se filtrado

    for brand in brands:
        for tld in tlds:
            cursor = get_or_create_cursor(brand.id, tld)

            if cursor.scan_phase == 'initial' and cursor.status != 'complete':
                run_initial_scan(brand, tld, cursor)
            else:
                run_delta_scan(brand, tld, cursor)

# Schedule: rodar após cada ingestão bem-sucedida
# Ou: cron diário (ex: 2 horas após o sync CZDS das 07:00)
# Recomendação: trigger event-driven após sync_czds_tld terminar com sucesso
```

---

## 9. Modelo de Scoring (V1)

### Fórmula composta

```python
def compute_similarity_score(
    label: str,
    brand_label: str,
    brand_keywords: list[str],
) -> dict:
    """Computa scores de similaridade para um candidato."""

    # 1. Trigram similarity (0-1)
    trigram = pg_similarity(label, brand_label)  # via SQL

    # 2. Levenshtein normalized (0-1)
    max_len = max(len(label), len(brand_label))
    edit_dist = levenshtein(label, brand_label)
    lev_norm = 1.0 - (edit_dist / max_len) if max_len > 0 else 0

    # 3. Brand containment (0 or 1)
    brand_hit = 1.0 if brand_label in label else 0.0

    # 4. Keyword risk (0-1)
    RISK_KEYWORDS = {'login', 'secure', 'verify', 'account', 'password',
                     'confirm', 'auth', 'bank', 'update', 'support'}
    label_lower = label.lower()
    risk_words_found = [kw for kw in RISK_KEYWORDS if kw in label_lower]
    brand_kw_found = [kw for kw in brand_keywords if kw in label_lower]
    keyword_score = min(1.0, (len(risk_words_found) * 0.3 + len(brand_kw_found) * 0.2))

    # 5. Homograph similarity (0-1)
    norm_label = normalize_homograph(label)
    norm_brand = normalize_homograph(brand_label)
    homograph = 1.0 if norm_label == norm_brand else pg_similarity(norm_label, norm_brand)

    # Final composite
    final = (
        0.30 * trigram +
        0.25 * lev_norm +
        0.20 * brand_hit +
        0.15 * keyword_score +
        0.10 * homograph
    )

    # Risk level
    if final >= 0.85 or (brand_hit and keyword_score > 0):
        risk_level = 'critical'
    elif final >= 0.70:
        risk_level = 'high'
    elif final >= 0.50:
        risk_level = 'medium'
    else:
        risk_level = 'low'

    return {
        'score_final': final,
        'score_trigram': trigram,
        'score_levenshtein': lev_norm,
        'score_brand_hit': brand_hit,
        'score_keyword': keyword_score,
        'score_homograph': homograph,
        'risk_level': risk_level,
        'reasons': _detect_reasons(trigram, lev_norm, brand_hit, keyword_score, homograph),
    }


def _detect_reasons(trigram, lev, brand, keyword, homograph) -> list[str]:
    reasons = []
    if lev >= 0.7 and trigram >= 0.4:
        reasons.append('typosquatting')
    if brand >= 1.0:
        reasons.append('brand_containment')
    if keyword > 0:
        reasons.append('risky_keywords')
    if homograph >= 0.9 and homograph > trigram:
        reasons.append('homograph_attack')
    if not reasons:
        reasons.append('lexical_similarity')
    return reasons
```

### Pesos ajustáveis

Os pesos (0.30, 0.25, 0.20, 0.15, 0.10) devem ser configuráveis por organização ou globalmente. O V1 usa valores fixos. O V2+ pode usar pesos ajustados por feedback do usuário (quais matches foram confirmados como ameaças).

---

## 10. Otimização de Queries SQL (Batch)

Para eficiência, não executar 6 queries separadas. Combinar em uma única query:

```sql
-- Query unificada de candidatos para uma brand
WITH candidates AS (
    -- Trigram + Levenshtein
    SELECT DISTINCT name, tld, label, first_seen_at,
           similarity(label, :brand_label) AS sim_trigram,
           levenshtein(label, :brand_label) AS edit_dist
    FROM domain
    WHERE tld = :tld
      AND label % :brand_label

    UNION

    -- Substring match (brand containment)
    SELECT DISTINCT name, tld, label, first_seen_at,
           similarity(label, :brand_label) AS sim_trigram,
           levenshtein(label, :brand_label) AS edit_dist
    FROM domain
    WHERE tld = :tld
      AND label LIKE :brand_like  -- '%meubanco%'

    UNION

    -- Exact match typo/homograph candidates
    SELECT DISTINCT name, tld, label, first_seen_at,
           similarity(label, :brand_label) AS sim_trigram,
           levenshtein(label, :brand_label) AS edit_dist
    FROM domain
    WHERE tld = :tld
      AND label IN :typo_candidates
)
SELECT * FROM candidates
-- Para delta scan, adicionar:
-- WHERE first_seen_at > :watermark_at
ORDER BY sim_trigram DESC
LIMIT 5000;
```

Scoring é aplicado em Python sobre os ~5000 candidatos (in-memory, rápido).

---

## 11. Estrutura de Arquivos (Backend)

```
backend/app/
├── models/
│   ├── domain.py                    # (modificado: + label column)
│   ├── monitored_brand.py           # NOVO
│   ├── similarity_scan_cursor.py    # NOVO
│   └── similarity_match.py          # NOVO
├── repositories/
│   ├── domain_repository.py         # (modificado: label no upsert)
│   ├── monitored_brand_repository.py # NOVO
│   └── similarity_repository.py     # NOVO: queries de candidatos
├── services/
│   └── use_cases/
│       ├── apply_zone_delta.py      # (modificado: compute label)
│       ├── sync_czds_tld.py         # (modificado: trigger similarity após sucesso)
│       ├── run_similarity_scan.py   # NOVO: orchestração do scan
│       └── compute_similarity.py    # NOVO: scoring engine
├── worker/
│   ├── czds_ingestor.py             # existente
│   └── similarity_worker.py         # NOVO: scheduler de similarity scans
├── api/v1/routers/
│   ├── czds_ingestion.py            # existente
│   ├── similarity.py                # existente (consulta de resultados)
│   └── monitored_brands.py         # NOVO: CRUD de brands monitoradas
└── schemas/
    ├── similarity.py                # NOVO: request/response schemas
    └── monitored_brand.py           # NOVO
```

---

## 12. Análise de Custo Comparativa

### Opção A: pgvector full table (DESCARTADA)

| Item | Custo |
|---|---|
| Storage 200M embeddings | 286 GB |
| HNSW index | 429 GB |
| RAM para ANN | 200+ GB |
| GPU para gerar embeddings | Horas de inferência |
| **Total** | **715+ GB storage, servidor dedicado** |

### Opção B: pg_trgm + Levenshtein + geração de candidatos (RECOMENDADA)

| Item | Custo |
|---|---|
| Coluna label (200M) | 2.7 GB |
| GIN trigram index (200M) | ~10.5 GB |
| Tabelas de análise | < 1 GB |
| RAM adicional | Marginal (GIN in memory ~2-4 GB) |
| Computação | CPU only, < 5s por brand × TLD |
| **Total** | **~14 GB storage adicional, zero GPU** |

### Opção C: Híbrido V2 (pg_trgm + embedding on-the-fly)

| Item | Custo adicional sobre B |
|---|---|
| Modelo MiniLM (CPU inference) | ~200 MB RAM |
| Embedding do candidato set (~10k/brand) | ~1-2s CPU por scan |
| Storage | Zero (não persiste) |
| **Total** | **~200 MB RAM + tempo de CPU** |

---

## 13. Riscos e Mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| GIN index em 200M rows fica lento | Queries > 1s | Particionar por TLD (partition pruning) + monitorar query plans |
| Muitas brands monitoradas (1000+) | Total scan time cresce | Paralelizar: 1 worker por TLD, processar brands em batch |
| False positives alto | Usuário desconfia do produto | Threshold conservador (0.5), pesos ajustáveis, feedback loop |
| Domínio malicioso registrado e removido em 24h | Não detectado no delta diário | Reduzir intervalo de delta para 6h, ou processar CT Logs (real-time) |
| Label muito curto (2-3 chars) retorna milhares de trigram matches | Scan lento para esse brand | Threshold dinâmico: labels curtos exigem similarity > 0.6 |

---

## 14. Métricas de Sucesso

| Métrica | Target V1 | Como medir |
|---|---|---|
| Scan time por brand × TLD (initial) | < 10 s | Log no worker |
| Scan time por brand × TLD (delta) | < 2 s | Log no worker |
| False positive rate | < 30% dos "high/critical" | Review workflow (dismissed / total) |
| Coverage (ataques reais detectados) | > 85% | Testes com dataset de ataques conhecidos |
| Tempo até detecção de novo domínio suspeito | < 24 h | first_detected_at - domain_first_seen |

---

## 15. Decisões Explícitas

| Decisão | Escolha | Alternativa descartada | Motivo |
|---|---|---|---|
| Busca primária | pg_trgm GIN | pgvector ANN | 715 GB vs 13 GB. Trigram cobre 90%+ dos ataques. |
| Status na tabela domain | Derivado de last_seen_at | Coluna status/is_active | Elimina soft-delete, simplifica ingestão |
| PK da tabela domain | name (natural) | UUID (surrogate) | Elimina 1.2 GB de index, nenhuma FK referencia domain.id |
| Embedding | On-the-fly no candidate set (V2) | Pre-computed full table | Custo proibitivo para full table |
| Checkpoint de scan | Watermark por brand × TLD | Checkpoint intra-scan | Scans são rápidos (<10s), restart é mais simples |
| Scoring | Fórmula composta V1 | ML classifier | MVP primeiro, ML quando houver dados de feedback |

---

## 16. Checklist de Implementação

```
Fase 1 — Domain table redesign (pré-requisito):
  [ ] Implementar migration 005 (domain-table-redesign-proposal.md)
  [ ] Adicionar coluna label e GIN trigram index
  [ ] Instalar extensions: pg_trgm, fuzzystrmatch
  [ ] Validar queries de similaridade com dados reais
  [ ] Medir performance com EXPLAIN ANALYZE

Fase 2 — Similarity infrastructure:
  [ ] Criar models: monitored_brand, similarity_scan_cursor, similarity_match
  [ ] Criar migration 006 com tabelas de análise
  [ ] Criar repositories: monitored_brand_repository, similarity_repository
  [ ] Implementar run_similarity_scan.py (orchestração)
  [ ] Implementar compute_similarity.py (scoring engine)
  [ ] Implementar homograph normalization + typo candidate generation

Fase 3 — Worker e API:
  [ ] Criar similarity_worker.py (scheduler)
  [ ] Criar router monitored_brands.py (CRUD)
  [ ] Criar router similarity.py (consulta de matches)
  [ ] Integrar: após sync_czds_tld sucesso → trigger similarity scan

Fase 4 — Validação:
  [ ] Testar com brands reais (google, facebook, itau, nubank)
  [ ] Medir precision/recall com dataset de ataques conhecidos
  [ ] Medir performance em escala (31M domains)
  [ ] Validar workflow de review (new → confirmed/dismissed)

Fase 5 — V2 (pós-MVP):
  [ ] Adicionar embedding on-the-fly para candidatos (MiniLM)
  [ ] Ajustar pesos de scoring com dados de feedback
  [ ] Dashboard operacional de scans
```
