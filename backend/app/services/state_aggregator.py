"""
State aggregator — derives current match state from monitoring events.

This module contains pure functions (no DB access) used by workers and repositories
to recalculate derived state after each new event.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.monitoring_event_repository import MonitoringEventRepository
from app.repositories.match_state_snapshot_repository import MatchStateSnapshotRepository
from app.repositories.brand_domain_health_repository import BrandDomainHealthRepository


# ── Pure functions (no DB) ────────────────────────────────────

def compute_state_fingerprint(
    derived_risk: str,
    derived_bucket: str,
    signal_codes: list[str],
    latest_tool_results: dict,  # {tool_name: result_data}
) -> str:
    """
    SHA-256 of the properties that, when changed, require LLM reassessment.
    Signal codes are sorted for order-independence.
    """
    THREAT_INTEL_CODES = {
        "safe_browsing_hit",
        "phishtank_verified_phish",
        "phishtank_in_database",
        "urlhaus_malware_listed",
    }
    SPOOFING_CODES = {"high_spoofing_risk", "elevated_spoofing_risk"}

    payload = {
        "derived_risk": derived_risk,
        "derived_bucket": derived_bucket,
        "signal_codes": sorted(signal_codes),
        "dns_resolves": any(c in signal_codes for c in ("live_http_surface", "restricted_live_surface")),
        "ssl_revoked": "certificate_revoked" in signal_codes,
        "threat_intel_hits": sorted(c for c in signal_codes if c in THREAT_INTEL_CODES),
        "spoofing_risk": next((c for c in signal_codes if c in SPOOFING_CODES), None),
        "suspicious_page_risk": latest_tool_results.get("suspicious_page", {}).get("risk_level"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()


def derive_bucket_from_score(derived_score: float) -> str:
    """
    Map derived score to attention bucket.
    Special signals (clone_detected, credential+impersonation) are handled separately
    by callers before invoking this function.
    """
    if derived_score >= 0.80:
        return "immediate_attention"
    if derived_score >= 0.48:
        return "defensive_gap"
    return "watchlist"


def derive_risk_from_signals(signal_codes: list[str]) -> str:
    """Derive risk level from the highest-severity signal present."""
    CRITICAL_SIGNALS = {
        "credential_collection_surface", "safe_browsing_hit",
        "phishtank_verified_phish", "certificate_revoked",
    }
    HIGH_SIGNALS = {
        "recent_registration", "mail_only_infrastructure",
        "brand_impersonation_content", "phishtank_in_database",
        "urlhaus_malware_listed", "high_spoofing_risk",
    }
    MEDIUM_SIGNALS = {
        "fresh_registration", "live_http_surface", "unusual_hosting_country",
        "shielded_hosting_provider", "elevated_spoofing_risk",
    }
    if any(s in signal_codes for s in CRITICAL_SIGNALS):
        return "critical"
    if any(s in signal_codes for s in HIGH_SIGNALS):
        return "high"
    if any(s in signal_codes for s in MEDIUM_SIGNALS):
        return "medium"
    return "low"


def compute_derived_score(
    *,
    base_lexical_score: float,
    signals: list[dict],
    domain_age_days: int | None,
) -> float:
    """
    Calculate derived_score = base + signal adjustments + temporal bonus.
    Result is clamped to [0, 1].
    """
    total = base_lexical_score + sum(
        s.get("score_adjustment", 0) for s in signals
    )

    # Temporal bonus/penalty
    if domain_age_days is not None:
        if domain_age_days <= 7:
            total += 0.05
        elif domain_age_days > 1095:  # > 3 years
            total -= 0.15
        elif domain_age_days > 365:   # > 1 year, no negative signals
            has_negative = any(
                s.get("score_adjustment", 0) < 0 for s in signals
            )
            if not has_negative:
                total -= 0.10

    return max(0.0, min(1.0, total))


# ── DB-aware aggregation ──────────────────────────────────────

class StateAggregator:
    """
    Recalculates match_state_snapshot and brand_domain_health
    after new monitoring_event records are created.

    Workers create events, then call aggregator methods to update
    the materialized state. API reads the materialized state.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.event_repo = MonitoringEventRepository(db)
        self.snapshot_repo = MatchStateSnapshotRepository(db)
        self.health_repo = BrandDomainHealthRepository(db)

    def recalculate_match_snapshot(
        self,
        *,
        match_id: UUID,
        brand_id: UUID,
        organization_id: UUID,
        base_lexical_score: float,
        domain_age_days: int | None = None,
    ) -> None:
        """
        Read all recent events for this match, aggregate signals,
        compute derived state, and upsert match_state_snapshot.
        """
        events = self.event_repo.list_for_match(match_id=match_id, limit=200)

        # Collect all signals from all events (deduplicate by code, keep latest)
        signals_by_code: dict[str, dict] = {}
        latest_tool_results: dict[str, dict] = {}

        for evt in reversed(events):  # oldest first so latest wins
            if evt.signals:
                for sig in evt.signals:
                    signals_by_code[sig["code"]] = {
                        **sig,
                        "source_tool": evt.tool_name,
                        "source_event_id": str(evt.id),
                    }
            if evt.tool_name and evt.result_data:
                latest_tool_results[evt.tool_name] = evt.result_data

        active_signals = list(signals_by_code.values())
        signal_codes = list(signals_by_code.keys())

        # Derive score and classification
        derived_score = compute_derived_score(
            base_lexical_score=base_lexical_score,
            signals=active_signals,
            domain_age_days=domain_age_days,
        )

        # Force immediate_attention for specific signal combos
        if "clone_detected" in signal_codes:
            derived_score = max(derived_score, 0.95)
        if "credential_collection_surface" in signal_codes and "brand_impersonation_content" in signal_codes:
            derived_score = max(derived_score, 0.85)

        derived_bucket = derive_bucket_from_score(derived_score)
        derived_risk = derive_risk_from_signals(signal_codes)

        state_fingerprint = compute_state_fingerprint(
            derived_risk=derived_risk,
            derived_bucket=derived_bucket,
            signal_codes=signal_codes,
            latest_tool_results=latest_tool_results,
        )

        events_hash = hashlib.sha256(
            json.dumps(sorted(str(e.id) for e in events)).encode()
        ).hexdigest()

        self.snapshot_repo.upsert(
            match_id=match_id,
            brand_id=brand_id,
            organization_id=organization_id,
            derived_score=derived_score,
            derived_bucket=derived_bucket,
            derived_risk=derived_risk,
            active_signals=active_signals,
            signal_codes=signal_codes,
            state_fingerprint=state_fingerprint,
            last_derived_at=datetime.now(timezone.utc),
            events_hash=events_hash,
        )
        self.db.commit()

    def recalculate_domain_health(
        self,
        *,
        brand_domain_id: UUID,
        brand_id: UUID,
        organization_id: UUID,
    ) -> None:
        """
        Read latest health check events for this domain, derive overall_status,
        and upsert brand_domain_health.
        """
        HEALTH_TOOLS = [
            "dns_lookup", "ssl_check", "http_headers", "email_security",
            "subdomain_takeover", "blacklist_check", "safe_browsing",
            "urlhaus", "phishtank", "suspicious_page",
        ]

        latest_results: dict[str, dict] = {}
        latest_event_ids: list[str] = []

        for tool in HEALTH_TOOLS:
            evt = self.event_repo.fetch_latest_for_domain_tool(
                brand_domain_id=brand_domain_id,
                tool_name=tool,
            )
            if evt:
                latest_results[tool] = evt.result_data or {}
                latest_event_ids.append(str(evt.id))

        # Derive boolean health fields from tool results
        health_fields = _derive_health_fields(latest_results)
        overall_status = _derive_overall_status(health_fields)

        state_fingerprint = hashlib.sha256(
            json.dumps(health_fields, sort_keys=True).encode()
        ).hexdigest()

        self.health_repo.upsert(
            brand_domain_id=brand_domain_id,
            brand_id=brand_id,
            organization_id=organization_id,
            overall_status=overall_status,
            last_check_at=datetime.now(timezone.utc),
            last_event_ids=latest_event_ids,
            state_fingerprint=state_fingerprint,
            **health_fields,
        )
        self.db.commit()


