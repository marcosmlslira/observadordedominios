from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.v1.routers import ingestion_config
from app.core.dependencies import get_current_admin
from app.infra.db.session import get_db
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.services.use_cases.sync_openintel_tld import (
    SnapshotAlreadyIngestedError,
    SnapshotNotFoundError,
)


class _DummyDb:
    def __init__(self) -> None:
        self.commits = 0
        self.closed = False

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        self.closed = True


def _override_admin():
    return "admin@observador.com"


def test_openintel_manual_trigger_marks_skip_as_success(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(ingestion_config.router)

    req_db = _DummyDb()
    bg_db = _DummyDb()
    run = SimpleNamespace(id=uuid4(), tld="fr", status="running")
    observed: dict[str, object] = {}

    def override_get_db():
        yield req_db

    def fake_recover(self, source, tld, *, stale_after_minutes, exclude_run_id=None):
        return []

    def fake_has_running(self, source, tld, exclude_run_id=None):
        return False

    def fake_create_run(self, source, tld):
        return run

    def fake_get_run(self, run_id):
        return run

    def fake_finish_run(self, obj, *, status, metrics=None, error_message=None, artifact_id=None):
        observed["finish_status"] = status
        observed["finish_error"] = error_message
        obj.status = status
        return obj

    class DummyThread:
        def __init__(self, *args, **kwargs):
            self._target = kwargs["target"]
            observed["thread_daemon"] = kwargs.get("daemon")

        def start(self):
            self._target()
            observed["thread_started"] = True

    monkeypatch.setattr(IngestionRunRepository, "recover_stale_runs", fake_recover)
    monkeypatch.setattr(IngestionRunRepository, "has_running_run", fake_has_running)
    monkeypatch.setattr(IngestionRunRepository, "create_run", fake_create_run)
    monkeypatch.setattr(IngestionRunRepository, "get_run", fake_get_run)
    monkeypatch.setattr(IngestionRunRepository, "finish_run", fake_finish_run)
    monkeypatch.setattr(ingestion_config, "SessionLocal", lambda: bg_db)
    monkeypatch.setattr(
        ingestion_config,
        "sync_openintel_tld",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            SnapshotAlreadyIngestedError("already ingested")
        ),
    )
    monkeypatch.setattr(ingestion_config, "threading", SimpleNamespace(Thread=DummyThread))
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = _override_admin

    try:
        client = TestClient(app)
        response = client.post("/v1/ingestion/trigger/openintel/fr", json={"force": False})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert observed["thread_started"] is True
    assert observed["finish_status"] == "success"
    assert "already ingested" in str(observed["finish_error"])
    assert req_db.commits == 1
    assert bg_db.commits == 1
    assert bg_db.closed is True


def test_openintel_manual_trigger_marks_no_snapshot_as_success(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(ingestion_config.router)

    req_db = _DummyDb()
    bg_db = _DummyDb()
    run = SimpleNamespace(id=uuid4(), tld="fr", status="running")
    observed: dict[str, object] = {}

    def override_get_db():
        yield req_db

    def fake_recover(self, source, tld, *, stale_after_minutes, exclude_run_id=None):
        return []

    def fake_has_running(self, source, tld, exclude_run_id=None):
        return False

    def fake_create_run(self, source, tld):
        return run

    def fake_get_run(self, run_id):
        return run

    def fake_finish_run(self, obj, *, status, metrics=None, error_message=None, artifact_id=None):
        observed["finish_status"] = status
        observed["finish_error"] = error_message
        obj.status = status
        return obj

    class DummyThread:
        def __init__(self, *args, **kwargs):
            self._target = kwargs["target"]

        def start(self):
            self._target()

    monkeypatch.setattr(IngestionRunRepository, "recover_stale_runs", fake_recover)
    monkeypatch.setattr(IngestionRunRepository, "has_running_run", fake_has_running)
    monkeypatch.setattr(IngestionRunRepository, "create_run", fake_create_run)
    monkeypatch.setattr(IngestionRunRepository, "get_run", fake_get_run)
    monkeypatch.setattr(IngestionRunRepository, "finish_run", fake_finish_run)
    monkeypatch.setattr(ingestion_config, "SessionLocal", lambda: bg_db)
    monkeypatch.setattr(
        ingestion_config,
        "sync_openintel_tld",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            SnapshotNotFoundError("no snapshot")
        ),
    )
    monkeypatch.setattr(ingestion_config, "threading", SimpleNamespace(Thread=DummyThread))
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_admin] = _override_admin

    try:
        client = TestClient(app)
        response = client.post("/v1/ingestion/trigger/openintel/fr", json={"force": False})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert observed["finish_status"] == "success"
    assert "no snapshot" in str(observed["finish_error"])
    assert req_db.commits == 1
    assert bg_db.commits == 1
