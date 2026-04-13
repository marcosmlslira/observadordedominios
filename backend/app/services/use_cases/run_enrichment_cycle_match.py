"""Enrichment use case for one similarity match.

Creates monitoring_event per tool, recalculates match_state_snapshot,
applies auto-dismiss rules (spec §6.1).
"""
from __future__ import annotations

import importlib
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.monitored_brand import MonitoredBrand
from app.models.similarity_match import SimilarityMatch
from app.repositories.monitoring_event_repository import MonitoringEventRepository
from app.services.state_aggregator import StateAggregator

logger = logging.getLogger(__name__)

_WAVE1_TOOLS = [
    ("dns_lookup",      "app.services.use_cases.tools.dns_lookup.DnsLookupService"),
    ("whois",           "app.services.use_cases.tools.whois_lookup.WhoisLookupService"),
    ("ssl_check",       "app.services.use_cases.tools.ssl_check.SslCheckService"),
    ("http_headers",    "app.services.use_cases.tools.http_headers.HttpHeadersService"),
    ("screenshot",      "app.services.use_cases.tools.screenshot_capture.ScreenshotCaptureService"),
    ("suspicious_page", "app.services.use_cases.tools.suspicious_page.SuspiciousPageService"),
]

_WAVE2_TOOLS = [
    ("email_security",  "app.services.use_cases.tools.email_security.EmailSecurityService"),
    ("ip_geolocation",  "app.services.use_cases.tools.ip_geolocation.IpGeolocationService"),
    ("blacklist_check", "app.services.use_cases.tools.blacklist_check.BlacklistCheckService"),
    ("safe_browsing",   "app.services.use_cases.tools.safe_browsing_check.SafeBrowsingCheckService"),
    ("urlhaus",         "app.services.use_cases.tools.urlhaus_check.UrlhausCheckService"),
    ("phishtank",       "app.services.use_cases.tools.phishtank_check.PhishTankCheckService"),
]

_CLONE_TOOL = ("website_clone", "app.services.use_cases.tools.website_clone.WebsiteCloneService")

_HIGH_RISK_SEVERITIES = {"critical", "high"}


def _run_tool(tool_class_path: str, domain: str) -> dict:
    module_path, class_name = tool_class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    service = getattr(module, class_name)()
    result = service._execute(domain)
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if hasattr(result, "dict"):
        return result.dict()
    return result if isinstance(result, dict) else {}


def _check_auto_dismiss(
    *,
    derived_score: float,
    active_signals: list[dict],
    matched_rule: str | None,
    tool_results: dict[str, dict],
) -> tuple[bool, str | None]:
    """Check all 3 auto-dismiss rules (spec §6.1). Returns (should_dismiss, rule_name)."""
    signal_severities = {s.get("severity", "low") for s in active_signals}
    has_critical_or_high = bool(signal_severities & _HIGH_RISK_SEVERITIES)

    # Rule 2 — Low score post-enrichment
    is_exact = (matched_rule or "") == "exact_label_match"
    if derived_score < 0.35 and not has_critical_or_high and not is_exact:
        return True, "low_score_post_enrichment"

    # Rule 1 — Dead domain
    dns = tool_results.get("dns_lookup", {})
    email = tool_results.get("email_security", {})
    whois = tool_results.get("whois", {})
    dns_has_records = bool(dns.get("records"))
    has_mx = bool(
        email.get("mx_records")
        or dns.get("mx_records")
        or (dns.get("records") and any(r.get("type") == "MX" for r in dns.get("records", [])))
    )
    domain_age_days = whois.get("domain_age_days") or whois.get("age_days")
    if (
        not dns_has_records
        and not has_mx
        and domain_age_days and int(domain_age_days) > 365
        and not has_critical_or_high
    ):
        return True, "dead_domain"

    # Rule 3 — Parked/for sale
    page = tool_results.get("suspicious_page", {})
    sb = tool_results.get("safe_browsing", {})
    uh = tool_results.get("urlhaus", {})
    pt = tool_results.get("phishtank", {})
    parked = page.get("page_type") in ("parked", "for_sale")
    sb_clean = not bool(sb.get("threats"))
    uh_clean = not bool(uh.get("listed"))
    pt_clean = not bool(pt.get("in_database"))
    if parked and not has_mx and sb_clean and uh_clean and pt_clean:
        return True, "parked_for_sale"

    return False, None


