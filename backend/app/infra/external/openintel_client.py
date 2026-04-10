"""OpenINTEL clients — S3 Parquet (zonefile) and web CSV.GZ (ccTLD domain lists)."""

from __future__ import annotations

import gzip
import io
import logging
from datetime import date, timedelta
from typing import Iterator

logger = logging.getLogger(__name__)


class OpenIntelClient:
    """Read ccTLD apex-domain snapshots from the OpenINTEL public S3 bucket.

    All S3 access is anonymous (no credentials required). Parquet files are
    read in streaming mode via pyarrow dataset + s3fs so nothing is written
    to disk.

    The dataset uses forward DNS measurements: each domain generates multiple
    rows (one per record type: A, AAAA, MX, NS…). Deduplication is handled
    inside stream_apex_domains via a rolling seen-set.
    """

    def __init__(self) -> None:
        from app.core.config import settings

        self.bucket = settings.OPENINTEL_S3_BUCKET
        self.prefix = settings.OPENINTEL_S3_PREFIX
        self.region = settings.OPENINTEL_S3_REGION
        self.endpoint = settings.OPENINTEL_S3_ENDPOINT or None
        self.qname_col = settings.OPENINTEL_S3_QNAME_COLUMN
        self.max_lookback_days = settings.OPENINTEL_MAX_LOOKBACK_DAYS

        import boto3
        from botocore import UNSIGNED
        from botocore.config import Config

        boto_kwargs: dict = {
            "config": Config(
                signature_version=UNSIGNED,
                connect_timeout=10,
                read_timeout=30,
                retries={"max_attempts": 2},
                s3={"addressing_style": "path"},
            ),
            "region_name": self.region,
        }
        if self.endpoint:
            boto_kwargs["endpoint_url"] = self.endpoint
        self._s3 = boto3.client("s3", **boto_kwargs)

    def discover_snapshot(self, tld: str) -> tuple[list[str], date] | None:
        """Return (list_of_s3_keys, snapshot_date) for the most recent available snapshot.

        Scans backwards from today up to `max_lookback_days` days until it finds a
        directory with at least one Parquet file. Returns ALL part files for that day
        (Spark/Hive sharding produces multiple parts that must all be read).
        Returns None if no snapshot is found within the lookback window.
        """
        today = date.today()
        for days_back in range(self.max_lookback_days + 1):
            d = today - timedelta(days=days_back)
            prefix = (
                f"{self.prefix}"
                f"source={tld}/"
                f"year={d.year:04d}/month={d.month:02d}/day={d.day:02d}/"
            )
            try:
                paginator = self._s3.get_paginator("list_objects_v2")
                all_keys: list[str] = []
                for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                    for obj in page.get("Contents", []):
                        key = obj["Key"]
                        if key.endswith(".parquet") or key.endswith(".gz.parquet"):
                            all_keys.append(key)
                if all_keys:
                    logger.debug(
                        "OpenINTEL snapshot found for TLD=%s date=%s: %d part(s)",
                        tld,
                        d,
                        len(all_keys),
                    )
                    return all_keys, d
            except Exception:
                logger.debug(
                    "Error listing OpenINTEL prefix for TLD=%s date=%s — skipping",
                    tld,
                    d,
                    exc_info=True,
                )

        logger.info(
            "No OpenINTEL snapshot found for TLD=%s within %d days",
            tld,
            self.max_lookback_days,
        )
        return None

    def stream_apex_domains(self, s3_keys: list[str], tld: str) -> Iterator[str]:
        """Yield apex domain names for `tld` from all Parquet part files in S3.

        Reads only the query_name column with filter pushdown, normalises names
        (lowercase, strip trailing dot), reduces to apex level (eTLD+1), and
        deduplicates across all parts via a rolling seen-set (resets every 500k
        unique apexes to bound memory usage).
        """
        import pyarrow.compute as pc
        import pyarrow.dataset as ds
        import s3fs

        client_kwargs: dict = {"region_name": self.region}
        if self.endpoint:
            client_kwargs["endpoint_url"] = self.endpoint

        fs = s3fs.S3FileSystem(anon=True, client_kwargs=client_kwargs)

        # Domain names in OpenINTEL Parquet are FQDN with trailing dot: "example.fr."
        # The pyarrow filter must use the FQDN suffix to match correctly.
        fqdn_suffix = f".{tld}."
        plain_suffix = f".{tld}"
        tld_depth = len(tld.split(".")) + 1  # labels in apex: "example.fr" → 2

        seen: set[str] = set()

        for s3_key in s3_keys:
            path = f"{self.bucket}/{s3_key}"
            try:
                dataset = ds.dataset(path, filesystem=fs, format="parquet")
                scanner = dataset.scanner(
                    columns=[self.qname_col],
                    filter=pc.ends_with(ds.field(self.qname_col), fqdn_suffix),
                    batch_size=50_000,
                )
                for batch in scanner.to_batches():
                    col = batch.column(self.qname_col)
                    for val in col:
                        qname = val.as_py()
                        if not isinstance(qname, str):
                            continue

                        domain = qname.rstrip(".").lower()
                        if not domain.endswith(plain_suffix):
                            continue

                        parts = domain.split(".")
                        if len(parts) < tld_depth:
                            continue

                        apex = ".".join(parts[-tld_depth:])

                        if apex not in seen:
                            seen.add(apex)
                            yield apex

                            if len(seen) >= 500_000:
                                seen.clear()

            except Exception:
                logger.warning(
                    "Failed to stream part file for TLD=%s key=%s — skipping part",
                    tld,
                    s3_key,
                    exc_info=True,
                )


