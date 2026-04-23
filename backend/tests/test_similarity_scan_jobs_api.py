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


def _override_get_db():
    yield SimpleNamespace(commit=lambda: None)


def _override_get_current_admin() -> str:
    return "admin@observador.com"


def _build_job(brand_id):
    queued_at = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        brand_id=brand_id,
        requested_tld=None,
        status="queued",
        queued_at=queued_at,
        started_at=None,
        finished_at=None,
        force_full=False,
        effective_tlds=["com.br", "com"],
        last_error=None,
        tld_results={
            "com.br": {
                "status": "queued",
                "candidates": 0,
                "matched": 0,
                "removed": 0,
                "ring_c_candidates": 0,
                "ring_c_matches": 0,
                "ring_c_limit": 1200,
                "error_message": None,
                "started_at": None,
                "finished_at": None,
            },
            "com": {
                "status": "queued",
                "candidates": 0,
                "matched": 0,
                "removed": 0,
                "ring_c_candidates": 0,
                "ring_c_matches": 0,
                "ring_c_limit": 2000,
                "error_message": None,
                "started_at": None,
                "finished_at": None,
            },
        },
    )


def test_trigger_scan_returns_durable_job_metadata(monkeypatch) -> None:
    brand_id = uuid4()
    fake_brand = SimpleNamespace(id=brand_id, tld_scope=["com.br", "com"])
    fake_job = _build_job(brand_id)

    monkeypatch.setattr(MonitoredBrandRepository, "get", lambda self, _brand_id: fake_brand)
    monkeypatch.setattr(SimilarityRepository, "get_active_scan_job_for_brand", lambda self, _brand_id: None)
    monkeypatch.setattr(
        "app.api.v1.routers.monitored_brands.resolve_effective_scan_tlds",
        lambda db, brand, requested_tld: ["com.br", "com"],
    )
    monkeypatch.setattr(SimilarityRepository, "create_scan_job", lambda self, **kwargs: fake_job)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_admin] = _override_get_current_admin
    try:
        client = TestClient(app)
        response = client.post(f"/v1/brands/{brand_id}/scan")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    payload = response.json()
    assert payload["job_id"] == str(fake_job.id)
    assert payload["status"] == "queued"
    assert payload["tlds_effective"] == ["com.br", "com"]
    assert len(payload["results"]) == 2
    assert payload["results"][0]["ring_c_limit"] in {1200, 2000}


def test_matches_response_includes_scan_context(monkeypatch) -> None:
    brand_id = uuid4()
    fake_job = _build_job(brand_id)

    monkeypatch.setattr(SimilarityRepository, "list_matches", lambda self, *args, **kwargs: [])
    monkeypatch.setattr(SimilarityRepository, "count_matches", lambda self, *args, **kwargs: 0)
    monkeypatch.setattr(SimilarityRepository, "get_active_scan_job_for_brand", lambda self, _brand_id: fake_job)
    monkeypatch.setattr(SimilarityRepository, "get_latest_scan_job_for_brand", lambda self, _brand_id: fake_job)

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_admin] = _override_get_current_admin
    try:
        client = TestClient(app)
        response = client.get(f"/v1/brands/{brand_id}/matches")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 0
    assert payload["active_scan"]["job_id"] == str(fake_job.id)
    assert payload["last_scan"]["tlds_effective"] == ["com.br", "com"]
