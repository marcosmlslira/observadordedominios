"""SSL Check tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.ssl_checker import check_ssl
from app.services.use_cases.tools.base import BaseToolService


class SslCheckService(BaseToolService):
    tool_type = "ssl_check"
    cache_ttl_seconds = settings.TOOLS_CACHE_SSL_CHECK
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return check_ssl(target)
