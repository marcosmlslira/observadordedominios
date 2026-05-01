from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from contextlib import contextmanager
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

sys.modules.setdefault(
    "tldextract",
    SimpleNamespace(
        TLDExtract=lambda cache_dir=None: (lambda value: SimpleNamespace(
            suffix="com.br",
            domain="example",
            registered_domain="example.com.br",
        ))
    ),
)
sys.modules.setdefault(
    "bs4",
    SimpleNamespace(BeautifulSoup=lambda *args, **kwargs: None),
)

from app.api.v1.routers import ingestion as ingestion_router
from app.core.dependencies import get_current_admin
from app.infra.db.session import get_db
from app.repositories.ingestion_run_repository import IngestionRunRepository


def _override_get_db():
    yield object()


def _override_admin():
    return "admin@observador.com"


def test_ingestion_summary_only_returns_active_sources(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    app = FastAPI()
    app.include_router(ingestion_router.router)

    def fake_get_source_summary(self):
        return [
            {
                "source": "czds",
                "total_runs": 2,
                "successful_runs": 1,
                "failed_runs": 0,
                "running_now": 1,
                "last_run_at": now,
                "last_success_at": now,
                "last_status": "running",
                "total_domains_seen": 10,
                "total_domains_inserted": 8,
            }
        ]

    monkeypatch.setattr(IngestionRunRepository, "get_source_summary", fake_get_source_summary)
    monkeypatch.setattr(ingestion_router, "_fetch_ingestion_worker_health", lambda: None)
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_admin] = _override_admin

    try:
        client = TestClient(app)
        response = client.get("/v1/ingestion/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = {item["source"]: item for item in response.json()}

    assert set(payload) == {"czds", "openintel"}
    assert payload["czds"]["mode"] == "Daily cron"
    assert payload["openintel"]["mode"] == "Daily cron"
    assert payload["czds"]["next_expected_run_hint"] is not None
    assert payload["openintel"]["next_expected_run_hint"] is not None


def test_ingestion_summary_marks_running_from_worker_heartbeat(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(ingestion_router.router)

    monkeypatch.setattr(IngestionRunRepository, "get_source_summary", lambda self: [])
    monkeypatch.setattr(
        ingestion_router,
        "_fetch_ingestion_worker_health",
        lambda: {"run_in_progress": True, "current_phase": "openintel"},
    )
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_admin] = _override_admin

    try:
        client = TestClient(app)
        response = client.get("/v1/ingestion/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = {item["source"]: item for item in response.json()}
    assert payload["openintel"]["running_active_count"] == 1
    assert payload["openintel"]["running_now"] == 1
    assert payload["czds"]["running_active_count"] == 0


def test_ingestion_runs_accepts_started_range_filters(monkeypatch) -> None:
    now = datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc)
    app = FastAPI()
    app.include_router(ingestion_router.router)
    seen: dict[str, object] = {}

    def fake_list_runs(
        self,
        *,
        limit,
        offset,
        source,
        status,
        tld,
        started_from,
        started_to,
    ):
        seen.update(
            limit=limit,
            offset=offset,
            source=source,
            status=status,
            tld=tld,
            started_from=started_from,
            started_to=started_to,
        )
        return [
            SimpleNamespace(
                id=uuid4(),
                source="openintel",
                tld="com",
                status="success",
                started_at=now,
                finished_at=now,
                domains_seen=10,
                domains_inserted=8,
                domains_reactivated=0,
                domains_deleted=0,
                error_message=None,
            )
        ]

    monkeypatch.setattr(IngestionRunRepository, "list_runs", fake_list_runs)
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_admin] = _override_admin

    try:
        client = TestClient(app)
        response = client.get(
            "/v1/ingestion/runs"
            "?source=openintel"
            "&started_from=2026-04-10T00:00:00%2B00:00"
            "&started_to=2026-04-24T23:59:59%2B00:00"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert seen["source"] == "openintel"
    assert seen["started_from"] == datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc)
    assert seen["started_to"] == datetime(2026, 4, 24, 23, 59, 59, tzinfo=timezone.utc)
    assert response.json()[0]["domains_inserted"] == 8


def test_tld_status_rejects_legacy_certstream_source() -> None:
    app = FastAPI()
    app.include_router(ingestion_router.router)
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_admin] = _override_admin

    try:
        client = TestClient(app)
        response = client.get("/v1/ingestion/tld-status?source=certstream")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "czds" in response.json()["detail"]
    assert "openintel" in response.json()["detail"]


def test_ingestion_incidents_returns_reason_codes() -> None:
    app = FastAPI()
    app.include_router(ingestion_router.router)

    class FakeDB:
        def execute(self, _query, _params):
            return SimpleNamespace(fetchall=lambda: [
                SimpleNamespace(
                    ts=datetime(2026, 4, 26, 1, 0, tzinfo=timezone.utc),
                    source="openintel",
                    tld="br",
                    id=uuid4(),
                    status="failed",
                    reason_code="stale_recovered",
                    error_message="Recovered stale run",
                )
            ])

    def _fake_db():
        yield FakeDB()

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[get_current_admin] = _override_admin

    try:
        client = TestClient(app)
        response = client.get("/v1/ingestion/incidents?hours=24")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["reason_code"] == "stale_recovered"
