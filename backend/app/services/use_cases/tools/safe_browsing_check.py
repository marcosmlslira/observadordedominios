"""Safe Browsing Check tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.safe_browsing_client import check_safe_browsing
from app.services.use_cases.tools.base import BaseToolService


class SafeBrowsingCheckService(BaseToolService):
    tool_type = "safe_browsing_check"
    cache_ttl_seconds = settings.TOOLS_CACHE_SAFE_BROWSING_CHECK
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return check_safe_browsing(target)
