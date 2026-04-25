from __future__ import annotations

import gzip
from datetime import date
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import polars as pl
import requests

from ..config import CZDSConfig
from ..models import SNAPSHOT_COLUMNS, snapshot_record_from_raw_bytes


class CZDSClient:
    def __init__(self, cfg: CZDSConfig):
        self.cfg = cfg
        self.base_url = cfg.base_url.strip().rstrip("/")

    def authenticate(self) -> str:
        if not self.cfg.username or not self.cfg.password:
            raise ValueError("CZDS credentials are required")
        resp = requests.post(
            self.cfg.auth_url,
            json={"username": self.cfg.username, "password": self.cfg.password},
            timeout=30,
        )
        resp.raise_for_status()
        token = resp.json().get("accessToken")
        if not token:
            raise RuntimeError("CZDS auth returned no accessToken")
        return token

    def authorized_tlds(self, token: str) -> set[str]:
        links_resp = requests.get(
            f"{self.base_url}/czds/downloads/links",
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
        links_resp.raise_for_status()
        authorized: set[str] = set()
        for link in links_resp.json():
            filename = Path(urlparse(link).path).name
            if filename.endswith(".zone"):
                authorized.add(filename[:-5].lower())
        return authorized

    def resolve_tlds(self, authorized: set[str]) -> list[str]:
        if self.cfg.tlds.strip().lower() == "all":
            selected = sorted(authorized)
        else:
            requested = {t.strip().lower() for t in self.cfg.tlds.split(",") if t.strip()}
            selected = sorted([t for t in requested if t in authorized])
        excluded = {t.strip().lower() for t in self.cfg.exclude_tlds.split(",") if t.strip()}
        if excluded:
            selected = [t for t in selected if t not in excluded]
        if self.cfg.max_tlds > 0:
            selected = selected[: self.cfg.max_tlds]
        return selected

    def download_zone_gz(self, token: str, tld: str) -> bytes:
        url = f"{self.base_url}/czds/downloads/{tld}.zone"
        with requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            stream=True,
            timeout=(30, 1200),
            allow_redirects=True,
        ) as resp:
            resp.raise_for_status()
            return resp.content

    def parse_zone_gz_to_snapshot(self, gz_bytes: bytes, tld: str) -> pl.DataFrame:
        rows: list[dict[str, str]] = []
        with gzip.GzipFile(fileobj=BytesIO(gz_bytes), mode="rb") as gz:
            for line in gz:
                s = line.strip()
                if not s or s.startswith(b";"):
                    continue
                tokens = s.split(None, 1)
                if not tokens:
                    continue
                owner_bytes = tokens[0].rstrip(b".")
                rec = snapshot_record_from_raw_bytes(owner_bytes)
                if rec["domain_norm"] and rec["domain_norm"] != tld and rec["domain_norm"].endswith("." + tld):
                    rows.append(rec)
        if not rows:
            return pl.DataFrame({c: [] for c in SNAPSHOT_COLUMNS})
        return pl.DataFrame(rows).select(SNAPSHOT_COLUMNS).unique(subset=["domain_norm"], keep="first")

    def choose_snapshot_date(self, *, today: date) -> date | None:
        if self.cfg.snapshot_date_override is not None:
            return self.cfg.snapshot_date_override
        if self.cfg.start_date and today < self.cfg.start_date:
            return None
        return today
