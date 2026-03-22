from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.use_cases.compute_similarity import compute_scores


def test_exact_match_is_not_typosquatting_or_critical() -> None:
    scores = compute_scores(
        label="google",
        brand_label="google",
        brand_keywords=[],
        trigram_sim=1.0,
    )

    assert scores["risk_level"] == "high"
    assert "exact_label_match" in scores["reasons"]
    assert "typosquatting" not in scores["reasons"]
    assert "brand_containment" not in scores["reasons"]


def test_boundary_match_blocks_authority_false_positive() -> None:
    scores = compute_scores(
        label="mckinneyavenuetransitauthority",
        brand_label="itau",
        brand_keywords=["auth", "login"],
        trigram_sim=0.31,
    )

    assert scores["score_brand_hit"] == 0.0
    assert scores["score_keyword"] == 0.0
    assert "brand_containment" not in scores["reasons"]
    assert scores["risk_level"] in {"low", "medium"}


def test_brand_plus_keyword_stays_critical() -> None:
    scores = compute_scores(
        label="google-login",
        brand_label="google",
        brand_keywords=["login"],
        trigram_sim=0.82,
    )

    assert scores["risk_level"] == "critical"
    assert "brand_containment" in scores["reasons"]
    assert "risky_keywords" in scores["reasons"]
