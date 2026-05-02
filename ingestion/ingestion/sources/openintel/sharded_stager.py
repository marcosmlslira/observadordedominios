"""Sharded OpenINTEL stager — handles large zonefile snapshots (e.g. ch, fr, se).

For TLDs whose Parquet snapshots exceed a configurable byte threshold, the
classic in-memory parser blows the heap (multi-GB Parquet payloads + Polars
concat + dedup all sit in RAM simultaneously). This module mirrors the CZDS
sharded strategy:

1. Stream the public OpenINTEL Parquet objects from S3 to local temp files.
2. Read each Parquet via `pyarrow.parquet.iter_batches()` — one row group at a
   time, projecting only the qname column. Never materialise the full table.
3. For each batch, normalise + filter + extract the registered domain in
   Python and append the line to the temp file of its MD5-stable shard.
4. Drop the downloaded Parquet immediately to free local disk.
5. Loop the 128 shards: read shard from disk, fetch matching shard from R2,
   compute the per-shard set diff, write deltas + new current shard.

Memory peak collapses from O(snapshot) ≈ multi-GB to O(largest shard) ≈
tens of MB. Disk peak is the largest single Parquet file, freed before the
next file is downloaded.

The shard function is shared with CZDS (`ingestion.core.sharding`) so a domain
landing in OpenINTEL shard N is the same domain that would land in CZDS shard
N — useful for any future cross-source reconciliation.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import IO, Any

import polars as pl
import pyarrow.parquet as pq

from ingestion.config.constants import SHARD_COUNT
from ingestion.core.sharding import stable_shard
from ingestion.core.types import Source
from ingestion.storage.layout import Layout
from ingestion.storage.r2 import R2Storage

log = logging.getLogger(__name__)

_SNAP_COLS = ["name", "tld", "label"]
_EMPTY_SHARD = pl.DataFrame(
    {
        "name": pl.Series([], dtype=pl.Utf8),
        "tld": pl.Series([], dtype=pl.Utf8),
        "label": pl.Series([], dtype=pl.Utf8),
    }
)


def _stage_parquet_keys_to_tempdir(
    s3_client: Any,
    bucket: str,
    keys: list[str],
    tld: str,
    qname_column: str,
    num_shards: int,
    staging_dir: Path,
    *,
    batch_size: int = 65536,
) -> tuple[dict[int, Path], dict[str, int]]:
    """Stream OpenINTEL Parquet objects and write one temp file per shard.

    Returns (shard_paths, counters). Counters report total rows scanned and rows
    that survived the filters — useful as observability without changing the
    snapshot count contract (which is the unique-domain count after diff).
    """
    handles: dict[int, IO[bytes]] = {}
    shard_paths: dict[int, Path] = {}
    suffix = "." + tld
    labels = len(tld.split(".")) + 1

    rows_scanned = 0
    rows_kept = 0

    try:
        for key in keys:
            local_name = key.replace("/", "_").replace("\\", "_")
            local_parquet = staging_dir / f"download-{local_name}"
            log.info("openintel staging download key=%s", key)
            with local_parquet.open("wb") as f:
                s3_client.download_fileobj(bucket, key, f)
            try:
                pq_file = pq.ParquetFile(str(local_parquet))
                if qname_column not in pq_file.schema_arrow.names:
                    log.warning(
                        "qname column %r not found in key=%s, columns=%s",
                        qname_column, key, pq_file.schema_arrow.names,
                    )
                    continue
                for batch in pq_file.iter_batches(
                    batch_size=batch_size, columns=[qname_column]
                ):
                    values = batch.column(0).to_pylist()
                    rows_scanned += len(values)
                    for raw in values:
                        if raw is None:
                            continue
                        norm = raw.rstrip(".").lower().strip()
                        if not norm or norm.startswith("*"):
                            continue
                        if not norm.endswith(suffix):
                            continue
                        parts = norm.split(".")
                        if len(parts) < labels:
                            continue
                        reg_domain = ".".join(parts[-labels:])
                        if not reg_domain or reg_domain == tld:
                            continue
                        shard_id = stable_shard(reg_domain, num_shards)
                        handle = handles.get(shard_id)
                        if handle is None:
                            shard_path = staging_dir / f"shard-{shard_id:04d}.txt"
                            handle = shard_path.open("ab", buffering=1024 * 1024)
                            handles[shard_id] = handle
                            shard_paths[shard_id] = shard_path
                        handle.write(reg_domain.encode("utf-8"))
                        handle.write(b"\n")
                        rows_kept += 1
            finally:
                try:
                    local_parquet.unlink()
                except OSError:
                    log.warning("could not delete temp parquet %s", local_parquet)
    finally:
        for handle in handles.values():
            handle.close()

    return shard_paths, {"rows_scanned": rows_scanned, "rows_kept": rows_kept}


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


def run_sharded_openintel_diff(
    *,
    s3_client: Any,
    bucket: str,
    keys: list[str],
    tld: str,
    qname_column: str,
    snapshot_date: date,
    storage: R2Storage,
    layout: Layout,
    num_shards: int = SHARD_COUNT,
) -> tuple[int, int, int, dict[str, float | int | str]]:
    """Process a large OpenINTEL zonefile snapshot via streaming + sharding.

    Returns (snapshot_count, added_count, removed_count, metrics).
    Writes shard-level delta Parquet objects and new current-state shards to R2.
    Does NOT write the success marker (caller's responsibility).
    """
    total_started_at = perf_counter()
    log.info(
        "sharding openintel snapshot tld=%s keys=%d num_shards=%d",
        tld, len(keys), num_shards,
    )
    with TemporaryDirectory(prefix=f"openintel-{tld}-") as staging_dir_name:
        staging_dir = Path(staging_dir_name)
        stage_started_at = perf_counter()
        staged_shards, stage_counters = _stage_parquet_keys_to_tempdir(
            s3_client=s3_client,
            bucket=bucket,
            keys=keys,
            tld=tld,
            qname_column=qname_column,
            num_shards=num_shards,
            staging_dir=staging_dir,
        )
        stage_seconds = perf_counter() - stage_started_at

        current_read_seconds = 0.0
        diff_seconds = 0.0
        current_write_seconds = 0.0
        snapshot_read_seconds = 0.0
        delta_write_seconds = 0.0
        total_snapshot = 0
        total_added = 0
        total_removed = 0

        delta_prefix = layout.delta_tld_date_prefix(
            "delta", Source.OPENINTEL.value, tld, snapshot_date
        )
        delta_removed_prefix = layout.delta_tld_date_prefix(
            "delta_removed", Source.OPENINTEL.value, tld, snapshot_date
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

            curr_key = layout.shard_current_key(
                Source.OPENINTEL.value, tld, shard_id
            )
            read_started_at = perf_counter()
            curr_df = storage.get_parquet_df_or_empty(curr_key, _SNAP_COLS)
            current_read_seconds += perf_counter() - read_started_at

            diff_started_at = perf_counter()
            snap_names = set(snap_df["name"].to_list())
            curr_names = (
                set(curr_df["name"].to_list()) if len(curr_df) > 0 else set()
            )

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

            write_started_at = perf_counter()
            if len(snap_df) > 0:
                storage.put_parquet_df(curr_key, snap_df)
            elif storage.key_exists(curr_key):
                storage.put_parquet_df(curr_key, snap_df)
            current_write_seconds += perf_counter() - write_started_at

    log.info(
        "sharded openintel diff done tld=%s snapshot=%d added=%d removed=%d",
        tld, total_snapshot, total_added, total_removed,
    )
    metrics: dict[str, float | int | str] = {
        "strategy": "sharded",
        "num_shards": num_shards,
        "non_empty_shards": len(staged_shards),
        "rows_scanned": stage_counters["rows_scanned"],
        "rows_kept": stage_counters["rows_kept"],
        "stage_to_disk_seconds": round(stage_seconds, 3),
        "snapshot_read_seconds": round(snapshot_read_seconds, 3),
        "current_read_seconds": round(current_read_seconds, 3),
        "diff_seconds": round(diff_seconds, 3),
        "current_write_seconds": round(current_write_seconds, 3),
        "delta_write_seconds": round(delta_write_seconds, 3),
        "processing_seconds": round(perf_counter() - total_started_at, 3),
    }
    return total_snapshot, total_added, total_removed, metrics
