"""CZDS API client — authenticate and download zone files from ICANN."""

from __future__ import annotations

import hashlib
import logging
import tempfile
from pathlib import Path

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_AUTH_URL = "https://account-api.icann.org/api/authenticate"


class CZDSClient:
    """Handles authentication and streaming zone-file downloads from CZDS."""

    def __init__(self) -> None:
        self.base_url = settings.CZDS_BASE_URL.rstrip("/")
        self._token: str | None = None

    # ── Authentication ──────────────────────────────────────
    def _authenticate(self) -> str:
        """Obtain a JWT from ICANN's account API."""
        logger.info("Authenticating with CZDS…")
        resp = httpx.post(
            _AUTH_URL,
            json={
                "username": settings.CZDS_USERNAME,
                "password": settings.CZDS_PASSWORD,
            },
            timeout=30,
        )
        resp.raise_for_status()
        token = resp.json().get("accessToken") or resp.text
        self._token = token.strip()
        logger.info("CZDS authentication successful.")
        return self._token

    @property
    def token(self) -> str:
        if self._token is None:
            self._authenticate()
        return self._token  # type: ignore[return-value]

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    # ── Zone download ───────────────────────────────────────
    def download_zone(self, tld: str, dest_dir: str | None = None) -> tuple[Path, str, int]:
        """
        Stream-download a zone file for *tld*.

        Returns
        -------
        (local_path, sha256_hex, size_bytes)
        """
        url = f"{self.base_url}/czds/downloads/{tld}.zone"
        logger.info("Downloading zone file for TLD=%s from %s", tld, url)

        dest = Path(dest_dir or tempfile.mkdtemp(prefix=f"czds_{tld}_"))
        local_path = dest / f"{tld}.zone.gz"

        sha = hashlib.sha256()
        size = 0

        with httpx.stream("GET", url, headers=self._headers(), timeout=600, follow_redirects=True) as r:
            r.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=8 * 1024 * 1024):
                    f.write(chunk)
                    sha.update(chunk)
                    size += len(chunk)

        sha256_hex = sha.hexdigest()
        logger.info(
            "Zone file downloaded: tld=%s  size=%d bytes  sha256=%s",
            tld, size, sha256_hex,
        )
        return local_path, sha256_hex, size

    # ── List authorised zones ───────────────────────────────
    def list_links(self) -> list[str]:
        """Return download-link URLs the current credential is authorised for."""
        url = f"{self.base_url}/czds/downloads/links"
        resp = httpx.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()
