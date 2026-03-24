"""Register all available tool services."""

from __future__ import annotations

from app.api.v1.routers.tools import register_tool
from app.services.use_cases.tools.dns_lookup import DnsLookupService
from app.services.use_cases.tools.whois_lookup import WhoisLookupService
from app.services.use_cases.tools.ssl_check import SslCheckService
from app.services.use_cases.tools.http_headers import HttpHeadersService
from app.services.use_cases.tools.screenshot_capture import ScreenshotCaptureService
from app.services.use_cases.tools.suspicious_page import SuspiciousPageService


def register_all_tools() -> None:
    """Instantiate and register every tool service."""
    register_tool(DnsLookupService())
    register_tool(WhoisLookupService())
    register_tool(SslCheckService())
    register_tool(HttpHeadersService())
    register_tool(ScreenshotCaptureService())
    register_tool(SuspiciousPageService())
