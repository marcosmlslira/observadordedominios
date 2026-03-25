from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.monitored_brand import MonitoredBrand
from app.services.use_cases.enrich_similarity_match import (
    enrich_similarity_match,
    should_auto_enrich_match,
)


def build_brand() -> MonitoredBrand:
    now = datetime.now(timezone.utc)
    return MonitoredBrand(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        brand_name="Growth Suplementos",
        primary_brand_name="Growth Suplementos",
        brand_label="gsuplementos",
        keywords=[],
        tld_scope=[],
        noise_mode="balanced",
        notes=None,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def test_watchlist_match_is_not_auto_enriched() -> None:
    assert not should_auto_enrich_match(
        {
            "attention_bucket": "watchlist",
            "matched_rule": "exact_label_match",
            "matched_seed_type": "domain_label",
            "actionability_score": 0.51,
            "risk_level": "high",
        }
    )


def test_typo_candidate_is_auto_enriched() -> None:
    assert should_auto_enrich_match(
        {
            "attention_bucket": "immediate_attention",
            "matched_rule": "typo_candidate",
            "matched_seed_type": "domain_label",
            "actionability_score": 0.82,
            "risk_level": "critical",
        }
    )


def test_enrichment_reduces_parked_exact_match_to_defensive_gap(monkeypatch) -> None:
    def fake_run_tools(db, domain):
        return {
            "whois": {"status": "completed", "error": None, "result": {"creation_date": "2023-01-01T00:00:00+00:00"}},
            "http_headers": {"status": "completed", "error": None, "result": {"status_code": 200, "final_url": "https://comgas.net", "server": "nginx"}},
            "suspicious_page": {
                "status": "completed",
                "error": None,
                "result": {
                    "risk_level": "low",
                    "page_disposition": "parked",
                    "has_login_form": False,
                    "has_credential_inputs": False,
                    "signals": [],
                },
            },
            "email_security": {"status": "completed", "error": None, "result": {"spoofing_risk": {"level": "medium"}}},
            "ip_geolocation": {"status": "completed", "error": None, "result": {"country_code": "CA", "org": "AWS", "asn": "AS16509"}},
        }

    monkeypatch.setattr(
        "app.services.use_cases.enrich_similarity_match._run_enrichment_tools",
        fake_run_tools,
    )

    enriched = enrich_similarity_match(
        None,
        build_brand(),
        {
            "domain_name": "comgas",
            "tld": "net",
            "matched_rule": "exact_label_match",
            "matched_seed_type": "domain_label",
            "actionability_score": 0.74,
            "attention_bucket": "defensive_gap",
            "attention_reasons": ["exact_match_on_official_label"],
        },
    )

    assert enriched["attention_bucket"] == "defensive_gap"
    assert "parked_or_for_sale_page" in enriched["attention_reasons"]


def test_enrichment_promotes_live_credential_surface(monkeypatch) -> None:
    def fake_run_tools(db, domain):
        return {
            "whois": {"status": "completed", "error": None, "result": {"creation_date": "2026-03-20T00:00:00+00:00"}},
            "http_headers": {"status": "completed", "error": None, "result": {"status_code": 200, "final_url": "https://gsuplementosq.com", "server": "ddos-guard"}},
            "suspicious_page": {
                "status": "completed",
                "error": None,
                "result": {
                    "risk_level": "critical",
                    "page_disposition": "challenge",
                    "has_login_form": True,
                    "has_credential_inputs": True,
                    "signals": [
                        {"category": "brand_impersonation"},
                        {"category": "social_engineering"},
                        {"category": "infrastructure_masking"},
                    ],
                },
            },
            "email_security": {"status": "completed", "error": None, "result": {"spoofing_risk": {"level": "critical"}}},
            "ip_geolocation": {"status": "completed", "error": None, "result": {"country_code": "RU", "org": "DDOS-GUARD LTD", "asn": "AS57724 DDOS-GUARD"}},
        }

    monkeypatch.setattr(
        "app.services.use_cases.enrich_similarity_match._run_enrichment_tools",
        fake_run_tools,
    )

    enriched = enrich_similarity_match(
        None,
        build_brand(),
        {
            "domain_name": "gsuplementosq",
            "tld": "com",
            "matched_rule": "typo_candidate",
            "matched_seed_type": "domain_label",
            "actionability_score": 0.69,
            "attention_bucket": "immediate_attention",
            "attention_reasons": ["typosquatting_pattern"],
        },
    )

    assert enriched["attention_bucket"] == "immediate_attention"
    assert enriched["actionability_score"] > 0.8
    assert "credential_collection_surface" in enriched["attention_reasons"]
