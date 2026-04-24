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


def test_ingestion_summary_includes_crtsh_hints(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    app = FastAPI()
    app.include_router(ingestion_router.router)

    def fake_get_source_summary(self):
        return [
            {
                "source": "certstream",
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
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_admin] = _override_admin

    try:
        client = TestClient(app)
        response = client.get("/v1/ingestion/summary")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = {item["source"]: item for item in response.json()}

    assert payload["certstream"]["mode"] == "Realtime stream"
    assert payload["certstream"]["status_hint"] == "Streaming continuously from CertStream."

    assert payload["crtsh"]["mode"] == "Daily cron"
    assert payload["crtsh"]["total_runs"] == 0
    assert payload["crtsh"]["status_hint"] == "crt.sh is scheduled and waiting for the next daily cron."
    assert payload["crtsh"]["next_expected_run_hint"] is not None

    assert "crtsh-bulk" not in payload


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


def test_tld_coverage_uses_short_lived_session_without_checkpoint_queries(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(ingestion_router.router)

    class FakePolicy:
        def __init__(self, tld: str) -> None:
            self.tld = tld
            self.last_error_code = None
            self.suspended_until = None

    class FakeSession:
        pass

    fake_session = FakeSession()
    seen: dict[str, object] = {}

    @contextmanager
    def fake_session_local():
        seen["session_opened"] = True
        yield fake_session
        seen["session_closed"] = True

    def fake_list_all(self):
        assert self.db is fake_session
        return [FakePolicy("com")]

    def fake_resolve(db, *, authorized_czds_tlds=None, policies=None, czds_client=None):
        assert db is fake_session
        seen["resolved_policies"] = policies
        return [
            SimpleNamespace(
                tld="com",
                effective_source="czds_primary",
                czds_available=True,
                ct_enabled=False,
                bulk_status="n/a",
                fallback_reason=None,
                priority_group="priority",
            )
        ]

    monkeypatch.setattr(ingestion_router, "SessionLocal", fake_session_local)
    monkeypatch.setattr(ingestion_router, "get_target_tlds", lambda: ["com"])
    monkeypatch.setattr(ingestion_router.CzdsPolicyRepository, "list_all", fake_list_all)
    monkeypatch.setattr(ingestion_router, "resolve_tld_coverages", fake_resolve)
    app.dependency_overrides[get_current_admin] = _override_admin

    try:
        client = TestClient(app)
        response = client.get("/v1/ingestion/tld-coverage")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["tld"] == "com"
    assert payload[0]["last_ct_stream_seen_at"] is None
    assert payload[0]["last_crtsh_success_at"] is None
    assert seen["session_opened"] is True
    assert seen["session_closed"] is True
    assert set(seen["resolved_policies"]) == {"com"}
