"""Subdomain Takeover Check tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.subdomain_takeover_client import check_takeover
from app.services.use_cases.tools.base import BaseToolService


class SubdomainTakeoverCheckService(BaseToolService):
    tool_type = "subdomain_takeover_check"
    cache_ttl_seconds = settings.TOOLS_CACHE_SUBDOMAIN_TAKEOVER
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return check_takeover(target)
