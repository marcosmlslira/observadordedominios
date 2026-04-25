from __future__ import annotations

import gzip
from datetime import date, timedelta
from io import BytesIO
from urllib.parse import urlparse

import boto3
import polars as pl
import requests
from botocore import UNSIGNED
from botocore.config import Config as BotoConfig

from ..config import OpenIntelConfig
from ..models import SNAPSHOT_COLUMNS, snapshot_record_from_raw_bytes, text_to_b64


class OpenIntelClient:
    def __init__(self, cfg: OpenIntelConfig):
        self.cfg = cfg
        self.zonefile_prefix = cfg.zonefile_prefix.strip().strip("/") + "/"
        self.zonefile_tlds = {t.strip().lower() for t in cfg.zonefile_tlds.split(",") if t.strip()}
        self.web_base = cfg.web_base.strip().rstrip("/")
        self.web_files_base = cfg.web_files_base.strip().rstrip("/")
        self.tlds = [t.strip().lower() for t in cfg.tlds.split(",") if t.strip()]
        if cfg.max_tlds > 0:
            self.tlds = self.tlds[: cfg.max_tlds]

        self.s3 = boto3.client(
            "s3",
            endpoint_url=cfg.zonefile_endpoint,
            region_name=cfg.zonefile_region,
            config=BotoConfig(signature_version=UNSIGNED, s3={"addressing_style": "path"}),
        )

    def probe(self) -> None:
        if self.cfg.mode in {"auto", "zonefile"}:
            self.s3.list_objects_v2(
                Bucket=self.cfg.zonefile_bucket,
                Prefix=self.zonefile_prefix,
                MaxKeys=1,
            )
        if self.cfg.mode in {"auto", "cctld-web"}:
            headers = {"Cookie": f"{self.cfg.web_cookie_name}={self.cfg.web_cookie_value}"}
            # Do not follow redirects in probe to avoid long hangs on external chains.
            resp = requests.head(self.web_base, headers=headers, timeout=20, allow_redirects=False)
            if resp.status_code >= 500:
                raise RuntimeError(f"OpenINTEL web probe failed ({resp.status_code})")

    def mode_for_tld(self, tld: str) -> str:
        if self.cfg.mode == "zonefile":
            return "zonefile"
        if self.cfg.mode == "cctld-web":
            return "cctld-web"
        return "zonefile" if tld in self.zonefile_tlds else "cctld-web"

    def _date_candidates(self, *, today: date, prefer_earliest: bool, start_date: date | None) -> list[date]:
        if self.cfg.snapshot_date_override is not None:
            return [self.cfg.snapshot_date_override]
        if start_date:
            min_date = max(start_date, today - timedelta(days=self.cfg.max_scan_days))
        else:
            min_date = today - timedelta(days=self.cfg.max_lookback_days)
        days = (today - min_date).days
        candidates = [min_date + timedelta(days=i) for i in range(days + 1)]
        return candidates if prefer_earliest else list(reversed(candidates))

    def target_snapshot_date(self, *, today: date) -> date:
        return self.cfg.snapshot_date_override or today

    def discover_zonefile_snapshot(
        self,
        *,
        tld: str,
        today: date,
        prefer_earliest: bool,
        start_date: date | None,
    ) -> tuple[list[str] | None, date | None]:
        for d in self._date_candidates(today=today, prefer_earliest=prefer_earliest, start_date=start_date):
            prefix = (
                f"{self.zonefile_prefix}"
                f"source={tld}/year={d.year:04d}/month={d.month:02d}/day={d.day:02d}/"
            )
            keys: list[str] = []
            paginator = self.s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.cfg.zonefile_bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    k = obj["Key"]
                    if k.endswith(".parquet") or k.endswith(".gz.parquet"):
                        keys.append(k)
            if keys:
                return keys, d
        return None, None

    def _web_file_url(self, tld: str, d: date) -> str:
        return (
            f"{self.web_files_base}/tld={tld}"
            f"/year={d.year:04d}/month={d.month:02d}/day={d.day:02d}"
            f"/ccTLD-domain-names-list.{tld}.{d.isoformat()}.csv.gz"
        )

    def _web_referer(self, tld: str, d: date) -> str:
        return f"{self.web_base}/tld={tld}/year={d.year:04d}/month={d.month:02d}/day={d.day:02d}/"

    def discover_web_snapshot(
        self,
        *,
        tld: str,
        today: date,
        prefer_earliest: bool,
        start_date: date | None,
    ) -> tuple[list[str] | None, date | None]:
        for d in self._date_candidates(today=today, prefer_earliest=prefer_earliest, start_date=start_date):
            url = self._web_file_url(tld, d)
            headers = {
                "Cookie": f"{self.cfg.web_cookie_name}={self.cfg.web_cookie_value}",
                "Referer": self._web_referer(tld, d),
            }
            try:
                resp = requests.head(url, headers=headers, timeout=20, allow_redirects=False)
                if resp.status_code in (200, 301, 302, 307, 308):
                    return [url], d
            except Exception:
                pass
        return None, None

    def parse_zonefile_snapshot(self, *, keys: list[str], tld: str, max_files_per_step: int) -> pl.DataFrame:
        if len(keys) > max_files_per_step:
            raise RuntimeError(f"too many zonefile keys ({len(keys)} > {max_files_per_step})")

        dfs: list[pl.DataFrame] = []
        for key in keys:
            obj = self.s3.get_object(Bucket=self.cfg.zonefile_bucket, Key=key)
            payload = obj["Body"].read()
            df = pl.read_parquet(BytesIO(payload))
            if self.cfg.zonefile_qname_column not in df.columns:
                continue
            dfs.append(df.select(pl.col(self.cfg.zonefile_qname_column).cast(pl.Utf8).alias("qname_raw")))

        if not dfs:
            return pl.DataFrame({c: [] for c in SNAPSHOT_COLUMNS})

        labels = len(tld.split(".")) + 1
        df_all = pl.concat(dfs, how="vertical_relaxed")
        return (
            df_all
            .with_columns(pl.col("qname_raw").str.replace(r"\.$", "").alias("qname_raw"))
            .filter(pl.col("qname_raw").str.to_lowercase().str.ends_with("." + tld))
            .with_columns(
                pl.col("qname_raw").str.split(".").list.tail(labels).list.join(".").alias("domain_raw")
            )
            .with_columns(
                pl.col("domain_raw").str.to_lowercase().alias("domain_norm"),
                pl.col("domain_raw").map_elements(text_to_b64, return_dtype=pl.Utf8).alias("domain_raw_b64"),
            )
            .select(SNAPSHOT_COLUMNS)
            .filter(pl.col("domain_norm") != "")
            .unique(subset=["domain_norm"], keep="first")
        )

    def parse_web_snapshot(self, *, url: str, tld: str, snapshot_date: date) -> pl.DataFrame:
        headers = {
            "Cookie": f"{self.cfg.web_cookie_name}={self.cfg.web_cookie_value}",
            "Referer": self._web_referer(tld, snapshot_date),
        }
        with requests.get(url, headers=headers, stream=True, timeout=(30, 1200), allow_redirects=True) as resp:
            resp.raise_for_status()
            payload = resp.content

        rows: list[dict[str, str]] = []
        with gzip.GzipFile(fileobj=BytesIO(payload), mode="rb") as gz:
            for line in gz:
                raw = line.strip()
                if raw:
                    rows.append(snapshot_record_from_raw_bytes(raw))

        if not rows:
            return pl.DataFrame({c: [] for c in SNAPSHOT_COLUMNS})
        return pl.DataFrame(rows).select(SNAPSHOT_COLUMNS).unique(subset=["domain_norm"], keep="first")
