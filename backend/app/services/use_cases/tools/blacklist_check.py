"""Blacklist Check tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.dnsbl_client import check_blacklists
from app.services.use_cases.tools.base import BaseToolService


class BlacklistCheckService(BaseToolService):
    tool_type = "blacklist_check"
    cache_ttl_seconds = settings.TOOLS_CACHE_BLACKLIST_CHECK
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return check_blacklists(target)
