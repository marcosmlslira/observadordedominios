from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.dependencies import get_current_admin
from app.infra.db.session import get_db
from app.main import app
from app.repositories.monitored_brand_repository import MonitoredBrandRepository
from app.repositories.similarity_repository import SimilarityRepository
from app.services.seed_generation import generate_deterministic_seeds
from app.services.use_cases.compute_similarity import (
    compute_scores,
    compute_seeded_scores,
    generate_typo_candidates,
)
from app.services.use_cases.run_similarity_scan import run_similarity_scan


def test_generate_deterministic_seeds_emits_punycode_homograph_seed() -> None:
    seeds = generate_deterministic_seeds("bradesco", [], [])
    homograph_values = {
        seed["seed_value"]
        for seed in seeds
        if seed["seed_type"] == "homograph_base"
    }

    assert "xn--brdesco-3fg" in homograph_values


def test_generate_typo_candidates_includes_punycode_confusable_variant() -> None:
    candidates = generate_typo_candidates("bradesco")

    assert "xn--brdesco-3fg" in candidates


def test_compute_scores_detects_homograph_from_punycode_label() -> None:
    scores = compute_scores(
        label="xn--brdesco-3fg",
        brand_label="bradesco",
        brand_keywords=[],
        trigram_sim=0.0,
    )

    assert scores["score_homograph"] == 1.0
    assert "homograph_attack" in scores["reasons"]
    assert scores["score_final"] >= 0.55


def test_compute_seeded_scores_promotes_punycode_homograph_above_threshold() -> None:
    scores = compute_seeded_scores(
        label="xn--brdesco-3fg",
        seed_value="bradesco",
        brand_keywords=[],
        trigram_sim=0.0,
        seed_weight=0.85,
        channel_scope="registrable_domain",
    )

    assert scores["score_final"] >= 0.5
    assert "homograph_attack" in scores["reasons"]
    assert scores["risk_level"] in {"medium", "high", "critical"}


def test_google_real_punycode_homographs_score_as_homograph_attack() -> None:
    for label in ("xn--gogle-jye", "xn--gogle-rce"):
        scores = compute_scores(
            label=label,
            brand_label="google",
            brand_keywords=[],
            trigram_sim=0.0,
        )

        assert scores["score_homograph"] == 1.0
        assert "homograph_attack" in scores["reasons"]


def test_paypal_real_punycode_homograph_scores_as_homograph_attack() -> None:
    scores = compute_scores(
        label="xn--pypal-4ve",
        brand_label="paypal",
        brand_keywords=[],
        trigram_sim=0.0,
    )

    assert scores["score_homograph"] == 1.0
    assert "homograph_attack" in scores["reasons"]


def test_seed_generation_emits_google_and_paypal_real_world_punycode_variants() -> None:
    google_homographs = {
        seed["seed_value"]
        for seed in generate_deterministic_seeds("google", [], [])
        if seed["seed_type"] == "homograph_base"
    }
    paypal_homographs = {
        seed["seed_value"]
        for seed in generate_deterministic_seeds("paypal", [], [])
        if seed["seed_type"] == "homograph_base"
    }

    assert "xn--gogle-jye" in google_homographs
    assert "xn--gogle-rce" in google_homographs
    assert "xn--pypal-4ve" in paypal_homographs