def run_enrichment_cycle_match(
    db: Session,
    match: SimilarityMatch,
    *,
    brand: MonitoredBrand,
    cycle_id: UUID,
) -> dict:
    """Run enrichment tools for one match, create events, recalculate snapshot.

    Returns:
        {"tools_run": int, "tools_failed": int, "auto_dismissed": bool,
         "dismiss_rule": str | None, "derived_bucket": str}
    """
    domain = match.domain_name
    if not domain.endswith(f".{match.tld}"):
        domain = f"{domain}.{match.tld}"

    organization_id = brand.organization_id
    event_repo = MonitoringEventRepository(db)
    tool_results: dict[str, dict] = {}
    tools_run = 0
    tools_failed = 0

    all_tools = list(_WAVE1_TOOLS) + list(_WAVE2_TOOLS)

    if (
        getattr(match, "attention_bucket", "") == "immediate_attention"
        and brand.domains
    ):
        all_tools.append(_CLONE_TOOL)

    for tool_name, tool_class_path in all_tools:
        if event_repo.event_exists_for_cycle(
            cycle_id=cycle_id,
            tool_name=tool_name,
            match_id=match.id,
        ):
            logger.debug("Skipping %s for match=%s (already in cycle)", tool_name, match.id)
            tools_run += 1
            continue

        try:
            result_data = _run_tool(tool_class_path, domain)
            tool_results[tool_name] = result_data
            event_repo.create(
                organization_id=organization_id,
                brand_id=match.brand_id,
                match_id=match.id,
                cycle_id=cycle_id,
                event_type="tool_execution",
                event_source="enrichment",
                tool_name=tool_name,
                result_data=result_data,
            )
            tools_run += 1
        except Exception:
            tools_failed += 1
            logger.exception("enrichment tool=%s match=%s FAILED", tool_name, match.id)
            event_repo.create(
                organization_id=organization_id,
                brand_id=match.brand_id,
                match_id=match.id,
                cycle_id=cycle_id,
                event_type="tool_execution",
                event_source="enrichment",
                tool_name=tool_name,
                result_data={"error": "tool_failed"},
            )

    db.flush()

    domain_age_days = None
    whois_result = tool_results.get("whois", {})
    if whois_result:
        domain_age_days = whois_result.get("domain_age_days") or whois_result.get("age_days")

    aggregator = StateAggregator(db)
    aggregator.recalculate_match_snapshot(
        match_id=match.id,
        brand_id=match.brand_id,
        organization_id=organization_id,
        base_lexical_score=float(match.score_final or 0.5),
        domain_age_days=int(domain_age_days) if domain_age_days else None,
    )
    # StateAggregator commits internally

    from app.repositories.match_state_snapshot_repository import MatchStateSnapshotRepository
    snapshot = MatchStateSnapshotRepository(db).get_by_match(match.id)

    # ── Ownership detection — suppress self-owned domains before LLM / threat counts ──
    from sqlalchemy import text as _text
    from app.services.use_cases.enrich_similarity_match import _derive_ownership

    match_dict = {
        "domain_name": match.domain_name,
        "tld": match.tld,
        "attention_bucket": getattr(match, "attention_bucket", ""),
    }
    ownership_class, self_owned = _derive_ownership(brand, match_dict, tool_results)
    if self_owned:
        db.execute(
            _text(
                "UPDATE similarity_match"
                " SET auto_disposition = 'self_owned',"
                "     auto_disposition_reason = 'same_registrant_detected',"
                "     self_owned = TRUE,"
                "     ownership_classification = :ownership"
                " WHERE id = :match_id"
            ),
            {"ownership": ownership_class, "match_id": match.id},
        )
        event_repo.create(
            organization_id=organization_id,
            brand_id=match.brand_id,
            match_id=match.id,
            cycle_id=cycle_id,
            event_type="auto_disposition",
            event_source="enrichment",
            tool_name=None,
            result_data={
                "ownership_classification": ownership_class,
                "auto_disposition": "self_owned",
                "self_owned": True,
            },
        )
        db.commit()
        logger.info(
            "Self-owned match=%s ownership=%s domain=%s",
            match.id, ownership_class, match.domain_name,
        )
        return {
            "tools_run": tools_run,
            "tools_failed": tools_failed,
            "auto_dismissed": False,
            "dismiss_rule": None,
            "derived_bucket": snapshot.derived_bucket if snapshot else "watchlist",
        }
    # ── End ownership detection ──────────────────────────────────────────────────

    auto_dismissed = False
    dismiss_rule = None

    if snapshot:
        auto_dismissed, dismiss_rule = _check_auto_dismiss(
            derived_score=snapshot.derived_score,
            active_signals=snapshot.active_signals or [],
            matched_rule=getattr(match, "matched_rule", None),
            tool_results=tool_results,
        )

        if auto_dismissed:
            from sqlalchemy import text
            db.execute(
                text(
                    "UPDATE similarity_match"
                    " SET auto_disposition = 'auto_dismissed',"
                    "     auto_disposition_reason = :reason"
                    " WHERE id = :match_id"
                ),
                {"reason": dismiss_rule, "match_id": match.id},
            )
            event_repo.create(
                organization_id=organization_id,
                brand_id=match.brand_id,
                match_id=match.id,
                cycle_id=cycle_id,
                event_type="auto_disposition",
                event_source="enrichment",
                tool_name=None,
                result_data={"rule": dismiss_rule, "auto_dismissed": True},
            )
            db.commit()
            logger.info(
                "Auto-dismissed match=%s rule=%s derived_score=%.3f",
                match.id, dismiss_rule, snapshot.derived_score,
            )

    return {
        "tools_run": tools_run,
        "tools_failed": tools_failed,
        "auto_dismissed": auto_dismissed,
        "dismiss_rule": dismiss_rule,
        "derived_bucket": snapshot.derived_bucket if snapshot else "watchlist",
    }
