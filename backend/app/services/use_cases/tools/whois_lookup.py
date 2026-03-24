"""WHOIS Lookup tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.whois_client import lookup_whois
from app.services.use_cases.tools.base import BaseToolService


class WhoisLookupService(BaseToolService):
    tool_type = "whois"
    cache_ttl_seconds = settings.TOOLS_CACHE_WHOIS
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return lookup_whois(target)
