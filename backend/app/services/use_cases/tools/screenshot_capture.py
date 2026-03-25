"""Screenshot Capture tool service."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from app.core.config import settings
from app.infra.external.screenshot_client import capture_screenshot
from app.services.use_cases.tools.base import BaseToolService

logger = logging.getLogger(__name__)


class ScreenshotCaptureService(BaseToolService):
    tool_type = "screenshot"
    cache_ttl_seconds = settings.TOOLS_CACHE_SCREENSHOT
    timeout_seconds = settings.TOOLS_SCREENSHOT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        result = capture_screenshot(target)
        screenshot_path = result.pop("screenshot_path", None)

        s3_key = None
        screenshot_url = None

        if screenshot_path and os.path.exists(screenshot_path):
            try:
                from app.infra.external.s3_storage import S3Storage

                s3 = S3Storage()
                s3.bucket = settings.TOOLS_S3_BUCKET
                s3.ensure_bucket()

                object_path = f"{target}/{Path(screenshot_path).name}"
                s3_key = f"tools/screenshots/{object_path}"
                s3.client.upload_file(
                    screenshot_path,
                    s3.bucket,
                    s3_key,
                    ExtraArgs={"ContentType": "image/png"},
                )
                screenshot_url = f"/v1/tools/screenshots/{object_path}"
                logger.info("Screenshot uploaded: %s", s3_key)
            except Exception as exc:
                logger.warning("Failed to upload screenshot to S3: %s", exc)
            finally:
                try:
                    os.unlink(screenshot_path)
                except OSError:
                    pass

        return {
            "screenshot_url": screenshot_url,
            "s3_key": s3_key,
            "page_title": result.get("page_title"),
            "final_url": result.get("final_url"),
            "viewport_width": result.get("viewport_width", 1280),
            "viewport_height": result.get("viewport_height", 720),
        }
