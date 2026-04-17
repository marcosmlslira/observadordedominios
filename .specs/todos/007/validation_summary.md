# Todo 007 — Validation Summary

**Feature:** Seed-First Candidate Retrieval + LLM Pause  
**Status:** Implemented — ready for review

---

## What Was Implemented

### Phase 0 — Feature Flags (LLM Cost Kill Switch)

Two boolean env vars added, both defaulting to `False`:

| Flag | Default | Purpose |
|---|---|---|
| `MATCH_LLM_ASSESSMENT_ENABLED` | `false` | Gates LLM threat assessment in `generate_llm_assessment.py` |
| `SEED_LLM_GENERATION_ENABLED` | `false` | Gates LLM seed generation in `generate_brand_seeds.py` |

**Files changed:**
- `backend/app/core/config.py` — added both flags
- `backend/app/services/use_cases/generate_llm_assessment.py` — early return if flag off
- `backend/app/worker/assessment_worker.py` — early exit if flag off
- `infra/stack.dev.yml` — both flags on `backend` and `assessment_worker` services
- `infra/stack.yml` — both flags on `backend` service

**How to validate Phase 0:**
```bash
# Default (both off) — no OpenRouter calls should happen
# Check logs for: "LLM assessment disabled by feature flag"
# Check logs for: "MATCH_LLM_ASSESSMENT_ENABLED=False, skipping assessment cycle"

# To enable LLM assessment:
# MATCH_LLM_ASSESSMENT_ENABLED=true in stack env
```

---

### Phase 1 — Deterministic Seed Expansion + Ring-Based Scan

#### 1a. New Seed Types

`monitoring_profile.py` now defines 8 new seed types in `SEED_BASE_WEIGHTS`:

| Seed Type | Strategy | Description |
|---|---|---|
| `combo_brand_keyword` | exact btree | brand + risk keyword combos |
| `combo_keyword_brand` | exact btree | keyword + brand combos |
| `typo_base` | exact btree | keyboard/visual typos of brand label |
| `homograph_base` | exact btree | unicode lookalike characters |
| `brand_primary` | fuzzy trigram | official primary brand name |
| `brand_alias` | fuzzy trigram | known aliases |
| `brand_phrase` | fuzzy trigram | longer brand phrases |
| `domain_label` | fuzzy trigram | existing official domain labels |

#### 1b. `seed_generation.py` (NEW)

`generate_deterministic_seeds(brand_label, brand_aliases, brand_keywords)`:
- **Combo section** (max 120): `{brand}+{keyword}`, `{keyword}+{brand}`, `{alias}+{keyword}`, etc.
- **Typo section** (max 50): uses `generate_typo_candidates()` from `compute_similarity.py`
- **Homograph section** (max 30): uses `HOMOGRAPH_REVERSE` ASCII→unicode mapping

`merge_seed_rows(base, expanded)`:
- Dedup by `(seed_value, seed_type, channel_scope)` — base seeds take priority

#### 1c. `sync_monitoring_profile.py` update

`_apply_profile_components()` now runs the full seed pipeline:
1. `replace_domains()` + `replace_aliases()`
2. `build_seed_rows()` → base seeds (existing behavior)
3. `generate_deterministic_seeds()` → expanded seeds
4. Optional: `generate_llm_seeds()` if `SEED_LLM_GENERATION_ENABLED=true`
5. `merge_seed_rows()` → dedup
6. `replace_seeds()` → persist

New public function `regenerate_seeds_for_brand(repo, brand)` added to trigger seed regeneration without modifying brand metadata.

#### 1d. `similarity_repository.py` — New Retrieval Methods

`fetch_candidates_exact(seeds, brand_label)`:
- Batches labels in 1000-chunk queries via `label = ANY(:labels)` btree lookup
- Scores each hit with `similarity()` + `levenshtein()` against `brand_label`

`fetch_candidates_punycode(best_homograph_seed)`:
- Filters `label LIKE 'xn--%'` for IDN domains
- Scores against the provided homograph seed label

#### 1e. `run_similarity_scan.py` — Ring-Based Retrieval

Four retrieval rings per scan:

| Ring | Seed types | Method | Limit |
|---|---|---|---|
| A | `typo_base`, `homograph_base` | exact btree | 2000 |
| B | `domain_label`, `brand_primary`, `brand_alias`, `brand_phrase` | fuzzy trigram | (existing) |
| C | always active | punycode IDN scan | 300 |
| D | `combo_brand_keyword`, `combo_keyword_brand` | exact btree | 500 |

New helpers:
- `_process_candidate()` — unified scoring + actionability check
- `_find_best_matching_seed()` — maps a candidate label back to best combo seed

#### 1f. New API Endpoints

`POST /api/v1/brands/{brand_id}/seeds/regenerate`
- Triggers `regenerate_seeds_for_brand()` and returns grouped seeds
- Response: `BrandSeedGroupedResponse` (seeds grouped by family/type)
- `?include_llm=true/false` query param (respected when flag is on)

