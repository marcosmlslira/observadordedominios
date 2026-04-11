"""PhishTank Check tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.phishtank_client import check_phishtank
from app.services.use_cases.tools.base import BaseToolService


class PhishTankCheckService(BaseToolService):
    tool_type = "phishtank_check"
    cache_ttl_seconds = settings.TOOLS_CACHE_PHISHTANK_CHECK
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return check_phishtank(target)
