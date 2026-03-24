"""IP Geolocation tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.geolocation_client import geolocate
from app.services.use_cases.tools.base import BaseToolService


class IpGeolocationService(BaseToolService):
    tool_type = "ip_geolocation"
    cache_ttl_seconds = settings.TOOLS_CACHE_IP_GEOLOCATION
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return geolocate(target)
