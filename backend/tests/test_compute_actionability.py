from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.monitored_brand import MonitoredBrand
from app.services.use_cases.compute_actionability import compute_actionability


def build_brand(*, label: str = "gsuplementos", name: str = "Growth Suplementos") -> MonitoredBrand:
    now = datetime.now(timezone.utc)
    return MonitoredBrand(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        brand_name=name,
        primary_brand_name=name,
        brand_label=label,
        keywords=[],
        tld_scope=[],
        noise_mode="balanced",
        notes=None,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


def test_typo_candidate_is_immediate_attention() -> None:
    result = compute_actionability(
        build_brand(),
        domain_name="gsuplementosq.com",
        tld="com",
        score_final=0.92,
        risk_level="critical",
        reasons=["typosquatting"],
        matched_rule="typo_candidate",
        matched_seed_type="domain_label",
        matched_seed_value="gsuplementos",
        matched_channel="registrable_domain",
        domain_first_seen=datetime.now(timezone.utc) - timedelta(days=3),
    )

    assert result["attention_bucket"] == "immediate_attention"
    assert result["actionability_score"] >= 0.68
    assert "typosquatting_pattern" in result["attention_reasons"]


def test_exact_official_label_match_becomes_defensive_gap() -> None:
    result = compute_actionability(
        build_brand(label="comgas", name="Comgas"),
        domain_name="comgas.net",
        tld="net",
        score_final=0.88,
        risk_level="high",
        reasons=["exact_label_match"],
        matched_rule="exact_label_match",
        matched_seed_type="domain_label",
        matched_seed_value="comgas",
        matched_channel="registrable_domain",
        domain_first_seen=datetime.now(timezone.utc) - timedelta(days=200),
    )

    assert result["attention_bucket"] == "defensive_gap"
    assert "exact_match_on_official_label" in result["attention_reasons"]


def test_generic_short_associated_seed_stays_watchlist() -> None:
    result = compute_actionability(
        build_brand(label="tenda", name="Tenda"),
        domain_name="enda.pro",
        tld="pro",
        score_final=0.76,
        risk_level="high",
        reasons=["exact_label_match"],
        matched_rule="exact_label_match",
        matched_seed_type="brand_primary",
        matched_seed_value="enda",
        matched_channel="associated_brand",
        domain_first_seen=datetime.now(timezone.utc) - timedelta(days=400),
    )

    assert result["attention_bucket"] == "watchlist"
    assert "exact_match_on_generic_associated_seed" in result["attention_reasons"]