class OpenIntelCctldClient:
    """Download ccTLD apex-domain lists from OpenINTEL website (HTTP CSV.GZ).

    OpenINTEL hosts 307 ccTLD domain lists at:
      https://openintel.nl/download/domain-lists/cctlds/tld={tld}/year=YYYY/month=MM/day=DD/
    The actual file is served via an S3 proxy at object.openintel.nl/seeseetld/lists/
    and requires:
      - Cookie: openintel-data-agreement-accepted=true
      - Referer: the canonical page URL (nginx checks it)

    File format: CSV.GZ — plain domain names, one per line, no header.
    """

    def __init__(self) -> None:
        from app.core.config import settings

        self.s3_base = settings.OPENINTEL_CCTLD_S3_BASE.rstrip("/")
        self.web_url = settings.OPENINTEL_CCTLD_WEB_URL.rstrip("/")
        self.cookie_name = settings.OPENINTEL_CCTLD_COOKIE_NAME
        self.cookie_value = settings.OPENINTEL_CCTLD_COOKIE_VALUE
        self.max_lookback_days = settings.OPENINTEL_MAX_LOOKBACK_DAYS

    def _file_url(self, tld: str, d: date) -> str:
        return (
            f"{self.s3_base}/tld={tld}"
            f"/year={d.year:04d}/month={d.month:02d}/day={d.day:02d}"
            f"/ccTLD-domain-names-list.{tld}.{d.isoformat()}.csv.gz"
        )

    def _referer(self, tld: str, d: date) -> str:
        return (
            f"{self.web_url}/tld={tld}"
            f"/year={d.year:04d}/month={d.month:02d}/day={d.day:02d}/"
        )

    def discover_snapshot(self, tld: str) -> tuple[list[str], date] | None:
        """Return ([url], snapshot_date) for the most recent available file.

        Scans backwards from today up to max_lookback_days using HEAD requests.
        """
        import httpx

        today = date.today()
        headers = {
            "Cookie": f"{self.cookie_name}={self.cookie_value}",
        }

        for days_back in range(self.max_lookback_days + 1):
            d = today - timedelta(days=days_back)
            url = self._file_url(tld, d)
            headers["Referer"] = self._referer(tld, d)
            try:
                resp = httpx.head(url, headers=headers, timeout=15, follow_redirects=True)
                if resp.status_code == 200:
                    logger.debug(
                        "OpenINTEL ccTLD snapshot found for TLD=%s date=%s", tld, d
                    )
                    return [url], d
                logger.debug(
                    "OpenINTEL ccTLD HEAD %s → %d — skipping", url, resp.status_code
                )
            except Exception:
                logger.debug(
                    "Error checking OpenINTEL ccTLD URL for TLD=%s date=%s — skipping",
                    tld,
                    d,
                    exc_info=True,
                )

        logger.info(
            "No OpenINTEL ccTLD snapshot found for TLD=%s within %d days",
            tld,
            self.max_lookback_days,
        )
        return None

    def stream_apex_domains(self, file_refs: list[str], tld: str) -> Iterator[str]:
        """Yield apex domain names from a CSV.GZ URL.

        Each line in the file is a bare domain name (e.g. ``example.ac``).
        Only the most recent file URL is passed (list always has one element).
        """
        import httpx

        url = file_refs[0]
        headers = {
            "Cookie": f"{self.cookie_name}={self.cookie_value}",
            "Referer": url,  # generous referer — file URL itself also accepted
        }

        # Re-derive the proper referer from the URL path
        # URL pattern: .../tld={tld}/year=YYYY/month=MM/day=DD/ccTLD-domain-names-list.{tld}.{date}.csv.gz
        try:
            dir_url = url.rsplit("/", 1)[0] + "/"
            # Build the canonical page referer
            tld_part = f"tld={tld}"
            if tld_part in dir_url:
                after_base = dir_url[dir_url.index(tld_part):]
                headers["Referer"] = f"{self.web_url}/{after_base}"
        except Exception:
            pass  # keep fallback referer

        try:
            with httpx.stream("GET", url, headers=headers, timeout=60, follow_redirects=True) as resp:
                resp.raise_for_status()
                raw = b"".join(resp.iter_bytes())

            with gzip.open(io.BytesIO(raw), "rt", encoding="utf-8", errors="replace") as f:
                seen: set[str] = set()
                for line in f:
                    domain = line.strip().lower()
                    if not domain:
                        continue
                    if domain not in seen:
                        seen.add(domain)
                        yield domain
                        if len(seen) >= 500_000:
                            seen.clear()

        except Exception:
            logger.warning(
                "Failed to stream ccTLD file for TLD=%s url=%s",
                tld,
                url,
                exc_info=True,
            )
