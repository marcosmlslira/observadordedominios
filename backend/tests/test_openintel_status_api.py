from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.v1.routers import ingestion as ingestion_router
from app.core.dependencies import get_current_admin
from app.infra.db.session import get_db


def _override_get_db():
    yield object()


def _override_admin():
    return "admin@observador.com"


def test_openintel_status_returns_counts_and_sorted_items(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    app = FastAPI()
    app.include_router(ingestion_router.router)

    policies = [
        SimpleNamespace(tld="br", is_enabled=True, priority=1),
        SimpleNamespace(tld="uk", is_enabled=True, priority=2),
        SimpleNamespace(tld="fr", is_enabled=False, priority=3),
    ]
    statuses = [
        SimpleNamespace(
            tld="br",
            last_verification_at=now,
            last_available_snapshot_date=date(2026, 4, 13),
            last_ingested_snapshot_date=date(2026, 4, 13),
            last_probe_outcome="already_ingested",
            last_error_message=None,
        ),
        SimpleNamespace(
            tld="uk",
            last_verification_at=now - timedelta(hours=1),
            last_available_snapshot_date=date(2026, 4, 14),
            last_ingested_snapshot_date=date(2026, 4, 13),
            last_probe_outcome="new_snapshot_pending_or_failed",
            last_error_message="timeout",
        ),
    ]

    monkeypatch.setattr(
        ingestion_router.IngestionConfigRepository,
        "list_tld_policies",
        lambda self, source: policies,
    )
    monkeypatch.setattr(
        ingestion_router.OpenintelTldStatusRepository,
        "list_for_tlds",
        lambda self, tlds: statuses,
    )
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_admin] = _override_admin

    try:
        client = TestClient(app)
        response = client.get("/v1/ingestion/openintel/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["source"] == "openintel"
    assert payload["overall_status"] == "warning"
    assert payload["status_counts"] == {
        "up_to_date_no_new_snapshot": 1,
        "new_snapshot_ingested": 0,
        "delayed": 1,
        "failed": 0,
        "no_data": 0,
    }
    assert payload["items"][0]["tld"] == "br"
    assert payload["items"][1]["tld"] == "uk"
    assert payload["items"][2]["tld"] == "fr"
    assert payload["items"][0]["status"] == "up_to_date_no_new_snapshot"
    assert payload["items"][1]["status"] == "delayed"
    assert payload["items"][2]["status"] == "no_data"
    assert payload["last_verification_at"] is not None


def test_openintel_status_failed_overrides_overall_status(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    app = FastAPI()
    app.include_router(ingestion_router.router)

    policies = [SimpleNamespace(tld="br", is_enabled=True, priority=1)]
    statuses = [
        SimpleNamespace(
            tld="br",
            last_verification_at=now,
            last_available_snapshot_date=None,
            last_ingested_snapshot_date=None,
            last_probe_outcome="verification_failed",
            last_error_message="provider error",
        )
    ]

    monkeypatch.setattr(
        ingestion_router.IngestionConfigRepository,
        "list_tld_policies",
        lambda self, source: policies,
    )
    monkeypatch.setattr(
        ingestion_router.OpenintelTldStatusRepository,
        "list_for_tlds",
        lambda self, tlds: statuses,
    )
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_admin] = _override_admin

    try:
        client = TestClient(app)
        response = client.get("/v1/ingestion/openintel/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()

    assert payload["overall_status"] == "failed"
    assert payload["status_counts"]["failed"] == 1
    assert payload["items"][0]["status"] == "failed"
    assert payload["items"][0]["last_error_message"] == "provider error"
