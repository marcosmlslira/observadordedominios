"""URLhaus Check tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.urlhaus_client import check_urlhaus
from app.services.use_cases.tools.base import BaseToolService


class UrlhausCheckService(BaseToolService):
    tool_type = "urlhaus_check"
    cache_ttl_seconds = settings.TOOLS_CACHE_URLHAUS_CHECK
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return check_urlhaus(target)
