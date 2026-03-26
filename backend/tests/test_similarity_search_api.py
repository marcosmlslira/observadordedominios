from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.dependencies import get_current_admin
from app.infra.db.session import get_db
from app.main import app
from app.repositories.similarity_repository import SimilarityRepository


def _override_get_db():
    yield object()


def _override_get_current_admin() -> str:
    return "admin@observador.com"


def test_similarity_search_contract_and_subdomain_flag(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_search_candidates(self, **kwargs):
        captured.update(kwargs)
        now = datetime.now(timezone.utc)
        return [
            {
                "name": "google.com.br",
                "tld": "com.br",
                "label": "google",
                "first_seen_at": now,
                "last_seen_at": now,
                "sim_trigram": 1.0,
                "edit_dist": 0,
            },
            {
                "name": "google-login.net",
                "tld": "net",
                "label": "google-login",
                "first_seen_at": now,
                "last_seen_at": now,
                "sim_trigram": 0.85,
                "edit_dist": 6,
            },
        ]

    monkeypatch.setattr(SimilarityRepository, "search_candidates", fake_search_candidates)
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_admin] = _override_get_current_admin

    try:
        client = TestClient(app)
        response = client.post(
            "/v1/similarity/search",
            json={
                "query_domain": "Google.com.br",
                "algorithms": ["hybrid"],
                "min_score": 0.4,
                "max_results": 10,
                "include_subdomains": True,
                "tld_allowlist": ["net", "org"],
                "sources": ["czds"],
                "offset": 0,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"]["normalized"] == "google.com.br"
    assert payload["results"][0]["domain"] == "google-login.net"
    assert payload["results"][0]["source"] == "czds"
    assert payload["results"][0]["scores"]["vector"] == 0.0
    assert payload["results"][0]["ownership_classification"] == "third_party_unknown"
    assert payload["pagination"]["returned"] == 1
    assert captured["include_subdomains"] is True
    assert captured["tld_allowlist"] == ["net", "org"]
    assert captured["query_label"] == "google"


def test_similarity_health_reports_latency(monkeypatch) -> None:
    def fake_search_candidates(self, **kwargs):
        now = datetime.now(timezone.utc)
        return [
            {
                "name": "google.net",
                "tld": "net",
                "label": "google",
                "first_seen_at": now,
                "last_seen_at": now,
                "sim_trigram": 1.0,
                "edit_dist": 0,
            },
        ]

    monkeypatch.setattr(SimilarityRepository, "search_candidates", fake_search_candidates)
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_admin] = _override_get_current_admin

    try:
        client = TestClient(app)
        search_response = client.post(
            "/v1/similarity/search",
            json={"query_domain": "google.com"},
        )
        health_response = client.get("/v1/similarity/health")
    finally:
        app.dependency_overrides.clear()

    assert search_response.status_code == 200
    assert health_response.status_code == 200
    payload = health_response.json()
    assert payload["status"] == "ok"
    assert payload["samples"] >= 1
    assert payload["vector_enabled"] is False
