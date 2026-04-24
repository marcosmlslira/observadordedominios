"""PostgreSQL bulk loader — reads delta Parquet files from R2 and loads into domain / domain_removed tables.

Strategy:
  1. Read delta Parquet(s) from R2 for the given source + tld + snapshot_date.
  2. Convert snapshot_date string → added_day INTEGER (YYYYMMDD).
  3. DETACH partition from parent so indexes can be managed independently.
  4. Drop non-PK indexes before bulk load (major speedup, especially for GIN trigram).
  5. Load shards in parallel (4 workers) using direct COPY into the detached partition.
  6. Rebuild indexes after all shards are loaded.
  7. ATTACH partition back to parent.
  8. Repeat for delta_removed → domain_removed.
"""

from __future__ import annotations

import io
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from time import perf_counter

import psycopg2
import polars as pl

from ingestion.storage.layout import Layout
from ingestion.storage.r2 import R2Storage

log = logging.getLogger(__name__)

_PARALLEL_WORKERS = 4


def _date_to_int(d: str) -> int:
    """Convert ISO date string '2026-04-23' → 20260423."""
    return int(d.replace("-", ""))


def _partition_name(table: str, tld: str) -> str:
    safe_tld = tld.replace("-", "_").replace(".", "_")
    return f"{table}_{safe_tld}"


def _is_attached(conn, parent: str, partition: str) -> bool:
    """Return True if partition is currently attached to parent."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM pg_inherits
            WHERE inhrelid = %s::regclass AND inhparent = %s::regclass
            """,
            (partition, parent),
        )
        return cur.fetchone() is not None


def _ensure_partition(conn, tld: str) -> None:
    """Create domain and domain_removed partitions for a TLD if they don't exist."""
    safe_tld = tld.replace("-", "_").replace(".", "_")
    with conn.cursor() as cur:
        # Check if partition already exists (might be detached standalone table)
        cur.execute(
            "SELECT 1 FROM pg_tables WHERE tablename = %s",
            (f"domain_{safe_tld}",),
        )
        if not cur.fetchone():
            cur.execute(
                f"CREATE TABLE domain_{safe_tld} PARTITION OF domain FOR VALUES IN ('{tld}')"
            )
        cur.execute(
            "SELECT 1 FROM pg_tables WHERE tablename = %s",
            (f"domain_removed_{safe_tld}",),
        )
        if not cur.fetchone():
            cur.execute(
                f"CREATE TABLE domain_removed_{safe_tld} PARTITION OF domain_removed FOR VALUES IN ('{tld}')"
            )
    conn.commit()


def _detach_partition(conn, parent: str, partition: str, tld: str) -> None:
    """Detach partition from parent. No-op if already detached."""
    if not _is_attached(conn, parent, partition):
        log.info("loader %s already detached from %s", partition, parent)
        return
    with conn.cursor() as cur:
        cur.execute(f"ALTER TABLE {parent} DETACH PARTITION {partition}")
    conn.commit()
    log.info("loader detached %s from %s", partition, parent)


def _attach_partition(conn, parent: str, partition: str, tld: str) -> None:
    """Re-attach partition to parent. No-op if already attached."""
    if _is_attached(conn, parent, partition):
        log.info("loader %s already attached to %s", partition, parent)
        return
    with conn.cursor() as cur:
        cur.execute(
            f"ALTER TABLE {parent} ATTACH PARTITION {partition} FOR VALUES IN ('{tld}')"
        )
    conn.commit()
    log.info("loader attached %s back to %s", partition, parent)


def _drop_standalone_indexes(conn, partition: str) -> list[str]:
    """Drop non-PK indexes on a detached (standalone) partition. Returns DDL for rebuild."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = %s
              AND indexname NOT IN (
                SELECT conname FROM pg_constraint
                WHERE conrelid = %s::regclass AND contype = 'p'
              )
            """,
            (partition, partition),
        )
        rows = cur.fetchall()
        ddls = []
        for indexname, indexdef in rows:
            cur.execute(f"DROP INDEX IF EXISTS {indexname}")
            ddls.append(indexdef)
            log.info("loader dropped index %s on %s", indexname, partition)
    conn.commit()
    return ddls


def _rebuild_indexes(conn, ddls: list[str], partition: str) -> None:
    """Rebuild previously dropped indexes on a partition."""
    for ddl in ddls:
        log.info("loader rebuilding index on %s ...", partition)
        t0 = perf_counter()
        with conn.cursor() as cur:
            cur.execute(ddl)
        conn.commit()
        log.info("loader index rebuilt on %s in %.1fs", partition, perf_counter() - t0)


