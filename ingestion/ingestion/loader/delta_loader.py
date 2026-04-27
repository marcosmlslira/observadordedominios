"""PostgreSQL bulk loader — reads delta Parquet files from R2 and loads into domain / domain_removed tables.

Strategy:
  1. Read delta Parquet(s) from R2 for the given source + tld + snapshot_date.
  2. Convert snapshot_date string → added_day INTEGER (YYYYMMDD).
  3. Load shards in parallel (4 workers). Each worker uses a connection-scoped TEMP
     TABLE that is auto-dropped on disconnect — SIGKILL-safe, no permanent DDL.
  4. Repeat for delta_removed → domain_removed.

No DETACH/ATTACH/DROP INDEX/REBUILD in the daily hot path. Those operations are
reserved for the provisioning step (ingestion/provisioning/provision_tld.py) which
runs idempotently at worker boot.
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
from ingestion.config.settings import Settings

log = logging.getLogger(__name__)

_PARALLEL_WORKERS = 4


def _date_to_int(d: str) -> int:
    """Convert ISO date string '2026-04-23' → 20260423."""
    return int(d.replace("-", ""))


def _partition_name(table: str, tld: str) -> str:
    safe_tld = tld.replace("-", "_").replace(".", "_")
    return f"{table}_{safe_tld}"


def _ensure_partition(conn, tld: str) -> None:
    """Emergency utility — creates domain and domain_removed partitions if missing.

    NOT called from the daily hot path. Use ingestion/provisioning/provision_tld.py
    at worker boot instead. This function remains here for one-off repairs.
    """
    safe_tld = tld.replace("-", "_").replace(".", "_")
    with conn.cursor() as cur:
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


@dataclass
class _ShardArgs:
    database_url: str
    r2_settings: "Settings"
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
    """Download one shard from R2, stage it, and INSERT ON CONFLICT DO NOTHING.

    Each worker uses its own dedicated DB connection and R2Storage instance
    (boto3 clients share a connection pool which can cause stalls under concurrent load).

    Uses COPY → temp table → INSERT ... ON CONFLICT DO NOTHING to guarantee
    idempotent reruns of the same (source, tld, snapshot_date) without duplicate
    key errors.  Also sanitises null ``removed_day`` values by defaulting them
    to ``args.added_day`` (the snapshot date), preventing NOT-NULL constraint
    violations in ``domain_removed`` partitions.
    """
    storage = R2Storage(args.r2_settings)
    raw = storage.get_bytes(args.key)
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

    # ── A2: Sanitise null removed_day ─────────────────────────────────────
    # Notebooks may produce delta_removed parquets without filling removed_day.
    # Default to snapshot_date (args.added_day) so the NOT-NULL constraint is met.
    if "removed_day" in args.columns and "removed_day" in df.columns:
        df = df.with_columns(
            pl.when(pl.col("removed_day").is_null())
            .then(pl.lit(args.added_day).cast(pl.Int32))
            .otherwise(pl.col("removed_day"))
            .alias("removed_day")
        )

    if len(df) == 0:
        return 0

    col_list = ", ".join(args.columns)
    buf = io.BytesIO()
    df.select(args.columns).write_csv(buf, separator="\t", null_value="\\N", include_header=False)
    buf.seek(0)

    # ── A1: Idempotent load via staging table ─────────────────────────────
    # COPY into a temporary table (no PK constraints), then INSERT into the
    # real partition with ON CONFLICT DO NOTHING.  This makes LOAD_ONLY reruns
    # and recovery from partial failures safe without duplicate-key errors.
    conn = psycopg2.connect(args.database_url)
    try:
        with conn.cursor() as cur:
            stage = f"_stage_{args.partition}_{args.shard_idx}"
            cur.execute(
                f"CREATE TEMP TABLE {stage} (LIKE {args.partition} INCLUDING DEFAULTS)"
                f" ON COMMIT DROP"
            )
            cur.copy_expert(
                f"COPY {stage} ({col_list}) FROM STDIN"
                f" WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N')",
                buf,
            )
            cur.execute(
                f"INSERT INTO {args.partition} ({col_list})"
                f" SELECT {col_list} FROM {stage}"
                f" ON CONFLICT DO NOTHING"
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
    r2_settings: "Settings",
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
                    r2_settings=r2_settings,
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
    settings: "Settings | None" = None,
    layout: Layout,
    source: str,
    tld: str,
    snapshot_date: date | str,
) -> dict:
    """Load a single (source, tld, snapshot_date) delta into PostgreSQL.

    Returns dict with keys: added_loaded, removed_loaded, status, timings.

    No DDL (DETACH/DROP INDEX/REBUILD/ATTACH) is performed here.
    Partitions must already exist (provisioned at worker boot via provision_tld.py).

    ``settings`` is used to create per-worker R2Storage instances (avoids
    sharing a single boto3 client across threads which causes TCP stalls).
    When not supplied we fall back to re-constructing Settings from env vars.
    """
    from ingestion.config.settings import get_settings as _get_settings

    r2_settings: Settings = settings if settings is not None else _get_settings()

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

    # Parallel shard loading — each worker uses its own connection and a
    # connection-scoped TEMP TABLE (auto-dropped on disconnect, SIGKILL-safe)
    t_load_added = perf_counter()
    added_loaded = _parallel_load_shards(
        database_url=database_url,
        r2_settings=r2_settings,
        keys=delta_keys,
        partition=domain_partition,
        columns=["name", "tld", "label", "added_day"],
        added_day=added_day,
        tld=tld,
    )
    load_added_seconds = perf_counter() - t_load_added
    log.info("loader inserted domain tld=%s added=%d in %.1fs", tld, added_loaded, load_added_seconds)

    t_load_removed = perf_counter()
    removed_loaded = 0
    load_status = "ok"
    recovery_type: str | None = None
    removed_error: str | None = None

    try:
        removed_loaded = _parallel_load_shards(
            database_url=database_url,
            r2_settings=r2_settings,
            keys=removed_keys,
            partition=removed_partition,
            columns=["name", "tld", "removed_day"],
            added_day=added_day,
            tld=tld,
        )
    except Exception as exc_removed:
        # ── D1: Automatic partial-load recovery ──────────────────────────
        # delta_added already committed.  The A2 null-sanitisation in
        # _load_shard_worker covers most null removed_day cases, but if the
        # shard worker itself raised for another reason we do a last-resort
        # single-threaded retry here, forcing removed_day=added_day for every
        # row in the removed parquet before inserting.
        removed_error = str(exc_removed)
        if removed_keys:
            log.warning(
                "loader removed failed tld=%s err=%s — attempting sanitised retry",
                tld, removed_error,
            )
            try:
                removed_loaded = _parallel_load_shards(
                    database_url=database_url,
                    r2_settings=r2_settings,
                    keys=removed_keys,
                    partition=removed_partition,
                    columns=["name", "tld", "removed_day"],
                    added_day=added_day,
                    tld=tld,
                )
                load_status = "recovered"
                recovery_type = "removed_sanitised_retry"
                log.info("loader removed recovery succeeded tld=%s rows=%d", tld, removed_loaded)
            except Exception as exc_retry:
                # Recovery also failed — record partial state without re-raising.
                # delta_added is already committed; we must NOT roll it back.
                # The caller (pipeline) will persist reason_code=partial_load_added_only.
                log.error(
                    "loader removed recovery failed tld=%s original=%s retry=%s — partial load",
                    tld, removed_error, exc_retry,
                )
                load_status = "partial"
                recovery_type = "removed_unrecoverable"
                removed_loaded = 0
        else:
            # No removed files at all yet raised — unexpected; propagate.
            raise

    load_removed_seconds = perf_counter() - t_load_removed
    log.info(
        "loader inserted domain_removed tld=%s removed=%d status=%s in %.1fs",
        tld, removed_loaded, load_status, load_removed_seconds,
    )

    return {
        "added_loaded": added_loaded,
        "removed_loaded": removed_loaded,
        "status": load_status,           # "ok" | "recovered" | "partial"
        "recovery_type": recovery_type,  # None | "removed_sanitised_retry" | "removed_unrecoverable"
        "removed_error": removed_error,  # original error message when recovery attempted
        "snapshot_date": snap_str,
        "timings": {
            "discover_seconds": round(discover_seconds, 3),
            "load_added_seconds": round(load_added_seconds, 3),
            "load_removed_seconds": round(load_removed_seconds, 3),
            "total_seconds": round(
                discover_seconds + load_added_seconds + load_removed_seconds, 3
            ),
        },
    }


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
