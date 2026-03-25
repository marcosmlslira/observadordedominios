"""Selective operational enrichment for high-signal similarity matches."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.monitored_brand import MonitoredBrand

PLACEHOLDER_ORG_ID = uuid.UUID(settings.TOOLS_PLACEHOLDER_ORG_ID)
HIGH_RISK_COUNTRY_CODES = {"RU", "BY", "KP", "IR"}
AUTO_ENRICH_LIMIT_PER_SCAN = 8


def should_auto_enrich_match(match: dict) -> bool:
    """Apply a strict gate so enrichment stays selective and affordable."""
    if (match.get("attention_bucket") or "watchlist") == "watchlist":
        return False

    matched_rule = (match.get("matched_rule") or "").lower()
    matched_seed_type = (match.get("matched_seed_type") or "").lower()
    actionability_score = float(match.get("actionability_score") or 0.0)
    risk_level = (match.get("risk_level") or "").lower()

    if matched_rule in {"typo_candidate", "homograph", "brand_plus_keyword"}:
        return True

    if matched_rule == "exact_label_match" and matched_seed_type == "domain_label":
        return True

    return actionability_score >= 0.72 and risk_level in {"high", "critical"}


def enrich_similarity_match(
    db: Session,
    brand: MonitoredBrand,
    match: dict,
) -> dict[str, object]:
    """Run low-volume enrichment tools and rebalance actionability."""
    domain = f"{match['domain_name']}.{match['tld']}"
    tool_results = _run_enrichment_tools(db, domain)

    signal_codes: list[str] = list(match.get("attention_reasons") or [])
    signals: list[dict[str, object]] = []
    score = float(match.get("actionability_score") or 0.0)

    score, signals = _apply_whois_adjustments(tool_results.get("whois"), score, signals)
    score, signals = _apply_http_adjustments(tool_results.get("http_headers"), score, signals)
    score, signals = _apply_page_adjustments(tool_results.get("suspicious_page"), score, signals)
    score, signals = _apply_email_adjustments(tool_results.get("email_security"), score, signals)
    score, signals = _apply_geo_adjustments(tool_results.get("ip_geolocation"), score, signals)

    signal_codes.extend([str(signal["code"]) for signal in signals])
    score = max(0.0, min(1.0, score))

    bucket, action = _bucket_after_enrichment(match, score, signal_codes)
    compact_tools = _compact_tool_results(tool_results)

    return {
        "actionability_score": round(score, 4),
        "attention_bucket": bucket,
        "attention_reasons": sorted(set(signal_codes)),
        "recommended_action": action,
        "enrichment_status": "completed",
        "enrichment_summary": {
            "signals": signals,
            "tools": compact_tools,
            "target": domain,
        },
        "last_enriched_at": datetime.now(timezone.utc),
    }


def _run_enrichment_tools(db: Session, domain: str) -> dict[str, dict]:
    from app.services.use_cases.tools.email_security import EmailSecurityService
    from app.services.use_cases.tools.http_headers import HttpHeadersService
    from app.services.use_cases.tools.ip_geolocation import IpGeolocationService
    from app.services.use_cases.tools.suspicious_page import SuspiciousPageService
    from app.services.use_cases.tools.whois_lookup import WhoisLookupService

    services = {
        "whois": WhoisLookupService(),
        "http_headers": HttpHeadersService(),
        "suspicious_page": SuspiciousPageService(),
        "email_security": EmailSecurityService(),
        "ip_geolocation": IpGeolocationService(),
    }

    results: dict[str, dict] = {}
    for tool_type, service in services.items():
        response = service.run(
            db,
            PLACEHOLDER_ORG_ID,
            domain,
            triggered_by="similarity_enrichment",
            force=False,
        )
        results[tool_type] = {
            "status": response.status,
            "error": response.error,
            "result": response.result or {},
        }
    return results


def _apply_whois_adjustments(tool_data: dict | None, score: float, signals: list[dict[str, object]]):
    if not tool_data or tool_data.get("status") != "completed":
        return score, signals

    creation_raw = ((tool_data.get("result") or {}).get("creation_date") or "").strip()
    if not creation_raw:
        return score, signals

    parsed = _parse_datetime_like(creation_raw)
    if not parsed:
        return score, signals

    age_days = max(0, int((datetime.now(timezone.utc) - parsed).total_seconds() // 86400))
    if age_days <= 30:
        score += 0.18
        signals.append(_signal("recent_registration", "high", "Domain was registered in the last 30 days."))
    elif age_days <= 90:
        score += 0.10
        signals.append(_signal("fresh_registration", "medium", "Domain was registered in the last 90 days."))

    return score, signals


def _apply_http_adjustments(tool_data: dict | None, score: float, signals: list[dict[str, object]]):
    if not tool_data or tool_data.get("status") != "completed":
        return score, signals

    result = tool_data.get("result") or {}
    status_code = result.get("status_code")
    final_url = (result.get("final_url") or "").lower()

    if status_code == 200:
        score += 0.05
        signals.append(_signal("live_http_surface", "medium", "HTTP endpoint is live and responding with 200."))
    elif status_code in {401, 403, 429, 503}:
        score += 0.06
        signals.append(
            _signal(
                "restricted_live_surface",
                "medium",
                f"HTTP endpoint responds with {status_code}, suggesting an accessible but restricted surface.",
            )
        )

    if final_url.startswith("https://"):
        score += 0.03
        signals.append(_signal("https_enabled", "low", "Site serves over HTTPS."))

    return score, signals


def _apply_page_adjustments(tool_data: dict | None, score: float, signals: list[dict[str, object]]):
    if not tool_data or tool_data.get("status") != "completed":
        return score, signals

    result = tool_data.get("result") or {}
    page_disposition = result.get("page_disposition")
    risk_level = result.get("risk_level")
    page_signals = result.get("signals") or []

    if page_disposition == "parked":
        score -= 0.22
        signals.append(_signal("parked_or_for_sale_page", "low", "Domain resolves to a parked or for-sale page."))
    elif page_disposition == "challenge":
        score += 0.08
        signals.append(_signal("protected_or_blocked_page", "medium", "Page is live behind a challenge or access barrier."))

    if result.get("has_login_form") or result.get("has_credential_inputs"):
        score += 0.26
        signals.append(_signal("credential_collection_surface", "critical", "Page exposes a login or credential capture surface."))

    if risk_level == "critical":
        score += 0.22
    elif risk_level == "high":
        score += 0.14
    elif risk_level == "medium":
        score += 0.06

    categories = {str(item.get("category")) for item in page_signals if item.get("category")}
    if "brand_impersonation" in categories:
        score += 0.18
        signals.append(_signal("brand_impersonation_content", "high", "Content references a protected brand inconsistent with the domain."))
    if "social_engineering" in categories:
        score += 0.10
        signals.append(_signal("social_engineering_language", "medium", "Urgency or coercive language was detected on page."))
    if "infrastructure_masking" in categories:
        score += 0.08
        signals.append(_signal("shielded_infrastructure", "medium", "Site is fronted by shielding infrastructure often seen in abuse cases."))

    return score, signals


def _apply_email_adjustments(tool_data: dict | None, score: float, signals: list[dict[str, object]]):
    if not tool_data or tool_data.get("status") != "completed":
        return score, signals

    spoofing_risk = ((tool_data.get("result") or {}).get("spoofing_risk") or {})
    level = str(spoofing_risk.get("level") or "").lower()

    if level == "critical":
        score += 0.16
        signals.append(_signal("high_spoofing_risk", "high", "Mail configuration allows high spoofing risk."))
    elif level == "high":
        score += 0.09
        signals.append(_signal("elevated_spoofing_risk", "medium", "Mail configuration presents elevated spoofing risk."))

    return score, signals


def _apply_geo_adjustments(tool_data: dict | None, score: float, signals: list[dict[str, object]]):
    if not tool_data or tool_data.get("status") != "completed":
        return score, signals

    result = tool_data.get("result") or {}
    country_code = str(result.get("country_code") or "").upper()
    org = str(result.get("org") or "")
    asn = str(result.get("asn") or "")

    if country_code in HIGH_RISK_COUNTRY_CODES:
        score += 0.12
        signals.append(_signal("unusual_hosting_country", "medium", f"Resolved infrastructure is hosted in {country_code}."))

    if "ddos-guard" in org.lower() or "ddos-guard" in asn.lower():
        score += 0.08
        signals.append(_signal("shielded_hosting_provider", "medium", "Infrastructure is associated with DDoS-Guard."))

    return score, signals


def _bucket_after_enrichment(match: dict, score: float, signal_codes: list[str]) -> tuple[str, str]:
    matched_rule = (match.get("matched_rule") or "").lower()
    matched_seed_type = (match.get("matched_seed_type") or "").lower()
    signal_set = set(signal_codes)

    if {"credential_collection_surface", "brand_impersonation_content"} & signal_set:
        return (
            "immediate_attention",
            "Investigate immediately. This candidate shows live impersonation or credential-capture signals.",
        )

    if score >= 0.80 and matched_rule in {"typo_candidate", "homograph", "brand_plus_keyword"}:
        return (
            "immediate_attention",
            "Investigate immediately. High-signal lexical pattern plus enrichment indicates a likely live threat.",
        )

    if "parked_or_for_sale_page" in signal_set and matched_rule == "exact_label_match" and matched_seed_type == "domain_label":
        return (
            "defensive_gap",
            "Treat as a defensive registration gap. The domain looks parked rather than operationally abusive.",
        )

    if score >= 0.55:
        return (
            "defensive_gap",
            "Review for ownership gap, escalation, or closer analyst follow-up.",
        )

    return (
        "watchlist",
        "Keep in watchlist unless new enrichment or analyst review raises operational concern.",
    )


def _compact_tool_results(tool_results: dict[str, dict]) -> dict[str, dict]:
    compact: dict[str, dict] = {}
    for tool_type, payload in tool_results.items():
        result = payload.get("result") or {}
        compact[tool_type] = {
            "status": payload.get("status"),
            "error": payload.get("error"),
            "summary": _compact_summary(tool_type, result),
        }
    return compact


def _compact_summary(tool_type: str, result: dict) -> dict:
    if tool_type == "whois":
        return {
            "registrar": result.get("registrar"),
            "creation_date": result.get("creation_date"),
            "registrant_country": result.get("registrant_country"),
        }
    if tool_type == "http_headers":
        return {
            "status_code": result.get("status_code"),
            "final_url": result.get("final_url"),
            "server": result.get("server"),
        }
    if tool_type == "suspicious_page":
        return {
            "risk_level": result.get("risk_level"),
            "page_disposition": result.get("page_disposition"),
            "has_login_form": result.get("has_login_form"),
            "has_credential_inputs": result.get("has_credential_inputs"),
        }
    if tool_type == "email_security":
        return {"spoofing_risk": result.get("spoofing_risk")}
    if tool_type == "ip_geolocation":
        return {
            "country_code": result.get("country_code"),
            "org": result.get("org"),
            "asn": result.get("asn"),
        }
    return result


def _parse_datetime_like(value: str) -> datetime | None:
    for candidate in (value.strip(), value.strip().replace("Z", "+00:00")):
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def _signal(code: str, severity: str, description: str) -> dict[str, object]:
    return {"code": code, "severity": severity, "description": description}
