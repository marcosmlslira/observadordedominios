from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.schemas.tools import WebsiteCloneRequest
from app.services.use_cases.tools.screenshot_capture import ScreenshotCaptureService

pytest.importorskip("bs4")

from app.services.use_cases.tools.suspicious_page import SuspiciousPageService


def test_website_clone_request_supports_separate_reference() -> None:
    body = WebsiteCloneRequest(
        target="https://fake-login.example.com/path",
        reference_target="https://www.example.com/login",
    )

    assert body.build_execution_target() == "fake-login.example.com|example.com"


def test_website_clone_request_supports_legacy_pipe_payload() -> None:
    body = WebsiteCloneRequest(
        target="https://fake-login.example.com|https://www.example.com/login",
    )

    assert body.build_execution_target() == "fake-login.example.com|example.com"


def test_screenshot_service_builds_public_tool_url(monkeypatch, tmp_path: Path) -> None:
    screenshot_file = tmp_path / "capture.png"
    screenshot_file.write_bytes(b"fake-png")

    monkeypatch.setattr(
        "app.services.use_cases.tools.screenshot_capture.capture_screenshot",
        lambda target: {
            "screenshot_path": str(screenshot_file),
            "page_title": "Example",
            "final_url": f"https://{target}",
            "viewport_width": 1280,
            "viewport_height": 720,
        },
    )

    uploaded: dict[str, str] = {}

    class FakeClient:
        def upload_file(self, path, bucket, key, ExtraArgs=None):  # noqa: N803
            uploaded["bucket"] = bucket
            uploaded["key"] = key

    class FakeStorage:
        def __init__(self) -> None:
            self.bucket = "tool-bucket"
            self.client = FakeClient()

        def ensure_bucket(self) -> None:
            return None

    monkeypatch.setattr("app.infra.external.s3_storage.S3Storage", FakeStorage)

    result = ScreenshotCaptureService()._execute("example.com")

    assert uploaded["key"].startswith("tools/screenshots/example.com/")
    assert result["screenshot_url"].startswith("/v1/tools/screenshots/example.com/")


def test_suspicious_page_detects_parked_domain(monkeypatch) -> None:
    service = SuspiciousPageService()
    monkeypatch.setattr(
        service,
        "_fetch_page",
        lambda target: {
            "html": "<html><head><title>Buy this domain</title></head><body>This domain is for sale</body></html>",
            "final_url": "https://forsale.example.com",
            "status_code": 200,
            "server": "GoDaddy",
        },
    )

    result = service._execute("example.com")

    assert result["page_disposition"] == "parked"
    assert result["risk_level"] == "low"
    assert any(signal["category"] == "parked_domain" for signal in result["signals"])


def test_suspicious_page_detects_challenge_page(monkeypatch) -> None:
    service = SuspiciousPageService()
    monkeypatch.setattr(
        service,
        "_fetch_page",
        lambda target: {
            "html": "<html><head><title>DDoS-Guard</title></head><body>Access denied</body></html>",
            "final_url": "https://example.com",
            "status_code": 503,
            "server": "ddos-guard",
        },
    )

    result = service._execute("example.com")

    assert result["page_disposition"] == "challenge"
    assert result["risk_level"] in {"low", "medium"}
    categories = {signal["category"] for signal in result["signals"]}
    assert "protected_page" in categories
    assert "infrastructure_masking" in categories
