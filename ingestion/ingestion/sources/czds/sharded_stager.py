"""Sharded CZDS stager — handles large TLDs (e.g. .com with 424M domains).

For TLDs exceeding SHARD_THRESHOLD entries, we cannot hold the entire snapshot
in memory.  Instead:

1. Download the zone file (gzip).
2. Parse it streaming, assigning each domain to a shard via MD5.
3. Stage each shard as a Parquet file in R2.
4. For each shard: load corresponding current-state shard from R2, compute diff,
   accumulate added/removed counts.
5. Write cumulative delta Parquet to R2, overwrite current-state shards.

The stable shard function must be byte-identical across runs for consistency.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import logging
from collections import defaultdict
from datetime import date
from time import perf_counter

import polars as pl

from ingestion.config.constants import SHARD_COUNT
from ingestion.config.settings import Settings
from ingestion.core.types import Source
from ingestion.storage.layout import Layout
from ingestion.storage.r2 import R2Storage

log = logging.getLogger(__name__)

_SNAP_COLS = ["name", "tld", "label"]
_EMPTY_SHARD = pl.DataFrame({"name": pl.Series([], dtype=pl.Utf8), "tld": pl.Series([], dtype=pl.Utf8), "label": pl.Series([], dtype=pl.Utf8)})


def _stable_shard(domain_norm: str, num_shards: int = SHARD_COUNT) -> int:
    return int(hashlib.md5(domain_norm.encode("utf-8")).hexdigest()[:8], 16) % num_shards


def _shard_gz_bytes(gz_bytes: bytes, tld: str, num_shards: int) -> dict[int, list[dict]]:
    """Stream-parse zone file and bucket rows into shards (in memory dict)."""
    from ingestion.core.label import extract_label

    shards: dict[int, list[dict]] = defaultdict(list)
    with gzip.GzipFile(fileobj=io.BytesIO(gz_bytes), mode="rb") as gz:
        for line in gz:
            s = line.strip()
            if not s or s.startswith(b";"):
                continue
            tokens = s.split(None, 1)
            if not tokens:
                continue
            norm = tokens[0].rstrip(b".").decode("latin-1").lower().strip()
            if not norm or norm == tld or not norm.endswith("." + tld) or norm.startswith("*"):
                continue
            shard_id = _stable_shard(norm, num_shards)
            shards[shard_id].append({"name": norm, "tld": tld, "label": extract_label(norm, tld)})
    return shards


def run_sharded_czds_diff(
    *,
    gz_bytes: bytes,
    tld: str,
    snapshot_date: date,
    storage: R2Storage,
    layout: Layout,
    num_shards: int = SHARD_COUNT,
 ) -> tuple[int, int, int, dict[str, float | int | str]]:
    """Process a large CZDS zone file using sharding.

    Returns (snapshot_count, added_count, removed_count).
    Writes delta Parquet and new current-state shards to R2.
    Does NOT write the success marker (caller's responsibility).
    """
    total_started_at = perf_counter()
    log.info("sharding zone file tld=%s num_shards=%d", tld, num_shards)
    parse_started_at = perf_counter()
    shard_buckets = _shard_gz_bytes(gz_bytes, tld, num_shards)
    shard_parse_seconds = perf_counter() - parse_started_at
    total_snapshot = sum(len(v) for v in shard_buckets.values())
    log.info("zone parsed tld=%s total_domains=%d", tld, total_snapshot)

    added_all: list[pl.DataFrame] = []
    removed_all: list[pl.DataFrame] = []
    current_read_seconds = 0.0
    diff_seconds = 0.0
    current_write_seconds = 0.0

    for shard_id in range(num_shards):
        rows = shard_buckets.get(shard_id, [])
        snap_df = (
            pl.DataFrame(rows, schema={"name": pl.Utf8, "tld": pl.Utf8, "label": pl.Utf8})
            if rows else _EMPTY_SHARD.clone()
        )

        curr_key = layout.shard_current_key(Source.CZDS.value, tld, shard_id)
        read_started_at = perf_counter()
        curr_df = storage.get_parquet_df_or_empty(curr_key, _SNAP_COLS)
        current_read_seconds += perf_counter() - read_started_at

        diff_started_at = perf_counter()
        snap_names = set(snap_df["name"].to_list())
        curr_names = set(curr_df["name"].to_list()) if len(curr_df) > 0 else set()

        added_names = snap_names - curr_names
        removed_names = curr_names - snap_names

        if added_names:
            added_all.append(snap_df.filter(pl.col("name").is_in(added_names)))
        if removed_names:
            removed_all.append(curr_df.filter(pl.col("name").is_in(removed_names)))
        diff_seconds += perf_counter() - diff_started_at

        # Overwrite current shard
        write_started_at = perf_counter()
        if rows:
            storage.put_parquet_df(curr_key, snap_df)
        elif storage.key_exists(curr_key):
            # TLD shard is now empty — overwrite with empty frame
            storage.put_parquet_df(curr_key, snap_df)
        current_write_seconds += perf_counter() - write_started_at

    added_df = pl.concat(added_all, how="vertical_relaxed") if added_all else _EMPTY_SHARD.clone()
    removed_df = pl.concat(removed_all, how="vertical_relaxed") if removed_all else _EMPTY_SHARD.clone()

    # Write deltas (name, tld, label) — delta_loader injects added_day from snapshot_date
    delta_write_started_at = perf_counter()
    if len(added_df) > 0:
        storage.put_parquet_df(layout.delta_key(Source.CZDS.value, tld, snapshot_date), added_df)

    if len(removed_df) > 0:
        storage.put_parquet_df(layout.delta_removed_key(Source.CZDS.value, tld, snapshot_date), removed_df)
    delta_write_seconds = perf_counter() - delta_write_started_at

    log.info(
        "sharded diff done tld=%s snapshot=%d added=%d removed=%d",
        tld, total_snapshot, len(added_df), len(removed_df),
    )
    metrics: dict[str, float | int | str] = {
        "strategy": "sharded",
        "num_shards": num_shards,
        "non_empty_shards": len(shard_buckets),
        "shard_parse_seconds": round(shard_parse_seconds, 3),
        "current_read_seconds": round(current_read_seconds, 3),
        "diff_seconds": round(diff_seconds, 3),
        "current_write_seconds": round(current_write_seconds, 3),
        "delta_write_seconds": round(delta_write_seconds, 3),
        "processing_seconds": round(perf_counter() - total_started_at, 3),
    }
    return total_snapshot, len(added_df), len(removed_df), metrics