def test_run_similarity_scan_persists_google_ring_c_homographs(monkeypatch) -> None:
    brand_id = uuid4()
    domain_seed_id = uuid4()
    homograph_seed_id = uuid4()
    watermark_day = 20260101
    captured: dict[str, object] = {"upserted": []}

    brand = SimpleNamespace(
        id=brand_id,
        brand_name="Google",
        brand_label="google",
        keywords=[],
        noise_mode="standard",
        domains=[
            SimpleNamespace(
                domain_name="google.com",
                registrable_domain="google.com",
                is_active=True,
            )
        ],
        seeds=[
            SimpleNamespace(
                id=domain_seed_id,
                seed_value="google",
                seed_type="domain_label",
                channel_scope="registrable_domain",
                base_weight=1.0,
                is_active=True,
            ),
            SimpleNamespace(
                id=homograph_seed_id,
                seed_value="xn--gogle-jye",
                seed_type="homograph_base",
                channel_scope="registrable_domain",
                base_weight=0.85,
                is_active=True,
            ),
        ],
    )
    cursor = SimpleNamespace(scan_phase="initial", watermark_day=None)

    class _FakeResult:
        def scalar(self):
            return watermark_day

    class _FakeDb:
        def commit(self):
            return None

        def rollback(self):
            return None

        def execute(self, *_args, **_kwargs):
            return _FakeResult()

    monkeypatch.setattr(SimilarityRepository, "get_or_create_cursor", lambda self, *_args, **_kwargs: cursor)
    monkeypatch.setattr(SimilarityRepository, "start_scan", lambda self, _cursor: None)
    monkeypatch.setattr(SimilarityRepository, "finish_scan", lambda self, _cursor, **_kwargs: None)
    monkeypatch.setattr(SimilarityRepository, "fetch_candidates_exact", lambda self, **_kwargs: [])
    monkeypatch.setattr(SimilarityRepository, "fetch_candidates", lambda self, **_kwargs: [])

    def fake_fetch_candidates_punycode(self, *, brand_label, tld, watermark_day=None, limit=0):
        captured["brand_label"] = brand_label
        captured["ring_c_tld"] = tld
        captured["ring_c_limit"] = limit
        captured["ring_c_watermark"] = watermark_day
        return [
            {
                "name": "xn--gogle-jye.com",
                "tld": "com",
                "label": "xn--gogle-jye",
                "added_day": 20260101,
                "sim_trigram": 0.0,
                "edit_dist": 8,
            },
            {
                "name": "xn--gogle-rce.com",
                "tld": "com",
                "label": "xn--gogle-rce",
                "added_day": 20260101,
                "sim_trigram": 0.0,
                "edit_dist": 8,
            },
        ]

    def fake_upsert_matches(self, matches):
        captured["upserted"] = matches
        return len(matches)

    monkeypatch.setattr(SimilarityRepository, "fetch_candidates_punycode", fake_fetch_candidates_punycode)
    monkeypatch.setattr(SimilarityRepository, "upsert_matches", fake_upsert_matches)
    monkeypatch.setattr(SimilarityRepository, "delete_subdomain_matches", lambda self, *_args, **_kwargs: 0)
    monkeypatch.setattr(SimilarityRepository, "reconcile_matches_for_brand_tld", lambda self, *_args, **_kwargs: 0)
    monkeypatch.setattr(SimilarityRepository, "delete_matches_for_brand_tld", lambda self, *_args, **_kwargs: 0)

    metrics = run_similarity_scan(_FakeDb(), brand, "com", force_full=True)

    assert captured["brand_label"] == "google"
    assert captured["ring_c_tld"] == "com"
    assert captured["ring_c_limit"] == 2000
    assert metrics["matched"] == 2
    assert metrics["ring_c_candidates"] == 2
    assert metrics["ring_c_matches"] == 2

    upserted = {row["domain_name"]: row for row in captured["upserted"]}
    assert "xn--gogle-jye.com" in upserted
    assert "xn--gogle-rce.com" in upserted
    assert upserted["xn--gogle-jye.com"]["matched_seed_value"] == "google"
    assert upserted["xn--gogle-jye.com"]["matched_seed_type"] == "domain_label"
    assert upserted["xn--gogle-jye.com"]["matched_rule"] == "homograph"
    assert "homograph_attack" in upserted["xn--gogle-jye.com"]["reasons"]
    assert upserted["xn--gogle-jye.com"]["score_homograph"] == 1.0
    assert upserted["xn--gogle-rce.com"]["matched_seed_value"] == "google"
    assert "homograph_attack" in upserted["xn--gogle-rce.com"]["reasons"]


