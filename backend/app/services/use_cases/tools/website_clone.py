"""Website Clone Detector tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.clone_detector_client import compare_websites
from app.services.use_cases.tools.base import BaseToolService


class WebsiteCloneService(BaseToolService):
    tool_type = "website_clone"
    cache_ttl_seconds = settings.TOOLS_CACHE_WEBSITE_CLONE
    timeout_seconds = 90  # Screenshots + fetching two pages takes longer

    def _execute(self, target: str) -> dict:
        # target format: "target.com|reference.com"
        if "|" in target:
            t, ref = target.split("|", 1)
        else:
            raise ValueError("Website Clone requires a target and reference domain")
        return compare_websites(t.strip(), ref.strip())
