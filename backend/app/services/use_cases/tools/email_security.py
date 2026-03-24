"""Email Security tool service (SPF, DMARC, DKIM)."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.email_security_client import check_email_security
from app.services.use_cases.tools.base import BaseToolService


class EmailSecurityService(BaseToolService):
    tool_type = "email_security"
    cache_ttl_seconds = settings.TOOLS_CACHE_EMAIL_SECURITY
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return check_email_security(target)