def test_run_similarity_scan_persists_paypal_ring_c_homograph(monkeypatch) -> None:
    brand_id = uuid4()
    domain_seed_id = uuid4()
    watermark_day = 20260101
    captured: dict[str, object] = {"upserted": []}

    brand = SimpleNamespace(
        id=brand_id,
        brand_name="PayPal",
        brand_label="paypal",
        keywords=[],
        noise_mode="standard",
        domains=[
            SimpleNamespace(
                domain_name="paypal.com",
                registrable_domain="paypal.com",
                is_active=True,
            )
        ],
        seeds=[
            SimpleNamespace(
                id=domain_seed_id,
                seed_value="paypal",
                seed_type="domain_label",
                channel_scope="registrable_domain",
                base_weight=1.0,
                is_active=True,
            ),
        ],
    )
    cursor = SimpleNamespace(scan_phase="initial", watermark_day=None)

    class _FakeResult:
        def scalar(self):
            return watermark_day

    class _FakeDb:
        def commit(self):
            return None

        def rollback(self):
            return None

        def execute(self, *_args, **_kwargs):
            return _FakeResult()

    monkeypatch.setattr(SimilarityRepository, "get_or_create_cursor", lambda self, *_args, **_kwargs: cursor)
    monkeypatch.setattr(SimilarityRepository, "start_scan", lambda self, _cursor: None)
    monkeypatch.setattr(SimilarityRepository, "finish_scan", lambda self, _cursor, **_kwargs: None)
    monkeypatch.setattr(SimilarityRepository, "fetch_candidates_exact", lambda self, **_kwargs: [])
    monkeypatch.setattr(SimilarityRepository, "fetch_candidates", lambda self, **_kwargs: [])

    def fake_fetch_candidates_punycode(self, *, brand_label, tld, watermark_day=None, limit=0):
        captured["brand_label"] = brand_label
        captured["ring_c_tld"] = tld
        captured["ring_c_limit"] = limit
        captured["ring_c_watermark"] = watermark_day
        return [
            {
                "name": "xn--pypal-4ve.com",
                "tld": "com",
                "label": "xn--pypal-4ve",
                "added_day": 20260101,
                "sim_trigram": 0.0,
                "edit_dist": 8,
            }
        ]

    def fake_upsert_matches(self, matches):
        captured["upserted"] = matches
        return len(matches)

    monkeypatch.setattr(SimilarityRepository, "fetch_candidates_punycode", fake_fetch_candidates_punycode)
    monkeypatch.setattr(SimilarityRepository, "upsert_matches", fake_upsert_matches)
    monkeypatch.setattr(SimilarityRepository, "delete_subdomain_matches", lambda self, *_args, **_kwargs: 0)
    monkeypatch.setattr(SimilarityRepository, "reconcile_matches_for_brand_tld", lambda self, *_args, **_kwargs: 0)
    monkeypatch.setattr(SimilarityRepository, "delete_matches_for_brand_tld", lambda self, *_args, **_kwargs: 0)

    metrics = run_similarity_scan(_FakeDb(), brand, "com", force_full=True)

    assert captured["brand_label"] == "paypal"
    assert captured["ring_c_tld"] == "com"
    assert captured["ring_c_limit"] == 2000
    assert metrics["matched"] == 1
    assert metrics["ring_c_candidates"] == 1
    assert metrics["ring_c_matches"] == 1

    upserted = captured["upserted"][0]
    assert upserted["domain_name"] == "xn--pypal-4ve.com"
    assert upserted["matched_seed_value"] == "paypal"
    assert upserted["matched_seed_type"] == "domain_label"
    assert upserted["matched_rule"] == "homograph"
    assert upserted["score_homograph"] == 1.0
    assert "homograph_attack" in upserted["reasons"]


def _override_get_db():
    yield SimpleNamespace(commit=lambda: None, refresh=lambda _: None)


def _override_get_current_admin() -> str:
    return "admin@observador.com"


def test_regenerate_brand_seeds_honors_include_llm(monkeypatch) -> None:
    brand_id = uuid4()
    fake_brand = SimpleNamespace(id=brand_id, seeds=[])
    captured: dict[str, object] = {}

    monkeypatch.setattr(MonitoredBrandRepository, "get", lambda self, _brand_id: fake_brand)

    def fake_regenerate(repo, brand, *, run_llm: bool = True):
        captured["brand"] = brand
        captured["run_llm"] = run_llm
        return brand

    monkeypatch.setattr(
        "app.api.v1.routers.monitored_brands.regenerate_seeds_for_brand",
        fake_regenerate,
    )

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_admin] = _override_get_current_admin
    try:
        client = TestClient(app)
        response = client.post(
            f"/v1/brands/{brand_id}/seeds/regenerate?include_llm=false"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert captured["brand"] is fake_brand
    assert captured["run_llm"] is False
