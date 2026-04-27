"""CZDS client — authentication, TLD resolution, zone file download and parsing.

Zone files are gzip-compressed text files with one DNS record per line.
We extract the owner field (left-most token) and normalise it.
Encoding: latin-1 (preserves all byte values 0-255 without loss).
"""

from __future__ import annotations

import gzip
import logging
import random
import time
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import polars as pl
import requests

from ingestion.config.settings import Settings

log = logging.getLogger(__name__)


CZDS_BASE_URL = "https://czds-api.icann.org"
CZDS_AUTH_URL = "https://account-api.icann.org/api/authenticate"


def _normalise(raw_bytes: bytes) -> str:
    return raw_bytes.decode("latin-1").lower().strip()


class CZDSClient:
    def __init__(self, cfg: Settings) -> None:
        self._username = cfg.czds_username
        self._password = cfg.czds_password
        self._base_url = CZDS_BASE_URL
        self._auth_url = CZDS_AUTH_URL
        self._max_tlds = cfg.czds_max_tlds

    # ── Auth ──────────────────────────────────────────────────────────────────

    def authenticate(self) -> str:
        """Authenticate with ICANN and return a bearer token.

        Retries up to 5 times with exponential backoff on HTTP 429 (rate-limit).
        """
        if not self._username or not self._password:
            raise ValueError("CZDS_USERNAME / CZDS_PASSWORD are required")

        max_retries = 5
        base_delay = 5.0
        max_delay = 120.0

        for attempt in range(max_retries + 1):
            resp = requests.post(
                self._auth_url,
                json={"username": self._username, "password": self._password},
                timeout=30,
            )
            if resp.status_code == 429 and attempt < max_retries:
                retry_after = int(resp.headers.get("Retry-After", 0) or 0)
                delay = max(float(retry_after), base_delay * (2 ** attempt))
                jitter = delay * random.uniform(-0.25, 0.25)
                delay = min(delay + jitter, max_delay)
                log.warning(
                    "czds auth rate-limited (429) attempt=%d/%d sleeping=%.1fs",
                    attempt + 1, max_retries, delay,
                )
                time.sleep(delay)
                continue
            resp.raise_for_status()
            token = resp.json().get("accessToken")
            if not token:
                raise RuntimeError("CZDS auth returned no accessToken")
            return token

        raise RuntimeError(f"CZDS auth: still rate-limited after {max_retries} retries")

    # ── TLD resolution ────────────────────────────────────────────────────────

    def authorized_tlds(self, token: str) -> set[str]:
        resp = requests.get(
            f"{self._base_url}/czds/downloads/links",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        resp.raise_for_status()
        authorized: set[str] = set()
        for link in resp.json():
            filename = Path(urlparse(link).path).name
            if filename.endswith(".zone"):
                authorized.add(filename[:-5].lower())
        return authorized

    def resolve_tlds(
        self,
        authorized: set[str],
        requested: list[str] | None = None,
        exclude: set[str] | None = None,
        max_tlds: int = 0,
    ) -> list[str]:
        if requested is None or not requested:
            selected = sorted(authorized)
        else:
            selected = sorted(t for t in requested if t in authorized)
        if exclude:
            selected = [t for t in selected if t not in exclude]
        if max_tlds and max_tlds > 0:
            selected = selected[:max_tlds]
        return selected

    # ── Download ──────────────────────────────────────────────────────────────

    def download_zone_gz(self, token: str, tld: str) -> bytes:
        """Download a zone file (gzip bytes) with streaming + resumable support."""
        url = f"{self._base_url}/czds/downloads/{tld}.zone"
        chunks: list[bytes] = []
        headers = {
            "Authorization": f"Bearer {token}",
        }
        offset = 0
        while True:
            req_headers = dict(headers)
            if offset > 0:
                req_headers["Range"] = f"bytes={offset}-"
            with requests.get(
                url,
                headers=req_headers,
                stream=True,
                timeout=(30, 1200),
                allow_redirects=True,
            ) as resp:
                if resp.status_code == 416:
                    break  # Range not satisfiable → already complete
                resp.raise_for_status()
                for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                    if chunk:
                        chunks.append(chunk)
                        offset += len(chunk)
                if resp.status_code == 200:
                    break  # Server returned full body (no partial content)
                content_range = resp.headers.get("Content-Range", "")
                if not content_range:
                    break
                # If there's a content-range, check if we got everything
                try:
                    total = int(content_range.split("/")[-1])
                    if offset >= total:
                        break
                except (ValueError, IndexError):
                    break
        return b"".join(chunks)

    # ── Parse ─────────────────────────────────────────────────────────────────

    def parse_zone_gz(self, gz_bytes: bytes, tld: str) -> pl.DataFrame:
        """Parse a gzipped zone file into an ADR-001 snapshot DataFrame.

        Returns DataFrame with columns: name, tld, label.
        Filters to only include proper second-level domains under *tld*.
        Wildcard records (starting with '*') are excluded.
        """
        from ingestion.core.label import extract_label

        names: set[str] = set()
        with gzip.GzipFile(fileobj=BytesIO(gz_bytes), mode="rb") as gz:
            for line in gz:
                s = line.strip()
                if not s or s.startswith(b";"):
                    continue
                tokens = s.split(None, 1)
                if not tokens:
                    continue
                norm = _normalise(tokens[0].rstrip(b"."))
                if norm and norm != tld and norm.endswith("." + tld) and not norm.startswith("*"):
                    names.add(norm)

        if not names:
            return pl.DataFrame({"name": pl.Series([], dtype=pl.Utf8), "tld": pl.Series([], dtype=pl.Utf8), "label": pl.Series([], dtype=pl.Utf8)})

        sorted_names = sorted(names)
        return pl.DataFrame({
            "name":  sorted_names,
            "tld":   [tld] * len(sorted_names),
            "label": [extract_label(n, tld) for n in sorted_names],
        })
