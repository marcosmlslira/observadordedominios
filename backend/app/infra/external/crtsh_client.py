"""crt.sh HTTP client for batch Certificate Transparency queries.

Queries crt.sh for .br domain certificates. Used as daily complementary
source alongside CertStream real-time ingestion.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

CRTSH_BASE_URL = "https://crt.sh/"
DEFAULT_TIMEOUT = 120
MAX_RETRIES = 3
BACKOFF_SECONDS = [30, 60, 120]


class CrtShClient:
    """HTTP client for querying crt.sh certificate transparency data."""

    def __init__(self, timeout: int = DEFAULT_TIMEOUT) -> None:
        self._timeout = timeout

    def query_br_domains(
        self,
        subtld: str,
        *,
        min_not_before: datetime | None = None,
    ) -> list[str]:
        """Query crt.sh for domains under a specific .br sub-TLD.

        Args:
            subtld: The sub-TLD to query (e.g., "com.br", "net.br").
            min_not_before: If set, only return domains from certificates
                           issued after this datetime.

        Returns:
            List of raw domain names (may include wildcards, duplicates).
        """
        query = f"%.{subtld}"
        url = CRTSH_BASE_URL
        params = {
            "q": query,
            "output": "json",
        }

        data = self._fetch_with_retry(url, params)
        if data is None:
            return []

        domains: list[str] = []
        for entry in data:
            # Filter by not_before if provided
            if min_not_before:
                not_before_str = entry.get("not_before")
                if not_before_str:
                    try:
                        not_before = datetime.fromisoformat(not_before_str)
                        if not_before < min_not_before:
                            continue
                    except (ValueError, TypeError):
                        pass

            # Extract domains from name_value (may be newline-separated)
            name_value = entry.get("name_value", "")
            if name_value:
                for name in name_value.split("\n"):
                    name = name.strip()
                    if name:
                        domains.append(name)

        logger.info(
            "crt.sh query for %s: %d entries, %d domains extracted (min_not_before=%s)",
            subtld, len(data), len(domains), min_not_before,
        )
        return domains

    def _fetch_with_retry(
        self,
        url: str,
        params: dict,
    ) -> list[dict] | None:
        """Fetch JSON from crt.sh with retry and exponential backoff."""
        with httpx.Client(timeout=self._timeout) as client:
            for attempt in range(MAX_RETRIES):
                try:
                    response = client.get(url, params=params)
                    response.raise_for_status()
                    return response.json()
                except httpx.TimeoutException:
                    logger.warning(
                        "crt.sh timeout (attempt %d/%d): %s",
                        attempt + 1, MAX_RETRIES, params.get("q"),
                    )
                except httpx.HTTPStatusError as e:
                    logger.warning(
                        "crt.sh HTTP %d (attempt %d/%d): %s",
                        e.response.status_code, attempt + 1, MAX_RETRIES, params.get("q"),
                    )
                except Exception:
                    logger.exception(
                        "crt.sh error (attempt %d/%d): %s",
                        attempt + 1, MAX_RETRIES, params.get("q"),
                    )

                if attempt < MAX_RETRIES - 1:
                    backoff = BACKOFF_SECONDS[attempt]
                    logger.info("Retrying in %ds...", backoff)
                    time.sleep(backoff)

        logger.error("crt.sh query failed after %d retries: %s", MAX_RETRIES, params.get("q"))
        return None
