"""CZDS API client — authenticate and download zone files from ICANN."""

from __future__ import annotations

import hashlib
import logging
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_AUTH_URL = "https://account-api.icann.org/api/authenticate"
# ICANN JWTs expire at 24 h; refresh proactively before expiry
_TOKEN_MAX_AGE_SECONDS = 23 * 3600


class CZDSAuthRateLimitedError(Exception):
    """Raised when ICANN authentication throttles the worker."""


class CZDSTldAccessError(Exception):
    """Raised when a specific TLD cannot be downloaded from CZDS."""

    def __init__(self, tld: str, status_code: int, message: str) -> None:
        super().__init__(message)
        self.tld = tld
        self.status_code = status_code


class CZDSClient:
    """Handles authentication and streaming zone-file downloads from CZDS.

    Designed to be shared across multiple threads (parallel TLD workers).
    A single instance per sync cycle avoids repeated ICANN auth calls that
    trigger HTTP 429 rate limits.
    """

    def __init__(self) -> None:
        self.base_url = settings.CZDS_BASE_URL.rstrip("/")
        self._token: str | None = None
        self._token_obtained_at: datetime | None = None
        self._authorized_tlds: set[str] | None = None
        # Serialize authentication and TLD-list fetches across threads
        self._auth_lock = threading.Lock()

    # ── Authentication ──────────────────────────────────────
    def _is_token_stale(self) -> bool:
        if self._token is None or self._token_obtained_at is None:
            return True
        age = (datetime.now(timezone.utc) - self._token_obtained_at).total_seconds()
        return age >= _TOKEN_MAX_AGE_SECONDS

    def _authenticate(self) -> str:
        """Obtain a JWT from ICANN's account API. Caller must hold _auth_lock."""
        logger.info("Authenticating with CZDS…")
        resp = httpx.post(
            _AUTH_URL,
            json={
                "username": settings.CZDS_USERNAME,
                "password": settings.CZDS_PASSWORD,
            },
            timeout=30,
        )
        if resp.status_code == 429:
            raise CZDSAuthRateLimitedError(
                "ICANN authentication is rate-limiting this worker."
            )
        resp.raise_for_status()
        token = resp.json().get("accessToken") or resp.text
        self._token = token.strip()
        self._token_obtained_at = datetime.now(timezone.utc)
        # Invalidate cached TLD list — it may change after re-auth
        self._authorized_tlds = None
        logger.info("CZDS authentication successful.")
        return self._token

    def invalidate_token(self) -> None:
        """Force re-authentication on the next token access."""
        with self._auth_lock:
            self._token = None
            self._token_obtained_at = None
            self._authorized_tlds = None

    @property
    def token(self) -> str:
        if not self._is_token_stale():
            return self._token  # type: ignore[return-value]
        with self._auth_lock:
            # Double-check after acquiring lock (another thread may have just authed)
            if self._is_token_stale():
                self._authenticate()
        return self._token  # type: ignore[return-value]

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    # ── Zone download ───────────────────────────────────────
    def _do_download(self, tld: str, dest_dir: str | None) -> tuple[Path, str, int]:
        """Single download attempt — may raise httpx.HTTPStatusError on 401."""
        url = f"{self.base_url}/czds/downloads/{tld}.zone"
        logger.info("Downloading zone file for TLD=%s from %s", tld, url)

        dest = Path(dest_dir or tempfile.mkdtemp(prefix=f"czds_{tld}_"))
        local_path = dest / f"{tld}.zone.gz"

        sha = hashlib.sha256()
        size = 0

        with httpx.stream("GET", url, headers=self._headers(), timeout=600, follow_redirects=True) as r:
            if r.status_code in {403, 404}:
                raise CZDSTldAccessError(
                    tld,
                    r.status_code,
                    f"CZDS denied access to zone file for {tld} with status {r.status_code}.",
                )
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

    def download_zone(self, tld: str, dest_dir: str | None = None) -> tuple[Path, str, int]:
        """
        Stream-download a zone file for *tld*, retrying once on token expiry.

        Returns
        -------
        (local_path, sha256_hex, size_bytes)
        """
        try:
            return self._do_download(tld, dest_dir)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401:
                logger.warning(
                    "Token rejected (401) while downloading TLD=%s. Refreshing token and retrying.",
                    tld,
                )
                self.invalidate_token()
                return self._do_download(tld, dest_dir)
            raise

    # ── List authorised zones ───────────────────────────────
    def list_links(self) -> list[str]:
        """Return download-link URLs the current credential is authorised for."""
        url = f"{self.base_url}/czds/downloads/links"
        resp = httpx.get(url, headers=self._headers(), timeout=30)
        resp.raise_for_status()
        return resp.json()

    def list_authorized_tlds(self) -> set[str]:
        """Return the cached set of downloadable TLDs for the current credential."""
        if self._authorized_tlds is not None:
            return self._authorized_tlds

        with self._auth_lock:
            # Double-check after acquiring lock
            if self._authorized_tlds is not None:
                return self._authorized_tlds

            tlds: set[str] = set()
            for link in self.list_links():
                path = urlparse(link).path
                filename = Path(path).name
                if not filename.endswith(".zone"):
                    continue
                tlds.add(filename[:-5].lower())

            self._authorized_tlds = tlds
            logger.info("Loaded %d authorized CZDS zone links.", len(tlds))

        return self._authorized_tlds
