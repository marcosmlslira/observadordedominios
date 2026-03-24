"""Monitoring profile normalization and seed derivation helpers."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from app.models.monitored_brand_alias import MonitoredBrandAlias
from app.models.monitored_brand_domain import MonitoredBrandDomain
from app.models.monitored_brand_seed import MonitoredBrandSeed

try:
    import tldextract  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised in tests via fallback
    tldextract = None

_ALIAS_SANITIZER_RE = re.compile(r"[^a-z0-9]+")
_SECOND_LEVEL_CCTLD_PREFIXES = {"ac", "co", "com", "edu", "gov", "net", "org"}

NOISE_MODES = {"conservative", "standard", "broad"}
ALIAS_TYPES = {"brand_alias", "brand_phrase", "support_keyword"}
SCAN_CHANNELS_FOR_DOMAIN_TABLE = {"registrable_domain", "associated_brand", "both"}

SEED_BASE_WEIGHTS: dict[str, float] = {
    "domain_label": 1.00,
    "hostname_stem": 0.95,
    "brand_primary": 0.90,
    "official_domain": 0.85,
    "brand_phrase": 0.80,
    "brand_alias": 0.65,
    "support_keyword": 0.20,
}

CHANNEL_MULTIPLIERS: dict[str, float] = {
    "registrable_domain": 1.00,
    "certificate_hostname": 0.85,
    "associated_brand": 0.75,
    "both": 0.90,
}


@dataclass(frozen=True)
class DomainInput:
    domain_name: str
    registrable_domain: str
    registrable_label: str
    public_suffix: str
    hostname_stem: str | None
    is_primary: bool


@dataclass(frozen=True)
class AliasInput:
    alias_value: str
    alias_normalized: str
    alias_type: str
    weight_override: float | None = None


def normalize_brand_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    return _ALIAS_SANITIZER_RE.sub("", normalized)


def normalize_domain_name(value: str) -> str:
    return value.strip().lower().rstrip(".")


def looks_like_domain(value: str) -> bool:
    candidate = normalize_domain_name(value)
    if " " in candidate or "." not in candidate:
        return False
    parts = _extract_domain_parts(candidate)
    return bool(parts and parts["registered_domain"] == candidate)


def normalize_noise_mode(value: str | None) -> str:
    if not value:
        return "standard"
    normalized = value.strip().lower()
    if normalized not in NOISE_MODES:
        raise ValueError(f"noise_mode must be one of: {', '.join(sorted(NOISE_MODES))}")
    return normalized


def resolve_primary_brand_name(
    display_name: str,
    primary_brand_name: str | None,
    official_domains: list[str],
) -> str:
    explicit = (primary_brand_name or "").strip()
    if explicit:
        return explicit

    if official_domains:
        first = build_domain_input(official_domains[0], is_primary=True)
        return first.registrable_label

    return display_name.strip()


def resolve_display_name(display_name: str, primary_brand_name: str | None) -> str:
    candidate = display_name.strip()
    if candidate:
        return candidate
    if primary_brand_name and primary_brand_name.strip():
        return primary_brand_name.strip()
    raise ValueError("brand_name must not be empty")


def resolve_official_domains(
    display_name: str,
    explicit_domains: list[str] | None,
) -> list[str]:
    values = [item for item in (explicit_domains or []) if item.strip()]
    if values:
        return values
    if looks_like_domain(display_name):
        return [display_name]
    return []


def build_domain_input(domain_name: str, *, is_primary: bool) -> DomainInput:
    normalized = normalize_domain_name(domain_name)
    parts = _extract_domain_parts(normalized)
    if not parts:
        raise ValueError(f"invalid official domain: {domain_name}")

    public_suffix = parts["suffix"]
    hostname_stem = None
    if "." in public_suffix:
        hostname_stem = f"{parts['domain']}.{public_suffix.split('.', 1)[0]}"

    return DomainInput(
        domain_name=normalized,
        registrable_domain=parts["registered_domain"],
        registrable_label=parts["domain"],
        public_suffix=public_suffix,
        hostname_stem=hostname_stem,
        is_primary=is_primary,
    )


def build_domain_inputs(official_domains: list[str]) -> list[DomainInput]:
    seen: set[str] = set()
    items: list[DomainInput] = []
    for index, domain_name in enumerate(official_domains):
        normalized = normalize_domain_name(domain_name)
        if normalized in seen:
            continue
        seen.add(normalized)
        items.append(build_domain_input(normalized, is_primary=index == 0))
    return items


def build_alias_inputs(
    primary_brand_name: str,
    aliases: list[str] | None,
    phrases: list[str] | None,
    support_keywords: list[str] | None,
) -> list[AliasInput]:
    normalized_inputs: list[AliasInput] = []
    seen: set[tuple[str, str]] = set()

    def _append(value: str, alias_type: str, weight_override: float | None = None) -> None:
        raw = value.strip()
        if not raw:
            return
        normalized = normalize_brand_text(raw)
        if not normalized:
            return
        key = (normalized, alias_type)
        if key in seen:
            return
        seen.add(key)
        normalized_inputs.append(
            AliasInput(
                alias_value=raw,
                alias_normalized=normalized,
                alias_type=alias_type,
                weight_override=weight_override,
            )
        )

    _append(primary_brand_name, "brand_primary")
    for alias in aliases or []:
        _append(alias, "brand_alias")
    for phrase in phrases or []:
        _append(phrase, "brand_phrase")
    for keyword in support_keywords or []:
        _append(keyword, "support_keyword")

    return normalized_inputs


def derive_brand_label(
    primary_brand_name: str,
    domain_inputs: list[DomainInput],
) -> str:
    if domain_inputs:
        return domain_inputs[0].registrable_label
    return normalize_brand_text(primary_brand_name)


def build_seed_rows(
    domains: list[MonitoredBrandDomain],
    aliases: list[MonitoredBrandAlias],
) -> list[dict]:
    seed_rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def _append(
        *,
        source_ref_type: str,
        source_ref_id,
        seed_value: str,
        seed_type: str,
        channel_scope: str,
        base_weight: float,
    ) -> None:
        normalized = normalize_brand_text(seed_value) if seed_type not in {"official_domain", "hostname_stem"} else seed_value.strip().lower()
        if not normalized:
            return
        key = (normalized, seed_type, channel_scope)
        if key in seen:
            return
        seen.add(key)
        seed_rows.append(
            {
                "source_ref_type": source_ref_type,
                "source_ref_id": source_ref_id,
                "seed_value": normalized,
                "seed_type": seed_type,
                "channel_scope": channel_scope,
                "base_weight": base_weight,
            }
        )

    for domain in domains:
        _append(
            source_ref_type="official_domain",
            source_ref_id=domain.id,
            seed_value=domain.registrable_label,
            seed_type="domain_label",
            channel_scope="registrable_domain",
            base_weight=SEED_BASE_WEIGHTS["domain_label"],
        )
        _append(
            source_ref_type="official_domain",
            source_ref_id=domain.id,
            seed_value=domain.domain_name,
            seed_type="official_domain",
            channel_scope="certificate_hostname",
            base_weight=SEED_BASE_WEIGHTS["official_domain"],
        )
        if domain.hostname_stem:
            _append(
                source_ref_type="official_domain",
                source_ref_id=domain.id,
                seed_value=domain.hostname_stem,
                seed_type="hostname_stem",
                channel_scope="certificate_hostname",
                base_weight=SEED_BASE_WEIGHTS["hostname_stem"],
            )

    for alias in aliases:
        seed_type = "brand_primary" if alias.alias_type == "brand_primary" else alias.alias_type
        channel_scope = "both" if seed_type == "brand_primary" else "associated_brand"
        _append(
            source_ref_type="alias",
            source_ref_id=alias.id,
            seed_value=alias.alias_normalized,
            seed_type=seed_type,
            channel_scope=channel_scope,
            base_weight=alias.weight_override or SEED_BASE_WEIGHTS.get(seed_type, 0.50),
        )

    return seed_rows


def iter_scan_seeds(seeds: list[MonitoredBrandSeed]) -> list[MonitoredBrandSeed]:
    allowed_types = {"domain_label", "brand_primary", "brand_alias", "brand_phrase"}
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


def pick_matched_rule(reasons: list[str], channel_scope: str) -> str:
    if "exact_label_match" in reasons:
        return "exact_label_match"
    if "homograph_attack" in reasons:
        return "homograph"
    if "typosquatting" in reasons:
        return "typo_candidate"
    if "brand_containment" in reasons and "risky_keywords" in reasons:
        return "brand_plus_keyword"
    if "brand_containment" in reasons:
        return "hostname_containment" if channel_scope == "certificate_hostname" else "brand_containment"
    return "lexical_similarity"


def _extract_domain_parts(candidate: str) -> dict[str, str] | None:
    if tldextract is not None:
        ext = tldextract.TLDExtract(cache_dir="/tmp/tldextract_cache")(candidate)
        if ext.domain and ext.suffix and ext.registered_domain:
            return {
                "domain": ext.domain,
                "suffix": ext.suffix,
                "registered_domain": ext.registered_domain,
            }

    labels = [label for label in candidate.split(".") if label]
    if len(labels) < 2:
        return None

    if (
        len(labels) >= 3
        and len(labels[-1]) == 2
        and labels[-2] in _SECOND_LEVEL_CCTLD_PREFIXES
    ):
        suffix_labels = labels[-2:]
        domain_index = -3
    else:
        suffix_labels = labels[-1:]
        domain_index = -2

    domain = labels[domain_index]
    suffix = ".".join(suffix_labels)
    registered_domain = ".".join([domain, *suffix_labels])
    return {
        "domain": domain,
        "suffix": suffix,
        "registered_domain": registered_domain,
    }
