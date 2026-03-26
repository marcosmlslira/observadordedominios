from __future__ import annotations

import json
from types import SimpleNamespace

import httpx

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
