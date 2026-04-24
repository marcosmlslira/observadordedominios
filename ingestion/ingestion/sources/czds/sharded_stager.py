"""Sharded CZDS stager — handles large TLDs (e.g. .com with 424M domains).

For TLDs exceeding SHARD_THRESHOLD entries, we cannot hold the entire snapshot
in memory.  Instead:

1. Download the zone file (gzip).
2. Parse it streaming, assigning each domain to a shard via MD5.
3. Stage each shard to local temp files so the full snapshot never sits in RAM.
4. For each shard: load corresponding current-state shard from R2, compute diff,
   write shard deltas to R2, and overwrite current-state shards.

The stable shard function must be byte-identical across runs for consistency.
"""

from __future__ import annotations

import gzip
import hashlib
import io
import logging
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import IO

import polars as pl

from ingestion.config.constants import SHARD_COUNT
from ingestion.core.types import Source
from ingestion.storage.layout import Layout
from ingestion.storage.r2 import R2Storage

log = logging.getLogger(__name__)

_SNAP_COLS = ["name", "tld", "label"]
_EMPTY_SHARD = pl.DataFrame({"name": pl.Series([], dtype=pl.Utf8), "tld": pl.Series([], dtype=pl.Utf8), "label": pl.Series([], dtype=pl.Utf8)})


def _stable_shard(domain_norm: str, num_shards: int = SHARD_COUNT) -> int:
    return int(hashlib.md5(domain_norm.encode("utf-8")).hexdigest()[:8], 16) % num_shards


def _stage_shards_to_tempdir(gz_bytes: bytes, tld: str, num_shards: int, staging_dir: Path) -> dict[int, Path]:
    """Stream-parse zone file and write one temp file per shard."""
    handles: dict[int, IO[bytes]] = {}
    shard_paths: dict[int, Path] = {}
    with gzip.GzipFile(fileobj=io.BytesIO(gz_bytes), mode="rb") as gz:
        try:
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
                if shard_id not in handles:
                    shard_path = staging_dir / f"shard-{shard_id:04d}.txt"
                    handles[shard_id] = shard_path.open("ab", buffering=1024 * 1024)
                    shard_paths[shard_id] = shard_path
                handles[shard_id].write(norm.encode("utf-8"))
                handles[shard_id].write(b"\n")
        finally:
            for handle in handles.values():
                handle.close()
    return shard_paths


def _read_staged_shard(path: Path | None, tld: str) -> pl.DataFrame:
    if path is None or not path.exists() or path.stat().st_size == 0:
        return _EMPTY_SHARD.clone()
    return (
        pl.read_csv(
            path,
            has_header=False,
            new_columns=["name"],
        )
        .with_columns(
            pl.lit(tld).alias("tld"),
            pl.col("name").str.strip_suffix(f".{tld}").alias("label"),
        )
        .select(_SNAP_COLS)
        .unique(subset=["name"], maintain_order=False)
    )


def run_sharded_czds_diff(
    *,
    gz_bytes: bytes,
    tld: str,
    snapshot_date: date,
    storage: R2Storage,
    layout: Layout,
    num_shards: int = SHARD_COUNT,
 ) -> tuple[int, int, int, dict[str, float | int | str]]:
    """Process a large CZDS zone file using streaming shard staging.

    Returns (snapshot_count, added_count, removed_count).
    Writes shard-level delta Parquet objects and new current-state shards to R2.
    Does NOT write the success marker (caller's responsibility).
    """
    total_started_at = perf_counter()
    log.info("sharding zone file tld=%s num_shards=%d", tld, num_shards)
    with TemporaryDirectory(prefix=f"czds-{tld}-") as staging_dir_name:
        staging_dir = Path(staging_dir_name)
        stage_started_at = perf_counter()
        staged_shards = _stage_shards_to_tempdir(gz_bytes, tld, num_shards, staging_dir)
        stage_seconds = perf_counter() - stage_started_at

        current_read_seconds = 0.0
        diff_seconds = 0.0
        current_write_seconds = 0.0
        snapshot_read_seconds = 0.0
        delta_write_seconds = 0.0
        total_snapshot = 0
        total_added = 0
        total_removed = 0

        delta_prefix = layout.delta_tld_date_prefix("delta", Source.CZDS.value, tld, snapshot_date)
        delta_removed_prefix = layout.delta_tld_date_prefix(
            "delta_removed",
            Source.CZDS.value,
            tld,
            snapshot_date,
        )
        stale_keys = storage.list_keys(delta_prefix)
        stale_keys.extend(storage.list_keys(delta_removed_prefix))
        if stale_keys:
            storage.delete_keys(stale_keys)

        for shard_id in range(num_shards):
            snapshot_path = staged_shards.get(shard_id)
            snapshot_read_started_at = perf_counter()
            snap_df = _read_staged_shard(snapshot_path, tld)
            snapshot_read_seconds += perf_counter() - snapshot_read_started_at
            total_snapshot += len(snap_df)

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
                added_df = snap_df.filter(pl.col("name").is_in(added_names))
                total_added += len(added_df)
                delta_key = f"{delta_prefix}shard={shard_id:04d}.parquet"
                delta_write_started_at = perf_counter()
                storage.put_parquet_df(delta_key, added_df)
                delta_write_seconds += perf_counter() - delta_write_started_at
            if removed_names:
                removed_df = curr_df.filter(pl.col("name").is_in(removed_names))
                total_removed += len(removed_df)
                removed_key = f"{delta_removed_prefix}shard={shard_id:04d}.parquet"
                delta_write_started_at = perf_counter()
                storage.put_parquet_df(removed_key, removed_df)
                delta_write_seconds += perf_counter() - delta_write_started_at
            diff_seconds += perf_counter() - diff_started_at

            # Overwrite current shard
            write_started_at = perf_counter()
            if len(snap_df) > 0:
                storage.put_parquet_df(curr_key, snap_df)
            elif storage.key_exists(curr_key):
                storage.put_parquet_df(curr_key, snap_df)
            current_write_seconds += perf_counter() - write_started_at

    log.info(
        "sharded diff done tld=%s snapshot=%d added=%d removed=%d",
        tld, total_snapshot, total_added, total_removed,
    )
    metrics: dict[str, float | int | str] = {
        "strategy": "sharded",
        "num_shards": num_shards,
        "non_empty_shards": len(staged_shards),
        "stage_to_disk_seconds": round(stage_seconds, 3),
        "snapshot_read_seconds": round(snapshot_read_seconds, 3),
        "current_read_seconds": round(current_read_seconds, 3),
        "diff_seconds": round(diff_seconds, 3),
        "current_write_seconds": round(current_write_seconds, 3),
        "delta_write_seconds": round(delta_write_seconds, 3),
        "processing_seconds": round(perf_counter() - total_started_at, 3),
    }
    return total_snapshot, total_added, total_removed, metrics
