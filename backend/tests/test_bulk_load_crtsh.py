from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.modules.setdefault(
    "tldextract",
    SimpleNamespace(
        TLDExtract=lambda cache_dir=None: (lambda value: SimpleNamespace(
            suffix="io",
            domain="example",
            registered_domain="example.io",
        ))
    ),
)

from app.services.use_cases import bulk_load_crtsh


class _FakeResponse:
    def __init__(self, *, headers: dict[str, str], content: bytes, json_payload=None, status_code: int = 200) -> None:
        self.headers = headers
        self.content = content
        self._json_payload = json_payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("GET", "https://crt.sh/")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("boom", request=request, response=response)

    def json(self):
        if isinstance(self._json_payload, Exception):
            raise self._json_payload
        return self._json_payload


class _FakeClient:
    response: _FakeResponse

    def __init__(self, *args, **kwargs) -> None:
        del args, kwargs

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb

    def get(self, url, params=None):
        del url, params
        return self.response


def test_fetch_chunk_payload_returns_success_for_json(monkeypatch) -> None:
    _FakeClient.response = _FakeResponse(
        headers={"content-type": "application/json"},
        content=b'[{"name_value":"one.example.com\\ntwo.example.com"}]',
        json_payload=[{"name_value": "one.example.com\ntwo.example.com"}],
    )
    monkeypatch.setattr(bulk_load_crtsh.httpx, "Client", _FakeClient)

    result = bulk_load_crtsh._fetch_chunk_payload("%.com.br")

    assert result.kind == "success"
    assert result.raw_domains == ["one.example.com", "two.example.com"]


def test_fetch_chunk_payload_splits_on_html_response(monkeypatch) -> None:
    _FakeClient.response = _FakeResponse(
        headers={"content-type": "text/html"},
        content=b"<html><body>rate limited</body></html>",
        json_payload=json.JSONDecodeError("x", "{}", 0),
    )
    monkeypatch.setattr(bulk_load_crtsh.httpx, "Client", _FakeClient)

    result = bulk_load_crtsh._fetch_chunk_payload("u%.com.br")

    assert result.kind == "split_required"
    assert result.error_type == "html_response"


def test_select_chunks_respects_priority_parallelism() -> None:
    job = SimpleNamespace(priority_tlds=["br", "io"])
    chunks = [
        SimpleNamespace(id="1", target_tld="br"),
        SimpleNamespace(id="2", target_tld="br"),
        SimpleNamespace(id="3", target_tld="br"),
        SimpleNamespace(id="4", target_tld="de"),
    ]

    selected = bulk_load_crtsh._select_chunks_for_execution(job, chunks)

    assert [chunk.id for chunk in selected] == ["1", "2"]


def test_execute_chunks_uses_plain_tasks(monkeypatch) -> None:
    task_id = uuid.uuid4()

    def fake_fetch(query_pattern: str):
        return bulk_load_crtsh.ChunkFetchResult(kind="success", raw_domains=[query_pattern])

    monkeypatch.setattr(bulk_load_crtsh, "_fetch_chunk_payload", fake_fetch)

    results = bulk_load_crtsh._execute_chunks(
        [
            bulk_load_crtsh.ExecutableChunk(
                id=task_id,
                target_tld="io",
                chunk_key="io:root",
                query_pattern="%.io",
                depth=0,
            )
        ]
    )

    assert results[task_id].kind == "success"
    assert results[task_id].raw_domains == ["%.io"]


def test_resume_bulk_job_recovers_running_chunks(monkeypatch) -> None:
    now = bulk_load_crtsh.datetime.now(bulk_load_crtsh.timezone.utc)
    job_id = uuid.uuid4()
    job = SimpleNamespace(
        id=job_id,
        status="running",
        finished_at=now,
        last_error="boom",
        updated_at=now,
    )
    running_chunk = SimpleNamespace(
        status="running",
        next_retry_at=None,
        finished_at=now,
        last_error_type=None,
        last_error_excerpt=None,
        updated_at=now,
    )

    class FakeDB:
        def commit(self):
            return None

        def refresh(self, obj):
            return None

        def expunge(self, obj):
            return None

        def close(self):
            return None

    class FakeRepo:
        def __init__(self, db):
            self.db = db

        def get_active_job(self):
            return job

        def get_job(self, requested_job_id):
            assert requested_job_id == job_id
            return job

        def list_chunks(self, requested_job_id, *, limit=100000, status=None, target_tld=None):
            del limit, target_tld
            assert requested_job_id == job_id
            if status == "running":
                return [running_chunk]
            return []

        def refresh_job_metrics(self, stored_job):
            return stored_job

    monkeypatch.setattr(bulk_load_crtsh, "SessionLocal", lambda: FakeDB())
    monkeypatch.setattr(bulk_load_crtsh, "CtBulkRepository", FakeRepo)

    resumed = bulk_load_crtsh.resume_bulk_job(job_id)

    assert resumed is job
    assert job.status == "pending"
    assert job.finished_at is None
    assert job.last_error is None
    assert running_chunk.status == "retry"
    assert running_chunk.last_error_type == "manual_resume"
