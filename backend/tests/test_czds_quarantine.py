from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault("apscheduler", SimpleNamespace())
sys.modules.setdefault("apscheduler.schedulers", SimpleNamespace())
sys.modules.setdefault(
    "apscheduler.schedulers.blocking",
    SimpleNamespace(BlockingScheduler=object),
)
sys.modules.setdefault("apscheduler.triggers", SimpleNamespace())
sys.modules.setdefault(
    "apscheduler.triggers.cron",
    SimpleNamespace(CronTrigger=object),
)

from app.core.config import settings
from app.infra.external.czds_client import CZDSAuthRateLimitedError, CZDSTldAccessError
from app.services.use_cases import sync_czds_tld as sync_module
from app.worker import czds_ingestor


class _DummyScalarResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar(self):
        return self._value


class _DummyDb:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def execute(self, *_args, **_kwargs):
        return _DummyScalarResult(True)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def flush(self) -> None:
        return None

    def close(self) -> None:
        return None


def _make_dummy_run():
    return SimpleNamespace(
        id=uuid4(),
        artifact_id=None,
        finished_at=None,
        status="running",
        error_message=None,
    )


def test_run_sync_cycle_reuses_shared_client_and_backs_off_on_auth_rate_limit(monkeypatch) -> None:
    seen_clients = []
    waits: list[int] = []

    monkeypatch.setattr(czds_ingestor, "SessionLocal", _DummyDb)

    def fake_sync(db, tld, *, czds_client, **_kwargs):
        seen_clients.append((tld, id(czds_client)))
        raise CZDSAuthRateLimitedError("throttled")

    monkeypatch.setattr(czds_ingestor, "sync_czds_tld", fake_sync)
    monkeypatch.setattr(czds_ingestor, "_wait_or_stop", lambda seconds: waits.append(seconds) or False)

    czds_ingestor.run_sync_cycle(["com", "net"])

    assert seen_clients == [("com", seen_clients[0][1])]
    assert waits == [settings.CZDS_AUTH_RATE_LIMIT_BACKOFF_SECONDS]


def test_sync_czds_tld_quarantines_missing_tld_before_download(monkeypatch) -> None:
    db = _DummyDb()
    run = _make_dummy_run()
    observed: dict[str, object] = {}

    monkeypatch.setattr(sync_module, "ensure_partition", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sync_module, "apply_zone_delta", lambda *_args, **_kwargs: {})

    class DummyRunRepo:
        def __init__(self, _db) -> None:
            pass

        def recover_stale_runs(self, *_args, **_kwargs):
            return []

        def has_running_run(self, *_args, **_kwargs):
            return False

        def get_checkpoint(self, *_args, **_kwargs):
            return None

        def create_run(self, *_args, **_kwargs):
            return run

        def touch_run(self, *_args, **_kwargs):
            return run

        def finish_run(self, run_obj, *, status, error_message=None, **_kwargs):
            observed["finish"] = {"status": status, "error_message": error_message}
            run_obj.status = status
            run_obj.error_message = error_message
            return run_obj

    class DummyPolicyRepo:
        def __init__(self, _db) -> None:
            pass

        def ensure(self, tld):
            return SimpleNamespace(tld=tld, suspended_until=None)

        def record_failure(self, tld, *, status_code, message, suspend_hours=None):
            observed["failure"] = {
                "tld": tld,
                "status_code": status_code,
                "message": message,
                "suspend_hours": suspend_hours,
            }

        def record_success(self, *_args, **_kwargs):
            raise AssertionError("record_success should not be called")

    class DummyClient:
        def list_authorized_tlds(self):
            return {"com", "org"}

        def download_zone(self, *_args, **_kwargs):
            raise AssertionError("download_zone should not be called")

    monkeypatch.setattr(sync_module, "IngestionRunRepository", DummyRunRepo)
    monkeypatch.setattr(sync_module, "CzdsPolicyRepository", DummyPolicyRepo)

    with pytest.raises(CZDSTldAccessError):
        sync_module.sync_czds_tld(db, "pay", czds_client=DummyClient(), s3_storage=SimpleNamespace())

    assert observed["failure"]["status_code"] == 404
    assert observed["failure"]["suspend_hours"] == settings.CZDS_TLD_NOT_FOUND_SUSPEND_HOURS
    assert observed["finish"]["status"] == "failed"


def test_sync_czds_tld_quarantines_forbidden_tld_after_download_denied(monkeypatch) -> None:
    db = _DummyDb()
    run = _make_dummy_run()
    observed: dict[str, object] = {}

    monkeypatch.setattr(sync_module, "ensure_partition", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(sync_module, "apply_zone_delta", lambda *_args, **_kwargs: {})

    class DummyRunRepo:
        def __init__(self, _db) -> None:
            pass

        def recover_stale_runs(self, *_args, **_kwargs):
            return []

        def has_running_run(self, *_args, **_kwargs):
            return False

        def get_checkpoint(self, *_args, **_kwargs):
            return None

        def create_run(self, *_args, **_kwargs):
            return run

        def touch_run(self, *_args, **_kwargs):
            return run

        def finish_run(self, run_obj, *, status, error_message=None, **_kwargs):
            observed["finish"] = {"status": status, "error_message": error_message}
            run_obj.status = status
            run_obj.error_message = error_message
            return run_obj

    class DummyPolicyRepo:
        def __init__(self, _db) -> None:
            pass

        def ensure(self, tld):
            return SimpleNamespace(tld=tld, suspended_until=None)

        def record_failure(self, tld, *, status_code, message, suspend_hours=None):
            observed["failure"] = {
                "tld": tld,
                "status_code": status_code,
                "message": message,
                "suspend_hours": suspend_hours,
            }

        def record_success(self, *_args, **_kwargs):
            raise AssertionError("record_success should not be called")

    class DummyClient:
        def list_authorized_tlds(self):
            return {"pay"}

        def download_zone(self, *_args, **_kwargs):
            raise CZDSTldAccessError("pay", 403, "forbidden")

    monkeypatch.setattr(sync_module, "IngestionRunRepository", DummyRunRepo)
    monkeypatch.setattr(sync_module, "CzdsPolicyRepository", DummyPolicyRepo)

    with pytest.raises(CZDSTldAccessError):
        sync_module.sync_czds_tld(db, "pay", czds_client=DummyClient(), s3_storage=SimpleNamespace())

    assert observed["failure"]["status_code"] == 403
    assert observed["failure"]["suspend_hours"] == settings.CZDS_TLD_FORBIDDEN_SUSPEND_HOURS
    assert observed["finish"]["status"] == "failed"
