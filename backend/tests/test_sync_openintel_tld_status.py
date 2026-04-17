from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.use_cases import sync_openintel_tld as sync_module


class _FakeDb:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def execute(self, *args, **kwargs):
        query = str(args[0]) if args else ""
        if "pg_try_advisory_lock" in query:
            return SimpleNamespace(scalar=lambda: True)
        return SimpleNamespace(scalar=lambda: None)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _FakeRunRepo:
    def __init__(self, db, *, already_ingested: bool = False) -> None:
        self.db = db
        self.already_ingested = already_ingested
        self.run = None
        self.finished = []
        self.checkpointed = False

    def has_running_run(self, source, tld, exclude_run_id=None):
        return False

    def recover_stale_runs(self, source, tld, *, stale_after_minutes, exclude_run_id=None):
        return []

    def get_checkpoint(self, source, tld):
        return None

    def has_successful_run_after(self, source, tld, after):
        return self.already_ingested

    def get_run(self, run_id):
        return None

    def create_run(self, source, tld):
        self.run = SimpleNamespace(id=uuid4(), source=source, tld=tld, status="running")
        return self.run

    def finish_run(self, run, *, status, metrics=None, error_message=None, artifact_id=None):
        self.finished.append({"status": status, "error_message": error_message, "metrics": metrics})
        run.status = status
        run.finished_at = datetime.now(timezone.utc)
        return run

    def upsert_checkpoint(self, source, tld, run):
        self.checkpointed = True


class _FakeStatusRepo:
    def __init__(self, db) -> None:
        self.db = db
        self.calls = []

    def upsert_status(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(**kwargs)


def _setup_common(monkeypatch, *, discover_result=None, discover_error: Exception | None = None, already_ingested=False, apply_error: Exception | None = None):
    db = _FakeDb()
    status_repo = _FakeStatusRepo(db)
    run_repo = _FakeRunRepo(db, already_ingested=already_ingested)

    class _Client:
        def discover_snapshot(self, tld):
            if discover_error is not None:
                raise discover_error
            return discover_result

        def stream_apex_domains(self, s3_keys, tld):
            yield f"example.{tld}"

    monkeypatch.setattr(sync_module, "OpenIntelClient", _Client)
    monkeypatch.setattr(sync_module, "OpenIntelCctldClient", _Client)
    monkeypatch.setattr(sync_module, "IngestionRunRepository", lambda _db: run_repo)
    monkeypatch.setattr(sync_module, "OpenintelTldStatusRepository", lambda _db: status_repo)
    monkeypatch.setattr(sync_module, "ensure_partition", lambda _db, _tld: None)
    monkeypatch.setattr(sync_module.settings, "OPENINTEL_RUNNING_STALE_MINUTES", 120)
    monkeypatch.setattr(sync_module.settings, "OPENINTEL_FORCE_COOLDOWN_HOURS", 24)
    monkeypatch.setattr(sync_module.settings, "OPENINTEL_MAX_LOOKBACK_DAYS", 10)

    if apply_error is None:
        monkeypatch.setattr(
            sync_module,
            "apply_domain_names_delta",
            lambda *_args, **_kwargs: {"seen": 1, "inserted": 1, "reactivated": 0, "deleted": 0},
        )
    else:
        def _raise_apply(*_args, **_kwargs):
            raise apply_error
        monkeypatch.setattr(sync_module, "apply_domain_names_delta", _raise_apply)

    return db, run_repo, status_repo


def test_sync_openintel_marks_no_snapshot_available(monkeypatch):
    db, _run_repo, status_repo = _setup_common(monkeypatch, discover_result=None)

    with pytest.raises(sync_module.SnapshotNotFoundError):
        sync_module.sync_openintel_tld(db, "fr")

    assert status_repo.calls[-1]["last_probe_outcome"] == "no_snapshot_available"
    assert status_repo.calls[-1]["last_available_snapshot_date"] is None


def test_sync_openintel_marks_already_ingested(monkeypatch):
    snapshot_date = date(2026, 4, 13)
    db, _run_repo, status_repo = _setup_common(
        monkeypatch,
        discover_result=(["s3://fake"], snapshot_date),
        already_ingested=True,
    )

    with pytest.raises(sync_module.SnapshotAlreadyIngestedError):
        sync_module.sync_openintel_tld(db, "fr")

    assert status_repo.calls[-1]["last_probe_outcome"] == "already_ingested"
    assert status_repo.calls[-1]["last_available_snapshot_date"] == snapshot_date


def test_sync_openintel_marks_ingested_new_snapshot(monkeypatch):
    snapshot_date = date(2026, 4, 13)
    db, run_repo, status_repo = _setup_common(
        monkeypatch,
        discover_result=(["s3://fake"], snapshot_date),
    )

    run_id = sync_module.sync_openintel_tld(db, "fr")

    assert run_id == run_repo.run.id
    assert run_repo.finished[-1]["status"] == "success"
    assert run_repo.checkpointed is True
    assert status_repo.calls[-1]["last_probe_outcome"] == "ingested_new_snapshot"
    assert status_repo.calls[-1]["last_ingested_snapshot_date"] == snapshot_date


def test_sync_openintel_marks_verification_failed_on_discover_error(monkeypatch):
    db, _run_repo, status_repo = _setup_common(
        monkeypatch,
        discover_error=RuntimeError("provider down"),
    )

    with pytest.raises(RuntimeError):
        sync_module.sync_openintel_tld(db, "fr")

    assert status_repo.calls[-1]["last_probe_outcome"] == "verification_failed"
    assert "provider down" in status_repo.calls[-1]["last_error_message"]


def test_sync_openintel_marks_pending_or_failed_on_ingest_error(monkeypatch):
    snapshot_date = date(2026, 4, 13)
    db, run_repo, status_repo = _setup_common(
        monkeypatch,
        discover_result=(["s3://fake"], snapshot_date),
        apply_error=RuntimeError("db write failed"),
    )

    with pytest.raises(RuntimeError):
        sync_module.sync_openintel_tld(db, "fr")

    assert run_repo.finished[-1]["status"] == "failed"
    assert status_repo.calls[-1]["last_probe_outcome"] == "new_snapshot_pending_or_failed"
    assert status_repo.calls[-1]["last_available_snapshot_date"] == snapshot_date
    assert "db write failed" in status_repo.calls[-1]["last_error_message"]
