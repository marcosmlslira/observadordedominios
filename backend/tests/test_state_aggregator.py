"""Tests for the state aggregator — fingerprint, score, bucket derivation."""
from __future__ import annotations
import sys, uuid, hashlib, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.state_aggregator import (
    compute_state_fingerprint,
    derive_bucket_from_score,
    compute_derived_score,
)


def make_signals(*codes):
    return [{"code": c, "severity": "high", "score_adjustment": 0.1} for c in codes]


# ── fingerprint ───────────────────────────────────────────────

def test_fingerprint_is_stable_for_same_inputs():
    fp1 = compute_state_fingerprint(
        derived_risk="high",
        derived_bucket="defensive_gap",
        signal_codes=["recent_registration", "live_http_surface"],
        latest_tool_results={},
    )
    fp2 = compute_state_fingerprint(
        derived_risk="high",
        derived_bucket="defensive_gap",
        signal_codes=["live_http_surface", "recent_registration"],  # different order
        latest_tool_results={},
    )
    assert fp1 == fp2, "fingerprint must be order-independent"


def test_fingerprint_changes_when_threat_intel_added():
    base = compute_state_fingerprint("high", "defensive_gap", [], {})
    with_hit = compute_state_fingerprint("high", "defensive_gap", ["safe_browsing_hit"], {})
    assert base != with_hit


def test_fingerprint_changes_when_risk_changes():
    fp_medium = compute_state_fingerprint("medium", "watchlist", [], {})
    fp_high = compute_state_fingerprint("high", "defensive_gap", [], {})
    assert fp_medium != fp_high


# ── bucket derivation ─────────────────────────────────────────

def test_bucket_immediate_at_080():
    assert derive_bucket_from_score(0.80) == "immediate_attention"

def test_bucket_immediate_above_080():
    assert derive_bucket_from_score(0.95) == "immediate_attention"

def test_bucket_defensive_at_048():
    assert derive_bucket_from_score(0.48) == "defensive_gap"

def test_bucket_watchlist_below_048():
    assert derive_bucket_from_score(0.47) == "watchlist"


# ── derived score ─────────────────────────────────────────────

def test_derived_score_adds_signal_adjustments():
    signals = [
        {"code": "recent_registration", "score_adjustment": 0.18},
        {"code": "live_http_surface", "score_adjustment": 0.05},
    ]
    # domain_age_days=10 is > 7, so no temporal bonus
    score = compute_derived_score(base_lexical_score=0.50, signals=signals, domain_age_days=10)
    assert abs(score - 0.73) < 0.001  # 0.50 + 0.18 + 0.05 = 0.73


def test_derived_score_clamped_to_1():
    signals = [{"code": "x", "score_adjustment": 0.99}]
    score = compute_derived_score(base_lexical_score=0.90, signals=signals, domain_age_days=5)
    assert score == 1.0


def test_derived_score_temporal_bonus_recent():
    # domain age <= 7 days gets +0.05
    score = compute_derived_score(base_lexical_score=0.50, signals=[], domain_age_days=5)
    assert abs(score - 0.55) < 0.001


def test_derived_score_temporal_penalty_old():
    # domain age > 1 year without signals gets -0.10
    score = compute_derived_score(base_lexical_score=0.50, signals=[], domain_age_days=400)
    assert abs(score - 0.40) < 0.001
