from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.v1.routers import czds_ingestion
from app.infra.db.session import get_db
from app.main import app
from app.repositories.ingestion_run_repository import IngestionRunRepository


class _DummyDb:
    def __init__(self) -> None:
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


def test_trigger_sync_recovers_stale_runs_before_queueing(monkeypatch) -> None:
    db = _DummyDb()
    run = SimpleNamespace(id=uuid4(), tld="org", status="running")
    observed: dict[str, object] = {}

    def override_get_db():
        yield db

    def fake_recover(self, source, tld, *, stale_after_minutes, exclude_run_id=None):
        observed["recover"] = {
            "source": source,
            "tld": tld,
            "stale_after_minutes": stale_after_minutes,
        }
        return [SimpleNamespace(id=uuid4())]

    def fake_has_running(self, source, tld, exclude_run_id=None):
        observed["has_running"] = {"source": source, "tld": tld}
        return False

    def fake_create_run(self, source, tld):
        observed["create_run"] = {"source": source, "tld": tld}
        return run

    class DummyThread:
        def __init__(self, *, target, args, daemon):
            observed["thread_args"] = {"args": args, "daemon": daemon}

        def start(self):
            observed["thread_started"] = True

    monkeypatch.setattr(IngestionRunRepository, "recover_stale_runs", fake_recover)
    monkeypatch.setattr(IngestionRunRepository, "has_running_run", fake_has_running)
    monkeypatch.setattr(IngestionRunRepository, "create_run", fake_create_run)
    monkeypatch.setattr(czds_ingestion.threading, "Thread", DummyThread)
    app.dependency_overrides[get_db] = override_get_db

    try:
        client = TestClient(app)
        response = client.post("/v1/czds/trigger-sync", json={"tld": "org", "force": True})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["run_id"] == str(run.id)
    assert observed["recover"]["tld"] == "org"
    assert observed["has_running"]["tld"] == "org"
    assert observed["create_run"]["tld"] == "org"
    assert observed["thread_started"] is True
    assert db.commits == 2
