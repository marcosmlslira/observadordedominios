"""Actionability scoring for similarity matches.

Separates lexical similarity from operational priority so the product can
answer what deserves attention now versus what is merely a defensive gap.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.models.monitored_brand import MonitoredBrand

AttentionBucket = str

STRATEGIC_DEFENSIVE_TLDS = {
    "com", "net", "org", "app", "io", "ai", "co", "xyz", "site", "store",
    "online", "shop", "info", "biz", "cloud", "dev", "pro", "com.br", "net.br", "org.br",
}


def compute_actionability(
    brand: MonitoredBrand,
    *,
    domain_name: str,
    tld: str,
    score_final: float,
    risk_level: str,
    reasons: list[str],
    matched_rule: str | None,
    matched_seed_type: str | None,
    matched_seed_value: str | None,
    matched_channel: str | None,
    domain_first_seen: int | None,
) -> dict[str, object]:
    score = score_final * 0.35
    actionability_reasons: list[str] = []

    seed_value = (matched_seed_value or "").strip().lower()
    seed_type = (matched_seed_type or "").strip().lower()
    rule = (matched_rule or "").strip().lower()
    channel = (matched_channel or "").strip().lower()
    domain_label = domain_name.split(".", 1)[0].lower()

    brand_label = (brand.brand_label or "").strip().lower()
    generic_associated_seed = (
        seed_type in {"brand_alias", "brand_phrase", "brand_primary"}
        and len(seed_value) <= 5
        and seed_value != brand_label
    )

    if domain_first_seen:
        y = domain_first_seen // 10000
        m = (domain_first_seen % 10000) // 100
        d = domain_first_seen % 100
        try:
            first_seen_dt = datetime(y, m, d, tzinfo=timezone.utc)
            age_days = max(0, int((datetime.now(timezone.utc) - first_seen_dt).total_seconds() // 86400))
        except (ValueError, TypeError):
            age_days = 999
    else:
        age_days = 999
    if age_days <= 30:
        score += 0.18
        actionability_reasons.append("newly_observed_domain")
    elif age_days <= 90:
        score += 0.08
        actionability_reasons.append("recently_observed_domain")

    if rule == "exact_label_match":
        if seed_type == "domain_label":
            score += 0.32
            actionability_reasons.append("exact_match_on_official_label")
        elif generic_associated_seed:
            score -= 0.12
            actionability_reasons.append("exact_match_on_generic_associated_seed")
        else:
            score += 0.16
            actionability_reasons.append("exact_match_on_associated_brand")

    if rule == "typo_candidate":
        score += 0.38
        actionability_reasons.append("typosquatting_pattern")
    elif rule == "homograph":
        score += 0.42
        actionability_reasons.append("homograph_pattern")
    elif rule == "brand_plus_keyword":
        score += 0.34
        actionability_reasons.append("brand_plus_risky_keyword")
    elif rule == "brand_containment":
        if channel == "associated_brand":
            score += 0.04
            actionability_reasons.append("associated_brand_containment")
        else:
            score += 0.10
            actionability_reasons.append("official_label_containment")

    if tld in STRATEGIC_DEFENSIVE_TLDS:
        score += 0.05
        actionability_reasons.append("strategic_tld")

    if risk_level in {"high", "critical"}:
        score += 0.10

    if generic_associated_seed:
        score -= 0.10

    if domain_label.endswith("login") or domain_label.startswith("login"):
        score += 0.10
        actionability_reasons.append("login_keyword_in_label")

    score = max(0.0, min(1.0, score))

    bucket: AttentionBucket
    recommended_action: str

    label = brand.brand_label or brand.brand_name or "the brand"

    if rule in {"typo_candidate", "homograph", "brand_plus_keyword"} and score >= 0.68:
        bucket = "immediate_attention"
        if rule == "homograph":
            recommended_action = (
                f"{domain_name} uses look-alike characters to mimic {label}. "
                "Inspect for active phishing infrastructure immediately."
            )
        elif rule == "typo_candidate":
            recommended_action = (
                f"{domain_name} is a likely typosquatting variant of {label}. "
                "Check for live content or credential-capture surfaces."
            )
        else:
            recommended_action = (
                f"{domain_name} combines {label}'s name with a high-risk keyword. "
                "Verify whether this domain is being used to impersonate the brand."
            )
    elif rule == "exact_label_match" and seed_type == "domain_label":
        bucket = "defensive_gap"
        recommended_action = (
            f"{domain_name} exactly matches a registered label of {label} "
            "but is not an official asset. Assess for defensive registration or legal action."
        )
    elif score >= 0.72 and risk_level in {"high", "critical"}:
        bucket = "immediate_attention"
        recommended_action = (
            f"{domain_name} scores high similarity to {label} with elevated risk signals. "
            "Inspect immediately for active impersonation or phishing."
        )
    elif score >= 0.48:
        bucket = "defensive_gap"
        recommended_action = (
            f"{domain_name} shows moderate similarity to {label}. "
            "Monitor closely and assess whether defensive registration or escalation is warranted."
        )
    else:
        bucket = "watchlist"
        recommended_action = (
            f"{domain_name} shows low-confidence similarity to {label}. "
            "Keep in watchlist unless enrichment data adds operational concern."
        )

    if bucket == "watchlist" and generic_associated_seed:
        recommended_action = (
            f"{domain_name} is a weak match on a short associated-brand term for {label}. "
            "Keep only for background monitoring unless new signals emerge."
        )

    return {
        "actionability_score": round(score, 4),
        "attention_bucket": bucket,
        "attention_reasons": sorted(set(actionability_reasons)),
        "recommended_action": recommended_action,
    }
