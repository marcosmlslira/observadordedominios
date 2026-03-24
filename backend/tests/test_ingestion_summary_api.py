from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.dependencies import get_current_admin
from app.infra.db.session import get_db
from app.main import app
from app.repositories.ingestion_run_repository import IngestionRunRepository


def _override_get_db():
    yield object()


def _override_admin():
    return "admin@observador.com"


def test_ingestion_summary_includes_crtsh_and_bulk_hints(monkeypatch) -> None:
    now = datetime.now(timezone.utc)

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

    assert payload["crtsh-bulk"]["mode"] == "Manual backfill"
    assert payload["crtsh-bulk"]["status_hint"] == "Manual historical backfill. No automatic scheduler."

