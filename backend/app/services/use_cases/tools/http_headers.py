"""HTTP Headers Analysis tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.http_analyzer import analyze_http_headers
from app.services.use_cases.tools.base import BaseToolService


class HttpHeadersService(BaseToolService):
    tool_type = "http_headers"
    cache_ttl_seconds = settings.TOOLS_CACHE_HTTP_HEADERS
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return analyze_http_headers(target)