def _derive_health_fields(results: dict[str, dict]) -> dict:
    """Extract boolean health indicators from raw tool result data."""
    fields: dict = {}

    # DNS
    dns = results.get("dns_lookup", {})
    records = dns.get("records", [])
    fields["dns_ok"] = len(records) > 0 if dns else None

    # SSL
    ssl = results.get("ssl_check", {})
    if ssl:
        cert = ssl.get("certificate") or {}
        days = cert.get("days_remaining")
        ocsp = cert.get("ocsp_status", "unknown")
        fields["ssl_ok"] = ssl.get("is_valid", False) and ocsp != "revoked"
        fields["ssl_days_remaining"] = days
    else:
        fields["ssl_ok"] = None
        fields["ssl_days_remaining"] = None

    # Email security
    email = results.get("email_security", {})
    if email:
        raw_sr = email.get("spoofing_risk")
        sr_level = raw_sr.get("level") if isinstance(raw_sr, dict) else raw_sr
        fields["email_security_ok"] = sr_level in ("none", "low")
        fields["spoofing_risk"] = sr_level
    else:
        fields["email_security_ok"] = None
        fields["spoofing_risk"] = None

    # HTTP headers
    headers = results.get("http_headers", {})
    if headers:
        sec = headers.get("security_headers", [])
        present = sum(1 for h in sec if h.get("present"))
        total = len(sec)
        if total == 0:
            fields["headers_score"] = None
        elif present == total:
            fields["headers_score"] = "good"
        elif present >= total // 2:
            fields["headers_score"] = "partial"
        else:
            fields["headers_score"] = "poor"
    else:
        fields["headers_score"] = None

    # Subdomain takeover
    takeover = results.get("subdomain_takeover", {})
    if takeover:
        vulnerable = takeover.get("vulnerable_subdomains", [])
        fields["takeover_risk"] = len(vulnerable) > 0
    else:
        fields["takeover_risk"] = None

    # Reputation
    bl = results.get("blacklist_check", {})
    fields["blacklisted"] = bool(bl.get("listed_count", 0) > 0) if bl else None

    sb = results.get("safe_browsing", {})
    fields["safe_browsing_hit"] = bool(sb.get("threats")) if sb else None

    uh = results.get("urlhaus", {})
    fields["urlhaus_hit"] = bool(uh.get("listed")) if uh else None

    pt = results.get("phishtank", {})
    fields["phishtank_hit"] = bool(pt.get("in_database")) if pt else None

    sp = results.get("suspicious_page", {})
    if sp:
        risk = sp.get("risk_level", "safe")
        fields["suspicious_content"] = risk not in ("safe", "inconclusive", "protected")
    else:
        fields["suspicious_content"] = None

    return fields


def _derive_overall_status(fields: dict) -> str:
    """Derive overall health status from boolean fields."""
    # Critical: any reputation hit or revoked SSL
    if any([
        fields.get("safe_browsing_hit"),
        fields.get("urlhaus_hit"),
        fields.get("phishtank_hit"),
        fields.get("blacklisted"),
        fields.get("suspicious_content"),
        fields.get("ssl_ok") is False,
    ]):
        return "critical"

    # Warning: email security issues, takeover risk, SSL expiring soon
    days_remaining = fields.get("ssl_days_remaining")
    if any([
        fields.get("email_security_ok") is False,
        fields.get("takeover_risk"),
        fields.get("headers_score") == "poor",
        days_remaining is not None and days_remaining < 30,
    ]):
        return "warning"

    # Unknown: not checked yet
    if all(v is None for v in fields.values()):
        return "unknown"

    return "healthy"