@dataclass
class _ShardArgs:
    database_url: str
    storage: R2Storage
    key: str
    partition: str
    columns: list[str]
    added_day: int
    shard_idx: int
    total_shards: int
    tld: str
    counter_lock: threading.Lock
    total_counter: list[int]  # mutable single-element list for shared counter


def _load_shard_worker(args: _ShardArgs) -> int:
    """Download one shard from R2 and COPY directly into the target partition.

    Each worker uses its own dedicated DB connection (psycopg2 is not thread-safe).
    Direct COPY (no temp table, no ON CONFLICT) — safe for CZDS sharded data where
    each domain name appears in exactly one shard.
    """
    raw = args.storage.get_bytes(args.key)
    df = pl.read_parquet(io.BytesIO(raw))

    required = [c for c in args.columns if c != "added_day"]
    for c in required:
        if c not in df.columns:
            df = df.with_columns(pl.lit(None).cast(pl.Utf8).alias(c))

    if "added_day" in args.columns:
        df = df.select(required).with_columns(
            pl.lit(args.added_day).cast(pl.Int32).alias("added_day")
        )
    else:
        df = df.select(args.columns)

    if len(df) == 0:
        return 0

    col_list = ", ".join(args.columns)
    buf = io.BytesIO()
    df.select(args.columns).write_csv(buf, separator="\t", null_value="\\N", include_header=False)
    buf.seek(0)

    conn = psycopg2.connect(args.database_url)
    try:
        with conn.cursor() as cur:
            cur.copy_expert(
                f"COPY {args.partition} ({col_list}) FROM STDIN"
                f" WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N')",
                buf,
            )
            inserted = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    with args.counter_lock:
        args.total_counter[0] += inserted
        running_total = args.total_counter[0]

    log.info(
        "loader shard %d/%d tld=%s rows=%d total=%d",
        args.shard_idx, args.total_shards, args.tld, inserted, running_total,
    )
    return inserted


def _parallel_load_shards(
    *,
    database_url: str,
    storage: R2Storage,
    keys: list[str],
    partition: str,
    columns: list[str],
    added_day: int,
    tld: str,
) -> int:
    """Load all shards into partition using a thread pool. Returns total rows loaded."""
    if not keys:
        return 0

    lock = threading.Lock()
    counter: list[int] = [0]
    total = len(keys)

    with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as pool:
        futures = [
            pool.submit(
                _load_shard_worker,
                _ShardArgs(
                    database_url=database_url,
                    storage=storage,
                    key=key,
                    partition=partition,
                    columns=columns,
                    added_day=added_day,
                    shard_idx=i,
                    total_shards=total,
                    tld=tld,
                    counter_lock=lock,
                    total_counter=counter,
                ),
            )
            for i, key in enumerate(keys, 1)
        ]
        for fut in as_completed(futures):
            fut.result()  # re-raises any worker exception immediately

    return counter[0]