`GET /api/v1/brands/{brand_id}/seeds/preview`
- Dry-run: returns deterministic seeds WITHOUT persisting
- Response: `SeedPreviewResponse`

**How to validate Phase 1:**
```bash
# After deploying, for any existing brand:
curl -X POST /api/v1/brands/{brand_id}/seeds/regenerate

# Response should show seeds grouped by family:
# { "by_family": { "combo_brand_keyword": [...], "typo_base": [...], ... }, "total": N }

# Preview without persisting:
curl /api/v1/brands/{brand_id}/seeds/preview
```

---

### Phase 2 — LLM-Powered Seed Generation

`generate_brand_seeds.py` (NEW):
- Called only when `SEED_LLM_GENERATION_ENABLED=true`
- Uses OpenRouter (`anthropic/claude-sonnet-4-20250514`) via `httpx`
- Prompt requests 3 seed categories: `llm_combo`, `llm_semantic`, `llm_social_engineering`
- JSON response parsed with markdown fence fallback regex
- Returns seed rows with `source_ref_type="llm_seed"`

**How to validate Phase 2:**
```bash
# Set SEED_LLM_GENERATION_ENABLED=true + OPENROUTER_API_KEY in stack env
# Trigger seed regeneration:
curl -X POST /api/v1/brands/{brand_id}/seeds/regenerate?include_llm=true

# Seeds with source_ref_type="llm_seed" should appear in response
```

---

## Key Design Decisions

1. **No DB migrations needed** — seed_type and source_ref_type are `VARCHAR(32)` / `VARCHAR(24)`, new values work without Alembic changes.

2. **Both flags default to `False`** — safe rollout, no behavior change on existing deploys.

3. **SYSTEM_SOURCE_REF_TYPES** constant in `monitoring_profile.py` identifies auto-generated seeds: `{"system_rule", "combo_generator", "llm_seed"}`. These are regenerated on each profile sync; user-defined seeds are preserved.

4. **`merge_seed_rows()` priority** — base seeds (from `build_seed_rows()`) take priority over expanded seeds when there's a key collision on `(seed_value, seed_type, channel_scope)`.

5. **`_find_best_matching_seed()`** — for Ring D combo hits, tries: (1) exact label match, (2) substring match, (3) first combo seed as fallback.

---

## Files Changed

### Modified
| File | Change |
|---|---|
| `backend/app/core/config.py` | +2 feature flags |
| `backend/app/services/monitoring_profile.py` | SYSTEM_SOURCE_REF_TYPES, SEED_BASE_WEIGHTS (+8 types), iter_scan_seeds expanded |
| `backend/app/services/use_cases/sync_monitoring_profile.py` | `_apply_profile_components()` full seed pipeline, `regenerate_seeds_for_brand()` added |
| `backend/app/services/use_cases/generate_llm_assessment.py` | Early return when flag off |
| `backend/app/worker/assessment_worker.py` | Early exit when flag off |
| `backend/app/repositories/similarity_repository.py` | `fetch_candidates_exact()`, `fetch_candidates_punycode()` added |
| `backend/app/services/use_cases/run_similarity_scan.py` | Full ring-based retrieval rewrite |
| `backend/app/schemas/monitored_brand.py` | `BrandSeedGroupedResponse`, `SeedPreviewResponse` added |
| `backend/app/api/v1/routers/monitored_brands.py` | 2 new endpoints, `_group_seeds_by_family()` helper |
| `infra/stack.dev.yml` | Both feature flag env vars |
| `infra/stack.yml` | Both feature flag env vars |

### Created
| File | Purpose |
|---|---|
| `backend/app/services/seed_generation.py` | Deterministic combo/typo/homograph seed generation |
| `backend/app/services/use_cases/generate_brand_seeds.py` | Phase 2 LLM seed generation via OpenRouter |

---

## Known Limitations / Caveats

1. **Ring B fallback** — if a brand has no fuzzy seeds (all seeds are exact/combo type), Ring B uses any remaining seeds through the fuzzy path. This is safe but may produce slightly over-broad results.

2. **`generate_brand_seeds.py` uses `httpx`** — verify `httpx` is in `pyproject.toml` dependencies (likely already present since `generate_llm_assessment.py` uses it too).

3. **Combo generation cap (120)** — brands with many aliases + many keywords may get truncated combos. This is intentional to keep seed counts manageable.

4. **`include_llm` query param** on regenerate endpoint — currently passed to the endpoint but the LLM gating is fully controlled by `SEED_LLM_GENERATION_ENABLED` in `_apply_profile_components()`. The param is reserved for future finer-grained control.

5. **Existing scan cursors** — regenerating seeds does not reset similarity scan cursors. A full rescan is only triggered when official domains change via `update_monitoring_profile()`.
