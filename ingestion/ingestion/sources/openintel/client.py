"""OpenINTEL client — discovers and downloads DNS zone-file snapshots.

Two modes:
- zonefile: reads Parquet files from the public OpenINTEL S3 bucket (unsigned)
- cctld-web: downloads CSV.GZ files from the OpenINTEL web portal
- auto: selects mode based on TLD — zonefile for known S3 TLDs, else cctld-web
"""

from __future__ import annotations

import gzip
import logging
from datetime import date, timedelta
from io import BytesIO

import boto3
import polars as pl
import requests
from botocore import UNSIGNED
from botocore.config import Config as BotoConfig

from ingestion.config.settings import Settings

log = logging.getLogger(__name__)


class OpenIntelClient:
    def __init__(self, cfg: Settings) -> None:
        self._mode = cfg.openintel_mode
        self._zonefile_bucket = cfg.openintel_zonefile_bucket
        self._zonefile_prefix = cfg.openintel_zonefile_prefix.strip("/") + "/"
        self._zonefile_endpoint = cfg.openintel_zonefile_endpoint
        self._zonefile_region = cfg.openintel_zonefile_region
        self._zonefile_qname_column = cfg.openintel_zonefile_qname_column
        self._zonefile_tlds = {t.strip().lower() for t in cfg.openintel_zonefile_tlds.split(",") if t.strip()}
        self._max_lookback_days = cfg.openintel_max_lookback_days
        self._max_scan_days = cfg.openintel_max_scan_days
        self._web_base = cfg.openintel_web_base.rstrip("/")
        self._web_files_base = cfg.openintel_web_files_base.rstrip("/")
        self._web_cookie_name = cfg.openintel_web_cookie_name
        self._web_cookie_value = cfg.openintel_web_cookie_value

        self._s3 = boto3.client(
            "s3",
            endpoint_url=self._zonefile_endpoint,
            region_name=self._zonefile_region,
            config=BotoConfig(signature_version=UNSIGNED, s3={"addressing_style": "path"}),
        )

    # ── Mode selection ────────────────────────────────────────────────────────

    def mode_for_tld(self, tld: str) -> str:
        if self._mode == "zonefile":
            return "zonefile"
        if self._mode == "cctld-web":
            return "cctld-web"
        return "zonefile" if tld in self._zonefile_tlds else "cctld-web"

    # ── Date candidates ───────────────────────────────────────────────────────

    def _date_candidates(
        self, *, today: date, prefer_earliest: bool, start_date: date | None
    ) -> list[date]:
        if start_date:
            min_date = max(start_date, today - timedelta(days=self._max_scan_days))
        else:
            min_date = today - timedelta(days=self._max_lookback_days)
        days = (today - min_date).days
        candidates = [min_date + timedelta(days=i) for i in range(days + 1)]
        return candidates if prefer_earliest else list(reversed(candidates))

    # ── Zonefile (S3) discovery ───────────────────────────────────────────────

    def discover_zonefile_snapshot(
        self,
        *,
        tld: str,
        today: date,
        prefer_earliest: bool = False,
        start_date: date | None = None,
    ) -> tuple[list[str] | None, date | None]:
        for d in self._date_candidates(today=today, prefer_earliest=prefer_earliest, start_date=start_date):
            prefix = (
                f"{self._zonefile_prefix}"
                f"source={tld}/year={d.year:04d}/month={d.month:02d}/day={d.day:02d}/"
            )
            keys: list[str] = []
            paginator = self._s3.get_paginator("list_objects_v2")
            try:
                for page in paginator.paginate(Bucket=self._zonefile_bucket, Prefix=prefix):
                    for obj in page.get("Contents", []):
                        k = obj["Key"]
                        if k.endswith(".parquet") or k.endswith(".gz.parquet"):
                            keys.append(k)
            except Exception as exc:
                log.warning("zonefile discovery error tld=%s date=%s err=%s", tld, d, exc)
                continue
            if keys:
                return keys, d
        return None, None

    def parse_zonefile_snapshot(self, *, keys: list[str], tld: str) -> pl.DataFrame:
        from ingestion.core.label import extract_label

        dfs: list[pl.DataFrame] = []
        for key in keys:
            try:
                obj = self._s3.get_object(Bucket=self._zonefile_bucket, Key=key)
                payload = obj["Body"].read()
                df = pl.read_parquet(BytesIO(payload))
            except Exception as exc:
                log.warning("failed to read zonefile key=%s err=%s", key, exc)
                continue
            col = self._zonefile_qname_column
            if col not in df.columns:
                log.warning("qname column %r not found in key=%s, columns=%s", col, key, df.columns)
                continue
            dfs.append(df.select(pl.col(col).cast(pl.Utf8).alias("qname_raw")))

        if not dfs:
            return _empty_snapshot()

        labels = len(tld.split(".")) + 1
        df_all = pl.concat(dfs, how="vertical_relaxed")
        names_df = (
            df_all
            .with_columns(pl.col("qname_raw").str.replace(r"\.$", "").str.to_lowercase().alias("name"))
            .filter(pl.col("name").str.ends_with("." + tld))
            .filter(~pl.col("name").str.starts_with("*"))
            .with_columns(
                pl.col("name").str.split(".").list.tail(labels).list.join(".").alias("name")
            )
            .filter(pl.col("name") != "")
            .select("name")
            .unique()
        )
        sorted_names = sorted(names_df["name"].to_list())
        return pl.DataFrame({
            "name":  sorted_names,
            "tld":   [tld] * len(sorted_names),
            "label": [extract_label(n, tld) for n in sorted_names],
        })

    # ── Web (cctld-web) discovery ─────────────────────────────────────────────

    def _web_file_url(self, tld: str, d: date) -> str:
        return (
            f"{self._web_files_base}/tld={tld}"
            f"/year={d.year:04d}/month={d.month:02d}/day={d.day:02d}"
            f"/ccTLD-domain-names-list.{tld}.{d.isoformat()}.csv.gz"
        )

    def _web_referer(self, tld: str, d: date) -> str:
        return f"{self._web_base}/tld={tld}/year={d.year:04d}/month={d.month:02d}/day={d.day:02d}/"

    def discover_web_snapshot(
        self,
        *,
        tld: str,
        today: date,
        prefer_earliest: bool = False,
        start_date: date | None = None,
    ) -> tuple[list[str] | None, date | None]:
        for d in self._date_candidates(today=today, prefer_earliest=prefer_earliest, start_date=start_date):
            url = self._web_file_url(tld, d)
            headers = {
                "Cookie": f"{self._web_cookie_name}={self._web_cookie_value}",
                "Referer": self._web_referer(tld, d),
            }
            try:
                resp = requests.head(url, headers=headers, timeout=20, allow_redirects=False)
                if resp.status_code in (200, 301, 302, 307, 308):
                    return [url], d
            except Exception:
                pass
        return None, None

    def parse_web_snapshot(self, *, url: str, tld: str, snapshot_date: date) -> pl.DataFrame:
        from ingestion.core.label import extract_label

        headers = {
            "Cookie": f"{self._web_cookie_name}={self._web_cookie_value}",
            "Referer": self._web_referer(tld, snapshot_date),
        }
        with requests.get(
            url, headers=headers, stream=True, timeout=(30, 1200), allow_redirects=True
        ) as resp:
            resp.raise_for_status()
            payload = resp.content

        names: set[str] = set()
        with gzip.GzipFile(fileobj=BytesIO(payload), mode="rb") as gz:
            for line in gz:
                raw_bytes = line.strip()
                if raw_bytes:
                    norm = raw_bytes.decode("latin-1").lower().strip()
                    if norm and not norm.startswith("*"):
                        names.add(norm)

        if not names:
            return _empty_snapshot()
        sorted_names = sorted(names)
        return pl.DataFrame({
            "name":  sorted_names,
            "tld":   [tld] * len(sorted_names),
            "label": [extract_label(n, tld) for n in sorted_names],
        })


def _empty_snapshot() -> pl.DataFrame:
    return pl.DataFrame({
        "name":  pl.Series([], dtype=pl.Utf8),
        "tld":   pl.Series([], dtype=pl.Utf8),
        "label": pl.Series([], dtype=pl.Utf8),
    })
