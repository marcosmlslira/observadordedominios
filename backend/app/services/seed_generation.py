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
    HOMOGRAPH_REVERSE,
    RISK_KEYWORDS,
    generate_typo_candidates,
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
    combo_keywords = list(RISK_KEYWORDS) + brand_keywords + ABUSE_SUFFIXES
    combo_keywords_unique = list(dict.fromkeys(combo_keywords))

    combo_count = 0
    brand_cores = [brand_label] + [a for a in brand_aliases if a != brand_label]

    for core in brand_cores:
        if combo_count >= MAX_COMBO_SEEDS:
            break
        for kw in combo_keywords_unique:
            if combo_count >= MAX_COMBO_SEEDS:
                break
            if _add(f"{core}-{kw}", "combo_brand_keyword"):
                combo_count += 1
            if _add(f"{core}{kw}", "combo_brand_keyword"):
                combo_count += 1
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
    typo_count = 0
    for core in brand_cores[:2]:
        if typo_count >= MAX_TYPO_SEEDS:
            break
        typo_variants = generate_typo_candidates(core)
        for variant in sorted(typo_variants, key=len):
            if typo_count >= MAX_TYPO_SEEDS:
                break
            if _add(variant, "typo_base"):
                typo_count += 1

    logger.info("Generated %d typo_base seeds for brand=%s", typo_count, brand_label)

    # ── 3. Homograph base seeds ────────────────────────────
    homograph_count = 0
    for core in brand_cores[:1]:
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

    for seed in base_seeds:
        key = (seed["seed_value"], seed["seed_type"], seed["channel_scope"])
        if key not in seen:
            seen.add(key)
            merged.append(seed)

    for seed in expanded_seeds:
        key = (seed["seed_value"], seed["seed_type"], seed["channel_scope"])
        if key not in seen:
            seen.add(key)
            merged.append(seed)

    return merged
