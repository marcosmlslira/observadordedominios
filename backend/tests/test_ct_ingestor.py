from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

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

from app.worker import ct_ingestor


class _DummyDb:
    def __init__(self) -> None:
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1

    def close(self) -> None:
        self.closed += 1


def test_recover_orphaned_certstream_runs_marks_old_run_failed(monkeypatch) -> None:
    db = _DummyDb()
    recovered_run = SimpleNamespace(id="run-1")
    captured: dict[str, object] = {}

    monkeypatch.setattr(ct_ingestor, "SessionLocal", lambda: db)

    class DummyRepo:
        def __init__(self, session) -> None:
            captured["session"] = session

        def mark_running_source_runs_failed(self, source, *, error_message):
            captured["args"] = {
                "source": source,
                "error_message": error_message,
            }
            return [recovered_run]

    monkeypatch.setattr(ct_ingestor, "IngestionRunRepository", DummyRepo)

    recovered = ct_ingestor._recover_orphaned_certstream_runs()

    assert recovered == 1
    assert captured["args"]["source"] == "certstream"
    assert "did not finalize cleanly" in captured["args"]["error_message"]
    assert db.committed == 1
    assert db.closed == 1
