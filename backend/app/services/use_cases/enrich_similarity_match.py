"""Selective operational enrichment for high-signal similarity matches."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.monitored_brand import MonitoredBrand
from app.services.monitoring_profile import normalize_brand_text
from app.services.registrable_domain import InvalidDomainError, parse_registrable_domain

PLACEHOLDER_ORG_ID = uuid.UUID(settings.TOOLS_PLACEHOLDER_ORG_ID)
HIGH_RISK_COUNTRY_CODES = {"RU", "BY", "KP", "IR"}
AUTO_ENRICH_LIMIT_PER_SCAN = 8


def should_auto_enrich_match(match: dict) -> bool:
    """Apply a strict gate so enrichment stays selective and affordable."""
    attention_bucket = (match.get("attention_bucket") or "watchlist")
    if attention_bucket == "watchlist":
        return False

    matched_rule = (match.get("matched_rule") or "").lower()
    matched_seed_type = (match.get("matched_seed_type") or "").lower()
    actionability_score = float(match.get("actionability_score") or 0.0)
    risk_level = (match.get("risk_level") or "").lower()

    if matched_rule in {"typo_candidate", "homograph", "brand_plus_keyword"}:
        return True

    if matched_rule == "exact_label_match" and matched_seed_type == "domain_label":
        return True

    # defensive_gap domains are registered but unowned — enrich at a lower threshold
    # because mail-only infrastructure risk is only detectable via DNS/email enrichment
    if attention_bucket == "defensive_gap" and actionability_score >= 0.55:
        return True

    return actionability_score >= 0.72 and risk_level in {"high", "critical"}


def enrich_similarity_match(
    db: Session,
    brand: MonitoredBrand,
    match: dict,
) -> dict[str, object]:
    """Run low-volume enrichment tools and rebalance actionability."""
    domain = str(match["domain_name"])
    if not domain.endswith(f".{match['tld']}"):
        domain = f"{domain}.{match['tld']}"
    tool_results = _run_enrichment_tools(db, domain)

    signal_codes: list[str] = list(match.get("attention_reasons") or [])
    signals: list[dict[str, object]] = []
    score = float(match.get("actionability_score") or 0.0)
    delivery_risk = "none"

    score, signals = _apply_whois_adjustments(tool_results.get("whois"), score, signals)
    score, signals = _apply_dns_adjustments(tool_results.get("dns_lookup"), score, signals)
    score, signals = _apply_http_adjustments(tool_results.get("http_headers"), score, signals)
    score, signals = _apply_page_adjustments(tool_results.get("suspicious_page"), score, signals)
    score, signals, delivery_risk = _apply_email_adjustments(
        tool_results.get("email_security"),
        tool_results.get("http_headers"),
        tool_results.get("suspicious_page"),
        score,
        signals,
        dns_tool_data=tool_results.get("dns_lookup"),
    )
    score, signals = _apply_geo_adjustments(tool_results.get("ip_geolocation"), score, signals)

    ownership_classification, self_owned = _derive_ownership(brand, match, tool_results)

    # T3.5 — Clone detection: only for immediate_attention matches with an official domain.
    # Runs after standard tools so we already know if the site is even reachable.
    clone_result: dict | None = None
    if (
        match.get("attention_bucket") == "immediate_attention"
        and ownership_classification not in {"official", "self_owned_related"}
        and brand.domains
    ):
        reference_domain = next(
            (d.domain_name for d in brand.domains if getattr(d, "is_primary", False)),
            brand.domains[0].domain_name,
        )
        score, signals, clone_result = _apply_clone_detection(
            db, domain, reference_domain, score, signals
        )

    signal_codes.extend([str(signal["code"]) for signal in signals])
    score = max(0.0, min(1.0, score))

    bucket, action = _bucket_after_enrichment(
        match,
        score,
        signal_codes,
        brand=brand,
        ownership_classification=ownership_classification,
    )
    disposition = _derive_disposition(
        match,
        score,
        signal_codes,
        tool_results,
        ownership_classification=ownership_classification,
        delivery_risk=delivery_risk,
    )
    compact_tools = _compact_tool_results(tool_results)
    if clone_result is not None:
        compact_tools["website_clone"] = clone_result
    confidence = _derive_confidence(tool_results, score, signal_codes)

    from app.services.use_cases.generate_llm_assessment import generate_llm_assessment
    llm_result = generate_llm_assessment(
        match={**match, "risk_level": match.get("risk_level"), "attention_bucket": bucket},
        brand_name=str(brand.brand_name or ""),
        tool_results=tool_results,
        signals=signals,
    )

    return {
        "actionability_score": round(score, 4),
        "attention_bucket": bucket,
        "attention_reasons": sorted(set(signal_codes)),
        "recommended_action": action,
        "enrichment_status": "completed",
        "ownership_classification": ownership_classification,
        "self_owned": self_owned,
        "disposition": disposition,
        "confidence": confidence,
        "delivery_risk": delivery_risk,
        "llm_assessment": llm_result,
        "enrichment_summary": {
            "signals": signals,
            "tools": compact_tools,
            "target": domain,
        },
        "last_enriched_at": datetime.now(timezone.utc),
    }


def _run_enrichment_tools(db: Session, domain: str) -> dict[str, dict]:
    from app.services.use_cases.tools.dns_lookup import DnsLookupService
    from app.services.use_cases.tools.email_security import EmailSecurityService
    from app.services.use_cases.tools.http_headers import HttpHeadersService
    from app.services.use_cases.tools.ip_geolocation import IpGeolocationService
    from app.services.use_cases.tools.screenshot_capture import ScreenshotCaptureService
    from app.services.use_cases.tools.ssl_check import SslCheckService
    from app.services.use_cases.tools.suspicious_page import SuspiciousPageService
    from app.services.use_cases.tools.whois_lookup import WhoisLookupService

    services = {
        "whois": WhoisLookupService(),
        "dns_lookup": DnsLookupService(),
        "http_headers": HttpHeadersService(),
        "suspicious_page": SuspiciousPageService(),
        "email_security": EmailSecurityService(),
        "ip_geolocation": IpGeolocationService(),
        "ssl_check": SslCheckService(),
        "screenshot": ScreenshotCaptureService(),
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


def _apply_dns_adjustments(tool_data: dict | None, score: float, signals: list[dict[str, object]]):
    if not tool_data or tool_data.get("status") != "completed":
        return score, signals

    result = tool_data.get("result") or {}
    records = result.get("records") or []
    record_types = {str(r.get("type", "")).upper() for r in records}

    has_a_or_aaaa = bool({"A", "AAAA"} & record_types)
    has_mx = "MX" in record_types

    if not has_a_or_aaaa and not has_mx:
        # Domain doesn't resolve at all — reduce actionability
        score -= 0.08
        signals.append(_signal("dns_not_resolving", "low", "Domain has no A, AAAA, or MX records — may be abandoned or not yet active."))
        return score, signals

    if has_mx and not has_a_or_aaaa:
        # Mail-only domain: configured for email but no web surface
        score += 0.12
        signals.append(_signal("mail_only_infrastructure", "high", "Domain has MX records but no web resolution — configured exclusively for email delivery."))

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
        score += 0.05
        signals.append(_signal("protected_or_blocked_page", "medium", "Page is live behind a challenge or access barrier."))
    elif page_disposition == "unreachable":
        signals.append(_signal("page_fetch_inconclusive", "low", "Page could not be fetched conclusively."))

    if result.get("has_login_form") or result.get("has_credential_inputs"):
        score += 0.26
        signals.append(_signal("credential_collection_surface", "critical", "Page exposes a login or credential capture surface."))

    if risk_level == "critical":
        score += 0.22
    elif risk_level == "high":
        score += 0.14
    elif risk_level == "medium":
        score += 0.06
    elif risk_level == "protected":
        score += 0.04

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


def _apply_email_adjustments(
    tool_data: dict | None,
    http_tool_data: dict | None,
    page_tool_data: dict | None,
    score: float,
    signals: list[dict[str, object]],
    *,
    dns_tool_data: dict | None = None,
):
    if not tool_data or tool_data.get("status") != "completed":
        return score, signals, "none"

    spoofing_risk = (tool_data.get("result") or {}).get("spoofing_risk") or {}
    if isinstance(spoofing_risk, str):
        level = spoofing_risk.lower()
    else:
        level = str(spoofing_risk.get("level") or "").lower()

    http_status = ((http_tool_data or {}).get("result") or {}).get("status_code")
    page_disposition = ((page_tool_data or {}).get("result") or {}).get("page_disposition")
    live_web_surface = http_status == 200 and page_disposition == "live"
    dns_records = ((dns_tool_data or {}).get("result") or {}).get("records") or []
    dns_record_types = {str(r.get("type", "")).upper() for r in dns_records}
    is_mail_only = "MX" in dns_record_types and not ({"A", "AAAA"} & dns_record_types)
    delivery_risk = "none"

    if level == "critical":
        score += 0.16
        signals.append(_signal("high_spoofing_risk", "high", "Mail configuration allows high spoofing risk."))
        delivery_risk = "high" if (not live_web_surface or is_mail_only) else "possible"
    elif level == "high":
        score += 0.09
        signals.append(_signal("elevated_spoofing_risk", "medium", "Mail configuration presents elevated spoofing risk."))
        delivery_risk = "high" if is_mail_only else "possible"
    elif level == "medium" and (not live_web_surface or is_mail_only):
        delivery_risk = "possible"

    return score, signals, delivery_risk


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


def _bucket_after_enrichment(
    match: dict,
    score: float,
    signal_codes: list[str],
    *,
    brand: MonitoredBrand,
    ownership_classification: str,
) -> tuple[str, str]:
    matched_rule = (match.get("matched_rule") or "").lower()
    matched_seed_type = (match.get("matched_seed_type") or "").lower()
    signal_set = set(signal_codes)
    domain = str(match.get("domain_name") or "")
    label = brand.brand_label or brand.brand_name or "the brand"

    if ownership_classification in {"official", "self_owned_related"}:
        return (
            "watchlist",
            f"{domain} appears to be an official or self-owned asset of {label}. Suppressed from frontline triage.",
        )

    if {"credential_collection_surface", "brand_impersonation_content", "clone_detected"} & signal_set:
        return (
            "immediate_attention",
            f"{domain} shows live impersonation, credential-capture, or clone signals targeting {label}. Investigate immediately.",
        )

    if score >= 0.80 and matched_rule in {"typo_candidate", "homograph", "brand_plus_keyword"}:
        return (
            "immediate_attention",
            f"{domain} scored high on both lexical similarity and enrichment signals for {label}. Likely a live threat.",
        )

    if "parked_or_for_sale_page" in signal_set and matched_rule == "exact_label_match" and matched_seed_type == "domain_label":
        return (
            "defensive_gap",
            f"{domain} exactly matches a {label} label but is parked. Assess for defensive registration before it activates.",
        )

    if score >= 0.55:
        return (
            "defensive_gap",
            f"{domain} shows moderate similarity to {label} after enrichment. Review for ownership gap or escalation.",
        )

    return (
        "watchlist",
        f"{domain} shows low post-enrichment signal for {label}. Keep in watchlist unless analyst flags new concern.",
    )


def _derive_ownership(
    brand: MonitoredBrand,
    match: dict,
    tool_results: dict[str, dict],
) -> tuple[str, bool]:
    official_domains = {
        (domain.registrable_domain or domain.domain_name).strip().lower()
        for domain in (brand.domains or [])
        if getattr(domain, "is_active", True)
    }
    target_domain = str(match["domain_name"]).lower()
    if not target_domain.endswith(f".{match['tld']}"):
        target_domain = f"{target_domain}.{match['tld']}"
    if target_domain in official_domains or str(match["domain_name"]).lower() in official_domains:
        return "official", True

    brand_tokens = {
        brand.brand_label,
        normalize_brand_text(brand.brand_name or ""),
        normalize_brand_text(brand.primary_brand_name or ""),
    }
    brand_tokens = {token for token in brand_tokens if token and len(token) >= 4}

    whois_result = (tool_results.get("whois") or {}).get("result") or {}
    registrant_candidates = [
        whois_result.get("registrant_organization"),
        whois_result.get("registrant_name"),
    ]
    for value in registrant_candidates:
        normalized = normalize_brand_text(str(value or ""))
        if normalized and any(token in normalized or normalized in token for token in brand_tokens):
            return "self_owned_related", True

    http_result = (tool_results.get("http_headers") or {}).get("result") or {}
    final_url = str(http_result.get("final_url") or "")
    hostname = urlparse(final_url).hostname or ""
    if hostname:
        try:
            final_host = parse_registrable_domain(hostname).registrable_domain
            if final_host in official_domains:
                return "self_owned_related", True
        except InvalidDomainError:
            pass

    # SSL SAN overlap: if the suspected domain's certificate covers any official domain
    # as a Subject Alternative Name, it's almost certainly self-owned infrastructure.
    # This is far more reliable than nameserver overlap (which would false-positive on
    # shared DNS providers like Cloudflare or Route 53).
    ssl_result = (tool_results.get("ssl_check") or {}).get("result") or {}
    ssl_sans = {
        r
        for san in ((ssl_result.get("certificate") or {}).get("san") or [])
        if san and not san.startswith("*.")
        for r in (_san_registrable(san),)
        if r
    }
    official_registrable = {r for d in official_domains if d for r in (_san_registrable(d),) if r}
    if ssl_sans and ssl_sans & official_registrable:
        return "self_owned_related", True

    creation_date = _parse_datetime_like(str(whois_result.get("creation_date") or ""))
    if creation_date and (datetime.now(timezone.utc) - creation_date).days > 365:
        return "third_party_legitimate", False
    return "third_party_unknown", False


def _derive_disposition(
    match: dict,
    score: float,
    signal_codes: list[str],
    tool_results: dict[str, dict],
    *,
    ownership_classification: str,
    delivery_risk: str,
) -> str:
    signal_set = set(signal_codes)
    page_result = (tool_results.get("suspicious_page") or {}).get("result") or {}
    page_disposition = page_result.get("page_disposition")
    if ownership_classification == "official":
        return "official"
    if ownership_classification == "self_owned_related":
        return "self_owned_related"
    if ownership_classification == "third_party_legitimate":
        return "third_party_legitimate"
    if {"credential_collection_surface", "brand_impersonation_content", "clone_detected"} & signal_set:
        return "likely_phishing"
    if delivery_risk == "high":
        return "mail_spoofing_risk"
    if page_disposition == "parked":
        return "defensive_gap"

    # Honest inconclusive states — never promote to live_but_unknown when data is absent.
    # Exclude screenshot and ssl_check from this check since they can legitimately fail
    # on domains without HTTPS/browser access without implying all intel is missing.
    _intel_tools = {k: v for k, v in tool_results.items() if k not in {"screenshot", "ssl_check"}}
    all_tools_failed = all(
        payload.get("status") != "completed"
        for payload in _intel_tools.values()
    )
    page_tool_status = (tool_results.get("suspicious_page") or {}).get("status")
    if all_tools_failed or page_tool_status not in {"completed"}:
        return "inconclusive"

    if page_disposition == "unreachable":
        return "inconclusive"

    if score >= 0.72:
        return "live_but_unknown"
    return "inconclusive"


def _apply_clone_detection(
    db: Session,
    target: str,
    reference: str,
    score: float,
    signals: list[dict[str, object]],
) -> tuple[float, list[dict[str, object]], dict]:
    """Run website clone comparison and add score adjustments.

    Only called for immediate_attention matches against the brand's primary
    official domain. Returns updated (score, signals, compact_clone_result).
    """
    from app.services.use_cases.tools.website_clone import WebsiteCloneService

    clone_target = f"{target}|{reference}"
    try:
        service = WebsiteCloneService()
        response = service.run(
            db,
            PLACEHOLDER_ORG_ID,
            clone_target,
            triggered_by="similarity_enrichment",
            force=False,
        )
        result = response.result or {}
    except Exception as exc:
        logger.warning("Clone detection failed for %s: %s", target, exc)
        return score, signals, {"status": "error", "error": str(exc)}

    clone_score = float((result.get("scores") or {}).get("overall") or 0.0)
    is_clone = bool(result.get("is_clone"))
    verdict = str(result.get("verdict") or "unknown")
    comparison_state = str(result.get("comparison_state") or "unknown")

    if is_clone or clone_score >= 0.75:
        score += 0.20
        signals.append(_signal(
            "clone_detected",
            "critical",
            f"Target site is a likely clone of the brand's official domain (similarity={clone_score:.2f}).",
        ))
    elif clone_score >= 0.50:
        score += 0.10
        signals.append(_signal(
            "clone_suspected",
            "high",
            f"Target site shows partial structural/textual similarity to the brand's official domain (score={clone_score:.2f}).",
        ))

    compact = {
        "status": response.status,
        "clone_score": round(clone_score, 4),
        "is_clone": is_clone,
        "verdict": verdict,
        "comparison_state": comparison_state,
        "reference": reference,
    }
    return score, signals, compact


def _derive_confidence(tool_results: dict[str, dict], score: float, signal_codes: list[str]) -> float:
    completed = sum(1 for payload in tool_results.values() if payload.get("status") == "completed")
    degraded = sum(
        1
        for payload in tool_results.values()
        if (payload.get("result") or {}).get("data_quality") in {"degraded", "inconclusive"}
    )
    confidence = min(1.0, max(0.15, score * 0.7 + completed * 0.04 - degraded * 0.08 + len(signal_codes) * 0.01))
    return round(confidence, 4)


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
            "lookup_status": result.get("lookup_status"),
            "availability_reason": result.get("availability_reason"),
        }
    if tool_type == "dns_lookup":
        records = result.get("records") or []
        types_found = sorted({str(r.get("type")) for r in records})
        return {
            "record_types": types_found,
            "has_mx": "MX" in types_found,
            "has_a": "A" in types_found or "AAAA" in types_found,
            "has_caa": "CAA" in types_found,
            "nameservers": result.get("nameservers") or [],
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
            "data_quality": result.get("data_quality"),
        }
    if tool_type == "email_security":
        return {"spoofing_risk": result.get("spoofing_risk"), "mta_sts_mode": (result.get("mta_sts") or {}).get("mode")}
    if tool_type == "ssl_check":
        cert = result.get("certificate") or {}
        return {
            "is_valid": result.get("is_valid"),
            "issuer": cert.get("issuer"),
            "days_remaining": cert.get("days_remaining"),
            "san_count": len(cert.get("san") or []),
        }
    if tool_type == "screenshot":
        return {
            "screenshot_url": result.get("screenshot_url"),
            "page_title": result.get("page_title"),
            "final_url": result.get("final_url"),
        }
    if tool_type == "ip_geolocation":
        return {
            "country_code": result.get("country_code"),
            "org": result.get("org"),
            "asn": result.get("asn"),
        }
    return result


def _san_registrable(hostname: str) -> str | None:
    """Extract the registrable domain from a SAN or domain string.

    Used to normalise wildcard-free SAN entries and official domain names
    to a common form before comparing them for SSL co-ownership detection.
    """
    try:
        return parse_registrable_domain(hostname.strip().lower().rstrip(".")).registrable_domain
    except (InvalidDomainError, Exception):
        return None


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
