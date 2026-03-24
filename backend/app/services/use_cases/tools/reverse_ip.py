"""Reverse IP Lookup tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.passive_dns_client import reverse_ip_lookup
from app.services.use_cases.tools.base import BaseToolService


class ReverseIpService(BaseToolService):
    tool_type = "reverse_ip"
    cache_ttl_seconds = settings.TOOLS_CACHE_REVERSE_IP
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return reverse_ip_lookup(target)
