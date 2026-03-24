"""Website screenshot capture using Playwright."""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 720
GOTO_TIMEOUT_MS = 30000
SCREENSHOT_TIMEOUT_MS = 10000


def capture_screenshot(
    domain: str,
    *,
    viewport_width: int = VIEWPORT_WIDTH,
    viewport_height: int = VIEWPORT_HEIGHT,
) -> dict:
    """Navigate to domain and take a full-page screenshot.

    Returns dict with screenshot bytes path, page title, and final URL.
    """
    from playwright.sync_api import sync_playwright

    url = f"https://{domain}"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            page = browser.new_page(
                viewport={"width": viewport_width, "height": viewport_height},
                ignore_https_errors=True,
            )
            try:
                page.goto(url, wait_until="networkidle", timeout=GOTO_TIMEOUT_MS)
            except Exception:
                # Fallback to HTTP
                url = f"http://{domain}"
                page.goto(url, wait_until="networkidle", timeout=GOTO_TIMEOUT_MS)

            page_title = page.title()
            final_url = page.url

            # Save screenshot to temp file
            tmp_path = Path(tempfile.mkdtemp()) / f"{uuid.uuid4()}.png"
            page.screenshot(path=str(tmp_path), full_page=False, timeout=SCREENSHOT_TIMEOUT_MS)

            return {
                "screenshot_path": str(tmp_path),
                "page_title": page_title,
                "final_url": final_url,
                "viewport_width": viewport_width,
                "viewport_height": viewport_height,
            }
        finally:
            browser.close()
