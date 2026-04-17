# 007 — Plano de Implementacao Detalhado

## Seed-First Candidate Retrieval + Pausa da LLM Granular

> Revisao pre-implementacao baseada na analise completa do codebase atual.
> Este documento contem todos os detalhes necessarios para executar a implementacao.

---

## Sumario

- [Diagnostico do Codebase Atual](#diagnostico-do-codebase-atual)
- [Fase 0 — Pausa da LLM Granular](#fase-0--pausa-da-llm-granular)
- [Fase 1 — Seed-First Deterministic Retrieval](#fase-1--seed-first-deterministic-retrieval)
- [Fase 2 — LLM Seed Generation](#fase-2--llm-seed-generation)
- [Mapa de Arquivos](#mapa-de-arquivos)
- [Verificacao End-to-End](#verificacao-end-to-end)

---

## Diagnostico do Codebase Atual

### Seed System — Estado Atual

**Arquivo:** `backend/app/services/monitoring_profile.py`

Seed types existentes e seus pesos (`SEED_BASE_WEIGHTS`, linha 25):

| seed_type | base_weight | Participa do scan? |
|-----------|-------------|-------------------|
| `domain_label` | 1.00 | Sim |
| `hostname_stem` | 0.95 | Nao (channel = certificate_hostname) |
| `brand_primary` | 0.90 | Sim |
| `official_domain` | 0.85 | Nao (channel = certificate_hostname) |
| `brand_phrase` | 0.80 | Sim |
| `brand_alias` | 0.65 | Sim |
| `support_keyword` | 0.20 | Nao (excluido do allowed_types) |

**`iter_scan_seeds()`** (linha 323) — filtra seeds para scan:
```python
allowed_types = {"domain_label", "brand_primary", "brand_alias", "brand_phrase"}
# Filtros: is_active, channel_scope in SCAN_CHANNELS_FOR_DOMAIN_TABLE, len >= 3
# Ordena: (base_weight, seed_type, seed_value) desc
```

**`SCAN_CHANNELS_FOR_DOMAIN_TABLE`** = `{"registrable_domain", "associated_brand", "both"}`

**`build_seed_rows()`** (linha 207) — gera seeds a partir de domains + aliases:
- Dedup via set `seen: set[tuple[str, str, str]]` — key: `(normalized_value, seed_type, channel_scope)`
- Normalizacao: `normalize_brand_text()` para aliases (NFKD + strip accents + lowercase + remove non-alnum)
- Normalizacao: `.strip().lower()` para domains
- `source_ref_type`: `"official_domain"` ou `"alias"`
- `source_ref_id`: UUID do domain ou alias de origem (nullable)

**MonitoredBrandSeed model** (`backend/app/models/monitored_brand_seed.py`):

| Coluna | Tipo | Constraints |
|--------|------|-------------|
| `id` | UUID | PK |
| `brand_id` | UUID | FK → monitored_brand.id ON DELETE CASCADE |
| `source_ref_type` | String(24) | NOT NULL |
| `source_ref_id` | UUID | NULLABLE |
| `seed_value` | String(253) | NOT NULL |
| `seed_type` | String(32) | NOT NULL |
| `channel_scope` | String(32) | NOT NULL |
| `base_weight` | Float | NOT NULL |
| `is_manual` | Boolean | NOT NULL, DEFAULT FALSE |
| `is_active` | Boolean | NOT NULL, DEFAULT TRUE |
| `created_at` | DateTime(tz) | NOT NULL |
| `updated_at` | DateTime(tz) | NOT NULL |

**Unique constraint:** `uq_brand_seed_unique` em `(brand_id, seed_value, seed_type, channel_scope)`
**Index:** `ix_brand_seed_channel` em `(brand_id, channel_scope, is_active)`

**Implicacao critica:** `seed_type` e `String(32)` (varchar), NAO enum PostgreSQL. Novos valores podem ser inseridos sem migracao Alembic. O mesmo vale para `source_ref_type` (String(24)).

---

### Retrieval — Estado Atual

**Arquivo:** `backend/app/repositories/similarity_repository.py`

`fetch_candidates()` (linha 73) — executa 3 sub-queries com savepoint isolation:

1. **Trigram** (`%` operator via GIN index):
   ```sql
   SELECT DISTINCT name, tld, label, first_seen_at,
          similarity(label, :brand_label) AS sim_trigram,
          levenshtein(label, :brand_label) AS edit_dist
   FROM domain
   WHERE tld = :tld AND label % :brand_label
     AND label NOT LIKE '%.%'  -- exclui subdomains
     AND first_seen_at > :watermark_at  -- delta scan
   LIMIT :limit
   ```

2. **Substring** (LIKE):
   ```sql
   WHERE tld = :tld AND label LIKE '%{brand}%'
   ```

3. **Typo exact** (= ANY):
   ```sql
   WHERE tld = :tld AND label = ANY(:typo_candidates)
   ```

**Dynamic similarity threshold** (por tamanho do brand):
- brand <= 5 chars: 0.55
- brand 6-8 chars: 0.45
- brand > 8 chars: 0.35

**Per-TLD query timeouts:**
- `.com`: 600s (170M+ rows)
- `.net`, `.org`: 300s
- `.com.br`: 180s
- `.info`, `.br`: 120s
- Outros: 45s

**Dedup**: merge 3 resultados, keep highest `sim_trigram` por domain name.

---

### Scan Orchestration — Estado Atual

**Arquivo:** `backend/app/services/use_cases/run_similarity_scan.py`

Fluxo completo:
1. Get/create cursor para brand x TLD
2. Determinar watermark (delta vs full)
3. `iter_scan_seeds()` — filtrar seeds elegiveis
4. Per-seed limit: `max(250, min(1500, int(5000 / len(scan_seeds))))`
5. **Loop por seed:**
   - `generate_typo_candidates(seed.seed_value)` — gera variantes
   - `repo.fetch_candidates(brand_label=seed.seed_value, ...)` — 3 sub-queries
   - Score via `compute_seeded_scores()`:
     - Base: `0.30*trigram + 0.25*levenshtein + 0.20*brand_hit + 0.15*keyword + 0.10*homograph`
     - Ajustado: `0.70*base + 0.20*seed_weight + 0.10*channel_multiplier`
   - Dedup por domain: keep highest `score_final`, tiebreak by `seed.base_weight`
6. Upsert matches (batch 500)
7. Cleanup subdomains + reconcile
8. Atualizar watermark

**Threshold por noise_mode:** conservative=0.60, standard=0.50, broad=0.42

---

### Typo Candidate Generation — Estado Atual

**Arquivo:** `backend/app/services/use_cases/compute_similarity.py` (linha 85)

`generate_typo_candidates()` gera:
1. Character omission (remove 1 char)
2. Character duplication (duplica 1 char)
3. Adjacent character swap (troca 2 adjacentes)
4. QWERTY adjacent key substitution
5. Homograph substitutions (via `HOMOGRAPH_REVERSE`)

**HOMOGRAPH_MAP** (linha 17): leet speak (0→o, 1→l, 3→e...) + Cyrillic (а→a, е→e, о→o...) + Greek (ο→o, α→a...) + visual (ı→i, ł→l)

**RISK_KEYWORDS** (linha 48): login, secure, verify, update, account, bank, password, confirm, auth, signin, support, help, official, alert, recover, payment, billing, wallet, transfer, reset

---

### LLM Assessment — Estado Atual (2 caminhos)

**Caminho 1 — Enrichment inline:**
- `backend/app/services/use_cases/enrich_similarity_match.py` (linhas 131-141)
- Chama `generate_llm_assessment()` no final do enrichment
- Skip para self-owned domains
- Resultado vai para `similarity_match.llm_assessment` (JSONB nullable)

**Caminho 2 — Assessment worker async:**
- `backend/app/worker/assessment_worker.py`
- Roda a cada 15 min via APScheduler
- Batch de 10 snapshots (immediate_attention + defensive_gap)
- Triggers: sem LLM, fingerprint mudou, ou > 7 dias
- Resultado vai para `match_state_snapshot.llm_assessment`

**Gate central:** `should_generate_assessment()` em `generate_llm_assessment.py` (linha 41):
- Requer API key configurada
- Requer risk_level in {medium, high, critical} OR attention_bucket in {immediate_attention, defensive_gap}

**Config LLM atual** (`config.py` linhas 150-153):
```python
OPENROUTER_API_KEY: str = ""
OPENROUTER_TIMEOUT_SECONDS: float = 20.0
OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
```

**Feature flags existentes no codebase** (padrao: booleans em env):
```python
CT_CERTSTREAM_ENABLED: bool = True     # linha 76
SIMILARITY_SCAN_ENABLED: bool = True   # linha 91
CT_CRTSH_ENABLED: bool = True          # linha 80
```

---

### Scoring — Estado Atual

**Arquivo:** `backend/app/services/use_cases/compute_similarity.py`

Pesos:
```python
W_TRIGRAM = 0.30
W_LEVENSHTEIN = 0.25
W_BRAND_HIT = 0.20
W_KEYWORD = 0.15
W_HOMOGRAPH = 0.10
```

`compute_scores()` — calcula score composto por candidato:
- trigram (pre-computado no SQL)
- levenshtein normalizado (0-1)
- brand_hit: boundary-aware containment (`_has_brand_boundary_match`)
- keyword risk: RISK_KEYWORDS + brand keywords
- homograph: `normalize_homograph()` + levenshtein proxy

`compute_seeded_scores()` — ajusta com contexto do seed:
```python
adjusted = 0.70 * base + 0.20 * seed_weight + 0.10 * channel_multiplier
```

**Channel multipliers** (`monitoring_profile.py` linha 35):
```python
"registrable_domain": 1.00
"certificate_hostname": 0.85
"associated_brand": 0.75
"both": 0.90
```

---

## Fase 0 — Pausa da LLM Granular

**Objetivo:** Cortar custo de LLM imediatamente sem quebrar nenhum fluxo.

### 0.1 — Feature flags

**Arquivo:** `backend/app/core/config.py`

Adicionar apos a secao `# -- LLM / OpenRouter` (apos linha 153, antes de `model_config`):

```python
    # ── LLM Feature Flags ────────────────────────────────────
    MATCH_LLM_ASSESSMENT_ENABLED: bool = False
    SEED_LLM_GENERATION_ENABLED: bool = False
```

- `MATCH_LLM_ASSESSMENT_ENABLED=false` desliga parecer LLM por dominio
- `SEED_LLM_GENERATION_ENABLED=false` desliga geracao de seeds por LLM (habilitado na Fase 2)

### 0.2 — Gate em should_generate_assessment()

**Arquivo:** `backend/app/services/use_cases/generate_llm_assessment.py`

Modificar `should_generate_assessment()` (linha 41) para checar a flag como primeira condicao:

```python
def should_generate_assessment(match: dict, api_key: str) -> bool:
    """Gate: only runs for medium+ risk matches with a configured API key."""
    from app.core.config import settings
    if not settings.MATCH_LLM_ASSESSMENT_ENABLED:
        return False

    if not api_key or not api_key.strip():
        return False

    risk_level = (match.get("risk_level") or "").lower()
    attention_bucket = (match.get("attention_bucket") or "").lower()

    return risk_level in _GATE_RISK_LEVELS or attention_bucket in _GATE_ATTENTION_BUCKETS
```

**Por que aqui e nao em cada caller?** Porque `should_generate_assessment()` ja e o chokepoint: tanto `enrich_similarity_match.py` quanto `assessment_worker.py` passam por `generate_llm_assessment()` → `should_generate_assessment()`. Um gate cobre ambos os caminhos.

### 0.3 — Early exit no assessment_worker

**Arquivo:** `backend/app/worker/assessment_worker.py`

Localizar a funcao `run_assessment_cycle()` e adicionar early return no inicio, antes de qualquer query ao banco:

```python
def run_assessment_cycle():
    from app.core.config import settings
    if not settings.MATCH_LLM_ASSESSMENT_ENABLED:
        logger.info("assessment_worker: MATCH_LLM_ASSESSMENT_ENABLED=false — skipping cycle")
        return
    # ... restante do codigo existente
```

**Por que tambem aqui se o gate em 0.2 ja cobre?** Porque o worker faz uma query `needs_llm_assessment()` para buscar snapshots candidatos ANTES de chamar `generate_llm_assessment()`. O early exit evita essa query desnecessaria, economizando DB load.

### 0.4 — Stack files

**Arquivo:** `infra/stack.dev.yml`

Adicionar no environment do servico backend (e assessment_worker se separado):

```yaml
MATCH_LLM_ASSESSMENT_ENABLED: "false"
SEED_LLM_GENERATION_ENABLED: "false"
```

**Arquivo:** `infra/stack.yml` (producao)

Mesmo ajuste. Default false garante que nao liga acidentalmente.

### 0.5 — Verificacao

1. Rodar enrichment — confirmar que `llm_assessment` retorna `None` sem erro
2. Rodar assessment_worker — confirmar log "skipping cycle" e zero queries
3. Verificar UI — `llm_assessment` ja e JSONB nullable, UI deve tratar ausencia como estado valido
4. Verificar `enrichment_summary.tools` — deve conter todos os tools normais (DNS, WHOIS, etc) sem LLM

---

## Fase 1 — Seed-First Deterministic Retrieval

**Objetivo:** Ampliar recall gerando mais candidatos relevantes sem depender de LLM.

### 1.1 — Expandir taxonomia de seeds

**Arquivo:** `backend/app/services/monitoring_profile.py`

#### 1.1.1 — Novos pesos em SEED_BASE_WEIGHTS (linha 25)

Adicionar ao dict existente:

```python
SEED_BASE_WEIGHTS: dict[str, float] = {
    # ── Existentes ──
    "domain_label": 1.00,
    "hostname_stem": 0.95,
    "brand_primary": 0.90,
    "official_domain": 0.85,
    "brand_phrase": 0.80,
    "brand_alias": 0.65,
    "support_keyword": 0.20,
    # ── Novas familias ──
    "homograph_base": 0.85,
    "typo_base": 0.80,
    "combo_brand_keyword": 0.75,
    "combo_keyword_brand": 0.70,
    "semantic_brand": 0.60,
    # ── LLM seeds (Fase 2) ──
    "llm_combo": 0.72,
    "llm_semantic": 0.58,
    "llm_social_engineering": 0.68,
}
```

#### 1.1.2 — Expandir allowed_types em iter_scan_seeds() (linha 324)

```python
def iter_scan_seeds(seeds: list[MonitoredBrandSeed]) -> list[MonitoredBrandSeed]:
    allowed_types = {
        # ── Existentes ──
        "domain_label", "brand_primary", "brand_alias", "brand_phrase",
        # ── Novas familias ──
        "combo_brand_keyword", "combo_keyword_brand",
        "typo_base", "homograph_base", "semantic_brand",
        # ── LLM seeds (Fase 2) ──
        "llm_combo", "llm_semantic", "llm_social_engineering",
    }
    result = [
        seed
        for seed in seeds
        if seed.is_active
        and seed.channel_scope in SCAN_CHANNELS_FOR_DOMAIN_TABLE
        and seed.seed_type in allowed_types
        and len(seed.seed_value) >= 3
    ]
    result.sort(key=lambda item: (item.base_weight, item.seed_type, item.seed_value), reverse=True)
    return result
```

#### 1.1.3 — Constantes para novas source_ref_types

Adicionar constantes (perto de `ALIAS_TYPES`):

```python
SYSTEM_SOURCE_REF_TYPES = {"system_rule", "combo_generator", "llm_seed"}
```

### 1.2 — Criar servico de geracao deterministica

**Novo arquivo:** `backend/app/services/seed_generation.py`

```python
"""Deterministic seed generation from brand profile.

Expands the base seeds (domain_label, brand_primary, etc.) into
candidate-oriented seeds: combos, typos, homographs.
"""

from __future__ import annotations

import logging
from app.services.monitoring_profile import (
    SEED_BASE_WEIGHTS,
    normalize_brand_text,
)
from app.services.use_cases.compute_similarity import (
    generate_typo_candidates,
    HOMOGRAPH_REVERSE,
    RISK_KEYWORDS,
)

logger = logging.getLogger(__name__)

# Prefixes/suffixes comuns em phishing e abuso de marca
ABUSE_PREFIXES = [
    "my", "meu", "portal", "acesso", "login", "painel",
    "app", "www", "secure", "oficial", "conta",
]
ABUSE_SUFFIXES = [
    "login", "online", "app", "web", "portal", "seguro",
    "oficial", "suporte", "help", "pay", "pagamento",
    "boleto", "fatura", "admin", "panel", "conta",
    "acesso", "reset", "verify", "update", "alert",
    "2via", "atendimento", "sac",
]

# Caps por familia para evitar explosao
MAX_COMBO_SEEDS = 120
MAX_TYPO_SEEDS = 50
MAX_HOMOGRAPH_SEEDS = 30


def generate_deterministic_seeds(
    brand_label: str,
    brand_aliases: list[str],
    brand_keywords: list[str],
) -> list[dict]:
    """Generate expanded seed rows from brand profile.

    Args:
        brand_label: Normalized primary brand label (e.g. "nubank").
        brand_aliases: Normalized brand aliases.
        brand_keywords: Brand-specific keywords (support_keyword values).

    Returns:
        List of seed row dicts ready for merge with build_seed_rows() output.
        Keys: source_ref_type, source_ref_id, seed_value, seed_type,
              channel_scope, base_weight.
    """
    seeds: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def _add(seed_value: str, seed_type: str, channel_scope: str = "registrable_domain") -> bool:
        """Add seed if not duplicate. Returns True if added."""
        normalized = normalize_brand_text(seed_value)
        if not normalized or len(normalized) < 3:
            return False
        key = (normalized, seed_type, channel_scope)
        if key in seen:
            return False
        seen.add(key)
        seeds.append({
            "source_ref_type": "system_rule",
            "source_ref_id": None,
            "seed_value": normalized,
            "seed_type": seed_type,
            "channel_scope": channel_scope,
            "base_weight": SEED_BASE_WEIGHTS.get(seed_type, 0.50),
        })
        return True

    # ── 1. Combo seeds: brand + keyword ────────────────────
    #    Usa RISK_KEYWORDS globais + brand_keywords especificas
    combo_keywords = list(RISK_KEYWORDS) + brand_keywords + ABUSE_SUFFIXES
    # Deduplica keywords
    combo_keywords_unique = list(dict.fromkeys(combo_keywords))

    combo_count = 0
    # Gerar combos para brand_label e aliases
    brand_cores = [brand_label] + [a for a in brand_aliases if a != brand_label]

    for core in brand_cores:
        if combo_count >= MAX_COMBO_SEEDS:
            break
        for kw in combo_keywords_unique:
            if combo_count >= MAX_COMBO_SEEDS:
                break
            # brand-keyword (com e sem separador)
            if _add(f"{core}-{kw}", "combo_brand_keyword"):
                combo_count += 1
            if _add(f"{core}{kw}", "combo_brand_keyword"):
                combo_count += 1
            # keyword-brand (com e sem separador)
            if _add(f"{kw}-{core}", "combo_keyword_brand"):
                combo_count += 1
            if _add(f"{kw}{core}", "combo_keyword_brand"):
                combo_count += 1

    # Prefixos de abuso
    for core in brand_cores:
        if combo_count >= MAX_COMBO_SEEDS:
            break
        for prefix in ABUSE_PREFIXES:
            if combo_count >= MAX_COMBO_SEEDS:
                break
            if _add(f"{prefix}{core}", "combo_keyword_brand"):
                combo_count += 1
            if _add(f"{prefix}-{core}", "combo_keyword_brand"):
                combo_count += 1

    logger.info("Generated %d combo seeds for brand=%s", combo_count, brand_label)

    # ── 2. Typo base seeds ─────────────────────────────────
    #    Reutiliza generate_typo_candidates() existente
    typo_count = 0
    for core in brand_cores[:2]:  # Apenas brand_label e first alias
        if typo_count >= MAX_TYPO_SEEDS:
            break
        typo_variants = generate_typo_candidates(core)
        # Priorizar variantes de single edit (mais plausivel)
        for variant in sorted(typo_variants, key=len):
            if typo_count >= MAX_TYPO_SEEDS:
                break
            if _add(variant, "typo_base"):
                typo_count += 1

    logger.info("Generated %d typo_base seeds for brand=%s", typo_count, brand_label)

    # ── 3. Homograph base seeds ────────────────────────────
    #    Reutiliza HOMOGRAPH_REVERSE existente
    homograph_count = 0
    for core in brand_cores[:1]:  # Apenas brand_label
        if homograph_count >= MAX_HOMOGRAPH_SEEDS:
            break
        for i, c in enumerate(core):
            if homograph_count >= MAX_HOMOGRAPH_SEEDS:
                break
            for variant_char in HOMOGRAPH_REVERSE.get(c, []):
                variant = core[:i] + variant_char + core[i + 1:]
                if _add(variant, "homograph_base"):
                    homograph_count += 1

    logger.info("Generated %d homograph_base seeds for brand=%s", homograph_count, brand_label)

    return seeds


def merge_seed_rows(
    base_seeds: list[dict],
    expanded_seeds: list[dict],
) -> list[dict]:
    """Merge base seeds with expanded seeds, base takes priority on conflict.

    Dedup key: (seed_value, seed_type, channel_scope)
    """
    seen: set[tuple[str, str, str]] = set()
    merged: list[dict] = []

    # Base seeds first (higher priority)
    for seed in base_seeds:
        key = (seed["seed_value"], seed["seed_type"], seed["channel_scope"])
        if key not in seen:
            seen.add(key)
            merged.append(seed)

    # Expanded seeds second (lower priority, skip conflicts)
    for seed in expanded_seeds:
        key = (seed["seed_value"], seed["seed_type"], seed["channel_scope"])
        if key not in seen:
            seen.add(key)
            merged.append(seed)

    return merged
```

### 1.3 — Integrar na sync_monitoring_profile

**Arquivo:** `backend/app/services/use_cases/sync_monitoring_profile.py`

Modificar `_apply_profile_components()` para chamar seed generation apos `build_seed_rows()`.

Localizacao atual (linhas 246-253):
```python
def _apply_profile_components(repo, brand, prepared):
    domains = repo.replace_domains(brand, prepared["domains"])
    aliases = repo.replace_aliases(brand, prepared["aliases"])
    repo.replace_seeds(brand, build_seed_rows(domains, aliases))
```

Novo codigo:
```python
def _apply_profile_components(repo, brand, prepared):
    domains = repo.replace_domains(brand, prepared["domains"])
    aliases = repo.replace_aliases(brand, prepared["aliases"])

    base_seeds = build_seed_rows(domains, aliases)

    # Expandir com seeds deterministicas (combos, typos, homographs)
    from app.services.seed_generation import generate_deterministic_seeds, merge_seed_rows

    # Extrair brand_label do perfil preparado
    brand_label = prepared.get("brand_label", "")
    if not brand_label and domains:
        brand_label = domains[0].registrable_label

    # Coletar aliases normalizados e keywords
    brand_aliases = [
        a.alias_normalized for a in aliases
        if a.alias_type in ("brand_primary", "brand_alias")
    ]
    brand_keywords = [
        a.alias_normalized for a in aliases
        if a.alias_type == "support_keyword"
    ]

    expanded_seeds = generate_deterministic_seeds(
        brand_label=brand_label,
        brand_aliases=brand_aliases,
        brand_keywords=brand_keywords,
    )

    all_seeds = merge_seed_rows(base_seeds, expanded_seeds)
    repo.replace_seeds(brand, all_seeds)
```

**Nota sobre `_prepare_profile_components()`**: Verificar se `brand_label` ja esta disponivel em `prepared`. Se nao, derivar de `compute_brand_label()` (linha 196 de `monitoring_profile.py`). O `prepared` dict precisa expor o brand_label calculado.

### 1.4 — Exact lookup no repository

**Arquivo:** `backend/app/repositories/similarity_repository.py`

Adicionar 2 novos metodos apos `fetch_candidates()`:

#### 1.4.1 — fetch_candidates_exact()

```python
def fetch_candidates_exact(
    self,
    candidate_labels: list[str],
    tld: str,
    *,
    watermark_at: datetime | None = None,
    limit: int = 2000,
) -> list[dict]:
    """Ring A/D: Exact label lookup for pre-generated candidates.

    Uses btree index on (tld, label) — very fast even on 170M+ row
    partitions. No trigram overhead.
    """
    if not candidate_labels:
        return []

    # Chunk labels to avoid exceeding PostgreSQL parameter limits
    # (max ~32k params, but keep practical at 1000 per batch)
    CHUNK_SIZE = 1000
    all_rows = []

    wm_filter = "AND first_seen_at > :watermark_at" if watermark_at else ""
    timeout_ms = _TLD_QUERY_TIMEOUT_MS.get(tld, _DEFAULT_QUERY_TIMEOUT_MS)

    sql = f"""
        SELECT DISTINCT name, tld, label, first_seen_at,
               similarity(label, label) AS sim_trigram,
               0 AS edit_dist
        FROM domain
        WHERE tld = :tld
          AND label = ANY(:candidates)
          AND label NOT LIKE '%.%'
          {wm_filter}
        LIMIT :limit
    """

    for i in range(0, len(candidate_labels), CHUNK_SIZE):
        chunk = candidate_labels[i:i + CHUNK_SIZE]
        params = {"tld": tld, "candidates": chunk, "limit": limit}
        if watermark_at:
            params["watermark_at"] = watermark_at

        rows = self._exec_candidate_part(
            sql, params,
            timeout_ms=timeout_ms,
            part_name="exact_lookup",
            tld=tld,
        )
        all_rows.extend(rows)

    # Dedup by name
    seen_names: dict[str, dict] = {}
    for row in all_rows:
        name = row[0]  # ou row.name dependendo do mapeamento
        if name not in seen_names:
            seen_names[name] = {
                "name": row[0],
                "tld": row[1],
                "label": row[2],
                "first_seen_at": row[3],
                "sim_trigram": 0.0,  # Exact match, trigram nao aplicavel
                "edit_dist": 0,
            }

    result = list(seen_names.values())
    return result[:limit]
```

**Nota importante sobre sim_trigram:** Para candidatos de exact lookup, o sim_trigram vindo do SQL nao e util (seria similarity(label, label) = 1.0 para self-match, que nao e o que queremos). O scoring correto acontece em `compute_seeded_scores()` que recalcula com base no seed original. Precisamos passar o `brand_label` do seed para o scoring, nao o label do candidato.

**Ajuste necessario:** A query deve computar `similarity(label, :brand_label)` e `levenshtein(label, :brand_label)` para manter compatibilidade com o scoring pipeline. Versao corrigida:

```python
    sql = f"""
        SELECT DISTINCT name, tld, label, first_seen_at,
               similarity(label, :brand_label) AS sim_trigram,
               levenshtein(label, :brand_label) AS edit_dist
        FROM domain
        WHERE tld = :tld
          AND label = ANY(:candidates)
          AND label NOT LIKE '%.%'
          {wm_filter}
        LIMIT :limit
    """
```

O `brand_label` precisa ser passado como parametro. Atualizar assinatura:

```python
def fetch_candidates_exact(
    self,
    candidate_labels: list[str],
    brand_label: str,  # Para calculo de similarity/levenshtein
    tld: str,
    *,
    watermark_at: datetime | None = None,
    limit: int = 2000,
) -> list[dict]:
```

#### 1.4.2 — fetch_candidates_punycode()

```python
def fetch_candidates_punycode(
    self,
    brand_label: str,
    tld: str,
    *,
    watermark_at: datetime | None = None,
    limit: int = 300,
) -> list[dict]:
    """Ring C: Find punycode/IDN domains for homograph analysis.

    Fetches domains starting with 'xn--' (punycode prefix) for comparison
    against brand after unicode normalization.
    """
    wm_filter = "AND first_seen_at > :watermark_at" if watermark_at else ""
    timeout_ms = _TLD_QUERY_TIMEOUT_MS.get(tld, _DEFAULT_QUERY_TIMEOUT_MS)

    sql = f"""
        SELECT DISTINCT name, tld, label, first_seen_at,
               similarity(label, :brand_label) AS sim_trigram,
               levenshtein(label, :brand_label) AS edit_dist
        FROM domain
        WHERE tld = :tld
          AND label LIKE 'xn--%%'
          AND label NOT LIKE '%.%'
          {wm_filter}
        LIMIT :limit
    """
    params: dict = {"tld": tld, "brand_label": brand_label, "limit": limit}
    if watermark_at:
        params["watermark_at"] = watermark_at

    rows = self._exec_candidate_part(
        sql, params,
        timeout_ms=timeout_ms,
        part_name="punycode_lookup",
        tld=tld,
    )

    return [
        {
            "name": row[0],
            "tld": row[1],
            "label": row[2],
            "first_seen_at": row[3],
            "sim_trigram": float(row[4]) if row[4] else 0.0,
            "edit_dist": int(row[5]) if row[5] else 0,
        }
        for row in rows
    ]
```

### 1.5 — Ring-based retrieval em run_similarity_scan

**Arquivo:** `backend/app/services/use_cases/run_similarity_scan.py`

Reestruturar o bloco principal da funcao `run_similarity_scan()`.

O loop existente (linhas 111-end) torna-se Ring B. Antes e depois dele, inserir os novos aneis.

```python
def run_similarity_scan(db, brand, tld, *, force_full=False):
    # ... setup existente ate linha 110 ...

    # ════════════════════════════════════════════════════════
    # Ring A — Exact Generated Candidates
    # ════════════════════════════════════════════════════════
    # Busca exata por seeds geradas (typo_base, homograph_base)
    ring_a_seed_types = {"typo_base", "homograph_base"}
    ring_a_seeds = [s for s in scan_seeds if s.seed_type in ring_a_seed_types]
    ring_a_labels = [s.seed_value for s in ring_a_seeds]

    if ring_a_labels:
        # Usar brand_label do seed de maior peso para similarity calc
        primary_brand_label = scan_seeds[0].seed_value  # Primeiro = maior peso
        ring_a_candidates = repo.fetch_candidates_exact(
            candidate_labels=ring_a_labels,
            brand_label=primary_brand_label,
            tld=tld,
            watermark_at=watermark_at,
            limit=2000,
        )
        logger.info("Ring A: %d exact candidates for tld=%s", len(ring_a_candidates), tld)

        for cand in ring_a_candidates:
            _process_candidate(
                cand, scan_seeds[0], brand, official_domains,
                threshold, now, best_matches_by_domain, candidate_domain_names,
            )

    # ════════════════════════════════════════════════════════
    # Ring B — Focused Fuzzy (loop existente, inalterado)
    # ════════════════════════════════════════════════════════
    fuzzy_seed_types = {"domain_label", "brand_primary", "brand_alias", "brand_phrase"}
    fuzzy_seeds = [s for s in scan_seeds if s.seed_type in fuzzy_seed_types]

    for seed in fuzzy_seeds:
        typo_candidates = list(generate_typo_candidates(seed.seed_value))
        candidates = repo.fetch_candidates(
            brand_label=seed.seed_value,
            tld=tld,
            typo_candidates=typo_candidates,
            watermark_at=watermark_at,
            limit=per_seed_limit,
        )
        # ... scoring e dedup existentes ...

    # ════════════════════════════════════════════════════════
    # Ring C — Homograph Retrieval
    # ════════════════════════════════════════════════════════
    # Busca dominios punycode e compara normalizacao com a marca
    primary_brand_label = scan_seeds[0].seed_value
    ring_c_candidates = repo.fetch_candidates_punycode(
        brand_label=primary_brand_label,
        tld=tld,
        watermark_at=watermark_at,
        limit=300,
    )
    if ring_c_candidates:
        logger.info("Ring C: %d punycode candidates for tld=%s", len(ring_c_candidates), tld)
        for cand in ring_c_candidates:
            _process_candidate(
                cand, scan_seeds[0], brand, official_domains,
                threshold, now, best_matches_by_domain, candidate_domain_names,
            )

    # ════════════════════════════════════════════════════════
    # Ring D — Combo/Context Retrieval
    # ════════════════════════════════════════════════════════
    combo_seed_types = {"combo_brand_keyword", "combo_keyword_brand"}
    combo_seeds = [s for s in scan_seeds if s.seed_type in combo_seed_types]
    combo_labels = [s.seed_value for s in combo_seeds]

    if combo_labels:
        ring_d_candidates = repo.fetch_candidates_exact(
            candidate_labels=combo_labels,
            brand_label=primary_brand_label,
            tld=tld,
            watermark_at=watermark_at,
            limit=500,
        )
        logger.info("Ring D: %d combo candidates for tld=%s", len(ring_d_candidates), tld)

        for cand in ring_d_candidates:
            # Encontrar o seed combo que melhor casa com este candidato
            matched_seed = _find_best_matching_seed(cand, combo_seeds) or scan_seeds[0]
            _process_candidate(
                cand, matched_seed, brand, official_domains,
                threshold, now, best_matches_by_domain, candidate_domain_names,
            )

    # ... restante: upsert, cleanup, watermark (inalterado) ...
```

**Funcao helper `_process_candidate()`** — Extrair logica repetida do loop existente:

```python
def _process_candidate(
    cand: dict,
    seed: MonitoredBrandSeed,
    brand: MonitoredBrand,
    official_domains: set[str],
    threshold: float,
    now: datetime,
    best_matches_by_domain: dict[str, dict],
    candidate_domain_names: set[str],
) -> None:
    """Score a candidate and update best_matches_by_domain if above threshold."""
    domain_name = cand["name"]
    candidate_domain_names.add(domain_name)

    if domain_name in official_domains:
        return

    scores = compute_seeded_scores(
        label=cand["label"],
        brand_label=seed.seed_value,
        brand_keywords=[],  # TODO: passar keywords da marca
        seed_weight=seed.base_weight,
        channel_scope=seed.channel_scope,
        trigram_sim=cand["sim_trigram"],
    )

    if scores["score_final"] < threshold:
        return

    # Dedup: manter match com maior score_final
    existing = best_matches_by_domain.get(domain_name)
    if existing:
        if (scores["score_final"], seed.base_weight) <= (
            existing["score_final"], existing.get("_seed_weight", 0)
        ):
            return

    matched_rule = pick_matched_rule(scores["reasons"], seed.channel_scope)
    bucket = compute_actionability(...)  # Usar funcao existente

    best_matches_by_domain[domain_name] = {
        # ... montar dict do match como no loop existente ...
    }
```

**Nota:** A implementacao exata de `_process_candidate` deve ser extraida do loop existente (linhas ~120-180 de run_similarity_scan.py) para evitar duplicacao. A logica de scoring, dedup e montagem do match dict permanece identica.

### 1.6 — Endpoints de seeds

**Arquivo:** `backend/app/api/v1/routers/monitored_brands.py`

#### POST /{brand_id}/seeds/regenerate

```python
@router.post("/{brand_id}/seeds/regenerate", response_model=BrandSeedGroupedResponse)
async def regenerate_brand_seeds(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    _admin = Depends(require_admin),
):
    """Re-generate deterministic seeds for a brand."""
    brand = _get_brand_or_404(db, brand_id)
    # Re-run profile sync which triggers seed generation
    from app.services.use_cases.sync_monitoring_profile import sync_monitoring_profile
    sync_monitoring_profile(db, brand)
    db.commit()
    return _group_seeds_by_family(brand.seeds)
```

#### GET /{brand_id}/seeds/preview

```python
@router.get("/{brand_id}/seeds/preview", response_model=SeedPreviewResponse)
async def preview_brand_seeds(
    brand_id: uuid.UUID,
    db: Session = Depends(get_db),
    _admin = Depends(require_admin),
):
    """Dry-run: show what seeds would be generated without persisting."""
    brand = _get_brand_or_404(db, brand_id)
    # Generate without persisting
    from app.services.seed_generation import generate_deterministic_seeds
    from app.services.monitoring_profile import build_seed_rows, compute_brand_label

    base_seeds = build_seed_rows(list(brand.domains or []), list(brand.aliases or []))
    brand_label = compute_brand_label(brand.brand_name, ...)

    expanded = generate_deterministic_seeds(
        brand_label=brand_label,
        brand_aliases=[a.alias_normalized for a in (brand.aliases or []) if a.alias_type in ("brand_primary", "brand_alias")],
        brand_keywords=[a.alias_normalized for a in (brand.aliases or []) if a.alias_type == "support_keyword"],
    )

    # Agrupar por familia
    families: dict[str, list[str]] = {}
    for seed in base_seeds + expanded:
        families.setdefault(seed["seed_type"], []).append(seed["seed_value"])

    return {"families": families, "total": sum(len(v) for v in families.values())}
```

#### Atualizar GET /{brand_id}/seeds

Adicionar agrupamento por familia na resposta existente.

**Arquivo:** `backend/app/schemas/monitored_brand.py`

```python
class BrandSeedGroupedResponse(BaseModel):
    by_family: dict[str, list[BrandSeedResponse]]
    total: int

class SeedPreviewResponse(BaseModel):
    families: dict[str, list[str]]
    total: int
```

---

## Fase 2 — LLM Seed Generation

**Objetivo:** Ampliar cobertura contextual usando LLM para gerar seeds que regras deterministicas nao capturam.

### 2.1 — Servico de geracao LLM

**Novo arquivo:** `backend/app/services/use_cases/generate_brand_seeds.py`

```python
"""LLM-powered seed generation for brand protection.

Uses OpenRouter to generate plausible attack domain patterns
that deterministic rules might miss. Gated by SEED_LLM_GENERATION_ENABLED.
"""

from __future__ import annotations

import json
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

MAX_LLM_SEEDS_PER_BRAND = 100
MIN_SEED_LENGTH = 3
MAX_SEED_LENGTH = 63

_PROMPT_TEMPLATE = """\
Voce e um especialista em seguranca cibernetica e brand protection.

Dado o perfil de uma marca, gere variacoes de dominios que um atacante real \
registraria para phishing, engenharia social ou uso indevido da marca.

MARCA: {brand_name}
DOMINIO OFICIAL: {official_domain}
SEGMENTO: {segment}
KEYWORDS DA MARCA: {keywords}

Gere APENAS nomes de dominio (sem TLD). Agrupe por categoria:

1. combo_brand_keyword: marca + palavra de acao (login, boleto, suporte, etc)
2. combo_keyword_brand: palavra + marca
3. semantic_brand: variacoes semanticas do negocio
4. social_engineering: nomes que simulam portal, area do cliente, etc

REGRAS:
- Maximo {max_seeds} seeds no total
- Apenas caracteres a-z, 0-9 e hifen
- Sem TLD (nao inclua .com, .br, etc)
- Foque em nomes plausives que enganariam um usuario real
- Considere o idioma principal da marca ({language})

Responda APENAS com JSON valido:
{{
  "llm_combo": ["seed1", "seed2"],
  "llm_semantic": ["seed1", "seed2"],
  "llm_social_engineering": ["seed1", "seed2"]
}}"""


def generate_llm_seeds(
    brand_name: str,
    official_domain: str,
    segment: str,
    keywords: list[str],
    *,
    language: str = "pt-BR",
    max_seeds: int = MAX_LLM_SEEDS_PER_BRAND,
) -> list[dict]:
    """Generate LLM-powered seeds for a brand.

    Returns list of seed row dicts with source_ref_type="llm_seed".
    Returns empty list if SEED_LLM_GENERATION_ENABLED is False.
    """
    if not settings.SEED_LLM_GENERATION_ENABLED:
        return []

    if not settings.OPENROUTER_API_KEY:
        logger.warning("SEED_LLM_GENERATION_ENABLED but no OPENROUTER_API_KEY")
        return []

    prompt = _PROMPT_TEMPLATE.format(
        brand_name=brand_name,
        official_domain=official_domain,
        segment=segment,
        keywords=", ".join(keywords) if keywords else "nenhuma",
        max_seeds=max_seeds,
        language=language,
    )

    # Chamar OpenRouter (reusar pattern de generate_llm_assessment.py)
    import httpx
    try:
        resp = httpx.post(
            f"{settings.OPENROUTER_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "anthropic/claude-sonnet-4-20250514",
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 2000,
                "temperature": 0.7,
            },
            timeout=settings.OPENROUTER_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.error("LLM seed generation failed: %s", exc)
        return []

    # Parse response
    try:
        content = resp.json()["choices"][0]["message"]["content"]
        # Extrair JSON do content (pode ter markdown wrapping)
        json_start = content.index("{")
        json_end = content.rindex("}") + 1
        data = json.loads(content[json_start:json_end])
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        logger.error("Failed to parse LLM seed response: %s", exc)
        return []

    # Validar e converter para seed rows
    seeds: list[dict] = []
    seen: set[str] = set()

    from app.services.monitoring_profile import normalize_brand_text, SEED_BASE_WEIGHTS

    for seed_type in ("llm_combo", "llm_semantic", "llm_social_engineering"):
        values = data.get(seed_type, [])
        if not isinstance(values, list):
            continue
        for raw_value in values:
            if not isinstance(raw_value, str):
                continue
            normalized = normalize_brand_text(raw_value)
            if not normalized or len(normalized) < MIN_SEED_LENGTH or len(normalized) > MAX_SEED_LENGTH:
                continue
            if normalized in seen:
                continue
            seen.add(normalized)
            seeds.append({
                "source_ref_type": "llm_seed",
                "source_ref_id": None,
                "seed_value": normalized,
                "seed_type": seed_type,
                "channel_scope": "registrable_domain",
                "base_weight": SEED_BASE_WEIGHTS.get(seed_type, 0.60),
            })

    logger.info(
        "LLM seed generation for brand=%s: %d seeds generated",
        brand_name, len(seeds),
    )
    return seeds[:max_seeds]
```

### 2.2 — Integrar no profile sync

**Arquivo:** `backend/app/services/use_cases/sync_monitoring_profile.py`

Apos a integracao da Fase 1 (deterministic seeds), adicionar:

```python
    # ── LLM seed generation (Fase 2) ──
    if settings.SEED_LLM_GENERATION_ENABLED:
        from app.services.use_cases.generate_brand_seeds import generate_llm_seeds
        llm_seeds = generate_llm_seeds(
            brand_name=brand.brand_name,
            official_domain=brand.domains[0].domain_name if brand.domains else "",
            segment=getattr(brand, "segment", ""),
            keywords=brand_keywords,
        )
        all_seeds = merge_seed_rows(all_seeds, llm_seeds)
```

### 2.3 — Regeneracao via API

Estender `POST /{brand_id}/seeds/regenerate` com query param:

```python
@router.post("/{brand_id}/seeds/regenerate")
async def regenerate_brand_seeds(
    brand_id: uuid.UUID,
    include_llm: bool = Query(True, description="Include LLM seed generation"),
    db: Session = Depends(get_db),
):
```

Se `include_llm=True` e `SEED_LLM_GENERATION_ENABLED=true`, chamar `generate_llm_seeds()` alem das deterministicas.

---

## Mapa de Arquivos Completo

### Fase 0 — Pausa LLM (4 arquivos modificados)

| Arquivo | Mudanca |
|---------|---------|
| `backend/app/core/config.py` | +2 feature flags |
| `backend/app/services/use_cases/generate_llm_assessment.py` | +gate em should_generate_assessment() |
| `backend/app/worker/assessment_worker.py` | +early exit em run_assessment_cycle() |
| `infra/stack.dev.yml` + `infra/stack.yml` | +env vars |

### Fase 1 — Seed-First Retrieval (6 arquivos modificados, 1 novo)

| Arquivo | Mudanca |
|---------|---------|
| `backend/app/services/monitoring_profile.py` | +SEED_BASE_WEIGHTS, +allowed_types |
| **`backend/app/services/seed_generation.py`** | **NOVO** — geracao deterministica |
| `backend/app/services/use_cases/sync_monitoring_profile.py` | +chamada seed_generation + merge |
| `backend/app/repositories/similarity_repository.py` | +fetch_candidates_exact(), +fetch_candidates_punycode() |
| `backend/app/services/use_cases/run_similarity_scan.py` | +ring-based retrieval A/B/C/D |
| `backend/app/api/v1/routers/monitored_brands.py` | +regenerate, +preview endpoints |
| `backend/app/schemas/monitored_brand.py` | +BrandSeedGroupedResponse, +SeedPreviewResponse |

### Fase 2 — LLM Seeds (2 arquivos modificados, 1 novo)

| Arquivo | Mudanca |
|---------|---------|
| **`backend/app/services/use_cases/generate_brand_seeds.py`** | **NOVO** — LLM seed generation |
| `backend/app/services/use_cases/sync_monitoring_profile.py` | +chamada LLM seeds |
| `backend/app/api/v1/routers/monitored_brands.py` | +param include_llm |

---

## Verificacao End-to-End

### Fase 0
1. Com `MATCH_LLM_ASSESSMENT_ENABLED=false`:
   - Executar enrichment → `llm_assessment` retorna `None`
   - Executar assessment_worker → log "skipping cycle", zero queries
   - UI mostra matches sem parecer LLM sem erro

### Fase 1
1. Criar/editar marca via API
2. `GET /v1/brands/{id}/seeds` → verificar seeds expandidas por familia
3. `GET /v1/brands/{id}/seeds/preview` → verificar dry-run
4. Executar scan → verificar logs de Ring A, B, C, D
5. Verificar matches novos vindos de candidatos exact (Ring A)
6. Verificar matches novos vindos de combos (Ring D)
7. Watermark/delta preservado — verificar cursor apos scan

### Fase 2
1. Setar `SEED_LLM_GENERATION_ENABLED=true`
2. `POST /v1/brands/{id}/seeds/regenerate?include_llm=true`
3. Verificar seeds LLM persistidas com `source_ref_type="llm_seed"`
4. Verificar que LLM seeds participam do scan via Ring A/D
5. Cap de seeds respeitado (MAX_LLM_SEEDS_PER_BRAND)

### Geral
- Score threshold e noise_mode inalterados
- Upsert/dedup por domain_name preservado
- assessment_worker nao gera custo quando flag desligada
- Nenhuma migracao Alembic necessaria (varchar columns aceitam novos valores)

---

## Decisoes de Design Documentadas

### Por que combos no seed creation time e nao no scan time?
- Seeds ficam persistidas e auditaveis via API
- Dedup acontece uma vez na criacao
- Scan nao precisa gerar combos por TLD (economia de CPU)
- Admin pode desativar seed especifica

### Por que gate unico em should_generate_assessment()?
- Chokepoint natural: ambos os caminhos (enrichment + worker) passam por ele
- Um gate cobre tudo, menor risco de esquecer um caminho
- Early exit no worker e redundante mas economiza query ao banco

### Por que nao Alembic migration?
- `seed_type` e `String(32)` varchar, nao enum
- `source_ref_type` e `String(24)` varchar
- Unique constraint funciona com novos valores automaticamente
- Menor risco operacional, deploy mais rapido

### Por que Ring A usa exact match e nao fuzzy?
- Candidatos gerados (typo_base, homograph_base) ja sao variantes
- Exact match usa btree index — ordens de magnitude mais rapido que trigram GIN
- Cobre o gap de "dominios que existem exatamente como previsto"
- Fuzzy continua no Ring B para dominios nao antecipados

### Cap de seeds por familia
- Combos: MAX_COMBO_SEEDS = 120 (evita explosao combinatoria)
- Typos: MAX_TYPO_SEEDS = 50 (single-edit mais plausivel)
- Homographs: MAX_HOMOGRAPH_SEEDS = 30 (mapa finito de confusables)
- LLM: MAX_LLM_SEEDS_PER_BRAND = 100 (controlado por prompt + cap)
