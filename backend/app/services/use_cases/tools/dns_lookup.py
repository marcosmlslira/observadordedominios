"""DNS Lookup tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.dns_resolver import resolve_domain
from app.services.use_cases.tools.base import BaseToolService


class DnsLookupService(BaseToolService):
    tool_type = "dns_lookup"
    cache_ttl_seconds = settings.TOOLS_CACHE_DNS_LOOKUP
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return resolve_domain(target)