def load_delta(
    *,
    database_url: str,
    storage: R2Storage,
    layout: Layout,
    source: str,
    tld: str,
    snapshot_date: date | str,
) -> dict:
    """Load a single (source, tld, snapshot_date) delta into PostgreSQL.

    Returns dict with keys: added_loaded, removed_loaded, status.
    """
    if isinstance(snapshot_date, date):
        snap_str = snapshot_date.isoformat()
    else:
        snap_str = snapshot_date
    added_day = _date_to_int(snap_str)

    delta_key = layout.delta_key(source, tld, snap_str)
    delta_removed_key = layout.delta_removed_key(source, tld, snap_str)
    delta_prefix = layout.delta_tld_date_prefix("delta", source, tld, snap_str)
    delta_removed_prefix = layout.delta_tld_date_prefix("delta_removed", source, tld, snap_str)

    t_discover = perf_counter()
    delta_keys = _list_parquet_keys(storage, delta_prefix, delta_key)
    removed_keys = _list_parquet_keys(storage, delta_removed_prefix, delta_removed_key)
    discover_seconds = perf_counter() - t_discover

    log.info(
        "loader source=%s tld=%s snapshot=%s added_files=%d removed_files=%d workers=%d",
        source, tld, snap_str, len(delta_keys), len(removed_keys), _PARALLEL_WORKERS,
    )

    domain_partition = _partition_name("domain", tld)
    removed_partition = _partition_name("domain_removed", tld)

    conn = psycopg2.connect(database_url)
    domain_detached = False
    removed_detached = False
    try:
        t_partition = perf_counter()
        _ensure_partition(conn, tld)
        partition_seconds = perf_counter() - t_partition

        # Detach so partition indexes become standalone and can be dropped/rebuilt
        # independently without affecting sibling partitions.
        _detach_partition(conn, "domain", domain_partition, tld)
        domain_detached = True
        _detach_partition(conn, "domain_removed", removed_partition, tld)
        removed_detached = True

        domain_index_ddls = _drop_standalone_indexes(conn, domain_partition)
        removed_index_ddls = _drop_standalone_indexes(conn, removed_partition)
    finally:
        conn.close()

    # Parallel shard loading — each worker uses its own connection
    t_load_added = perf_counter()
    try:
        added_loaded = _parallel_load_shards(
            database_url=database_url,
            storage=storage,
            keys=delta_keys,
            partition=domain_partition,
            columns=["name", "tld", "label", "added_day"],
            added_day=added_day,
            tld=tld,
        )
    except Exception:
        # Re-attach before propagating so the DB stays consistent
        _safe_reattach(database_url, domain_partition, "domain", tld, domain_detached)
        _safe_reattach(database_url, removed_partition, "domain_removed", tld, removed_detached)
        raise
    load_added_seconds = perf_counter() - t_load_added
    log.info("loader inserted domain tld=%s added=%d in %.1fs", tld, added_loaded, load_added_seconds)

    t_load_removed = perf_counter()
    try:
        removed_loaded = _parallel_load_shards(
            database_url=database_url,
            storage=storage,
            keys=removed_keys,
            partition=removed_partition,
            columns=["name", "tld", "removed_day"],
            added_day=added_day,
            tld=tld,
        )
    except Exception:
        _safe_reattach(database_url, domain_partition, "domain", tld, domain_detached)
        _safe_reattach(database_url, removed_partition, "domain_removed", tld, removed_detached)
        raise
    load_removed_seconds = perf_counter() - t_load_removed
    log.info("loader inserted domain_removed tld=%s removed=%d in %.1fs", tld, removed_loaded, load_removed_seconds)

    # Rebuild indexes and re-attach
    conn = psycopg2.connect(database_url)
    try:
        t_index = perf_counter()
        _rebuild_indexes(conn, domain_index_ddls, domain_partition)
        _rebuild_indexes(conn, removed_index_ddls, removed_partition)
        index_seconds = perf_counter() - t_index

        _attach_partition(conn, "domain", domain_partition, tld)
        domain_detached = False
        _attach_partition(conn, "domain_removed", removed_partition, tld)
        removed_detached = False
    finally:
        conn.close()

    return {
        "added_loaded": added_loaded,
        "removed_loaded": removed_loaded,
        "status": "ok",
        "snapshot_date": snap_str,
        "timings": {
            "discover_seconds": round(discover_seconds, 3),
            "ensure_partition_seconds": round(partition_seconds, 3),
            "load_added_seconds": round(load_added_seconds, 3),
            "load_removed_seconds": round(load_removed_seconds, 3),
            "index_rebuild_seconds": round(index_seconds, 3),
            "total_seconds": round(
                discover_seconds + partition_seconds + load_added_seconds
                + load_removed_seconds + index_seconds, 3
            ),
        },
    }


def _safe_reattach(database_url: str, partition: str, parent: str, tld: str, was_detached: bool) -> None:
    if not was_detached:
        return
    try:
        conn = psycopg2.connect(database_url)
        try:
            _attach_partition(conn, parent, partition, tld)
        finally:
            conn.close()
    except Exception as e:
        log.error("loader failed to re-attach %s to %s: %s", partition, parent, e)


def _read_parquet_or_empty(storage: R2Storage, key: str, required_columns: list[str]) -> pl.DataFrame:
    if not storage.key_exists(key):
        return pl.DataFrame({c: pl.Series([], dtype=pl.Utf8) for c in required_columns})
    raw = storage.get_bytes(key)
    df = pl.read_parquet(io.BytesIO(raw))
    for c in required_columns:
        if c not in df.columns:
            df = df.with_columns(pl.lit(None).cast(pl.Utf8).alias(c))
    return df.select(required_columns)


def _list_parquet_keys(storage: R2Storage, prefix: str, fallback_key: str) -> list[str]:
    keys = [key for key in storage.list_keys(prefix) if key.endswith(".parquet")]
    if keys:
        return sorted(keys)
    if storage.key_exists(fallback_key):
        return [fallback_key]
    return []
