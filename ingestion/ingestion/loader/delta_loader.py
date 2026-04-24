"""PostgreSQL bulk loader — reads delta Parquet files from R2 and loads into domain / domain_removed tables.

Strategy:
  1. Read delta Parquet(s) from R2 for the given source + tld + snapshot_date.
  2. Convert snapshot_date string → added_day INTEGER (YYYYMMDD).
  3. COPY into a TEMP TABLE.
  4. INSERT INTO domain ... ON CONFLICT DO NOTHING (append-only — no updates).
  5. Repeat for delta_removed → domain_removed.
  6. Ensure partition exists for the TLD (CREATE TABLE IF NOT EXISTS).
"""

from __future__ import annotations

import io
import logging
from datetime import date
from time import perf_counter

import psycopg2
import polars as pl

from ingestion.storage.layout import Layout
from ingestion.storage.r2 import R2Storage

log = logging.getLogger(__name__)


def _date_to_int(d: str) -> int:
    """Convert ISO date string '2026-04-23' → 20260423."""
    return int(d.replace("-", ""))


def _ensure_partition(conn, tld: str) -> None:
    """Create domain and domain_removed partitions for a TLD if they don't exist."""
    safe_tld = tld.replace("-", "_").replace(".", "_")
    with conn.cursor() as cur:
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS domain_{safe_tld}
            PARTITION OF domain FOR VALUES IN ('{tld}')
            """
        )
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS domain_removed_{safe_tld}
            PARTITION OF domain_removed FOR VALUES IN ('{tld}')
            """
        )
    conn.commit()


def _copy_load(conn, df: pl.DataFrame, table: str, columns: list[str]) -> int:
    """COPY df rows into a TEMP TABLE, then INSERT ... ON CONFLICT DO NOTHING."""
    if len(df) == 0:
        return 0

    temp = f"_tmp_ingestion_{table}"
    col_list = ", ".join(columns)
    placeholders = ", ".join(["%s"] * len(columns))

    with conn.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE IF NOT EXISTS {temp} (LIKE {table} INCLUDING DEFAULTS) ON COMMIT DROP")

        # Use COPY for bulk load
        buf = io.StringIO()
        for row in df.iter_rows():
            buf.write("\t".join(str(v) if v is not None else "\\N" for v in row) + "\n")
        buf.seek(0)
        cur.copy_from(buf, temp, columns=columns, null="\\N")

        cur.execute(
            f"""
            INSERT INTO {table} ({col_list})
            SELECT {col_list} FROM {temp}
            ON CONFLICT DO NOTHING
            """
        )
        inserted = cur.rowcount

    conn.commit()
    return inserted


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

    discover_started_at = perf_counter()
    delta_keys = _list_parquet_keys(storage, delta_prefix, delta_key)
    removed_keys = _list_parquet_keys(storage, delta_removed_prefix, delta_removed_key)
    discover_seconds = perf_counter() - discover_started_at

    log.info(
        "loader source=%s tld=%s snapshot=%s added_files=%d removed_files=%d",
        source, tld, snap_str, len(delta_keys), len(removed_keys),
    )

    conn = psycopg2.connect(database_url)
    try:
        partition_started_at = perf_counter()
        _ensure_partition(conn, tld)
        partition_seconds = perf_counter() - partition_started_at

        # Prepare added frame — inject added_day from snapshot_date
        added_loaded = 0
        added_read_seconds = 0.0
        added_load_seconds = 0.0
        for key in delta_keys:
            added_read_started_at = perf_counter()
            delta_df = _read_parquet_or_empty(storage, key, ["name", "tld", "label"])
            added_read_seconds += perf_counter() - added_read_started_at
            if len(delta_df) == 0:
                continue
            load_df = delta_df.select(["name", "tld", "label"]).with_columns(
                pl.lit(added_day).cast(pl.Int32).alias("added_day")
            )
            added_load_started_at = perf_counter()
            added_loaded += _copy_load(conn, load_df, "domain", ["name", "tld", "label", "added_day"])
            added_load_seconds += perf_counter() - added_load_started_at
        log.info("loader inserted domain tld=%s added=%d", tld, added_loaded)

        removed_loaded = 0
        removed_read_seconds = 0.0
        removed_load_seconds = 0.0
        for key in removed_keys:
            removed_read_started_at = perf_counter()
            removed_df = _read_parquet_or_empty(storage, key, ["name", "tld"])
            removed_read_seconds += perf_counter() - removed_read_started_at
            if len(removed_df) == 0:
                continue
            rem_df = removed_df.select(["name", "tld"]).with_columns(
                pl.lit(added_day).cast(pl.Int32).alias("removed_day")
            )
            removed_load_started_at = perf_counter()
            removed_loaded += _copy_load(conn, rem_df, "domain_removed", ["name", "tld", "removed_day"])
            removed_load_seconds += perf_counter() - removed_load_started_at
        log.info("loader inserted domain_removed tld=%s removed=%d", tld, removed_loaded)

    finally:
        conn.close()

    timings = {
        "discover_delta_seconds": round(discover_seconds, 3),
        "read_added_delta_seconds": round(added_read_seconds, 3),
        "read_removed_delta_seconds": round(removed_read_seconds, 3),
        "ensure_partition_seconds": round(partition_seconds, 3),
        "load_added_seconds": round(added_load_seconds, 3),
        "load_removed_seconds": round(removed_load_seconds, 3),
        "total_seconds": round(
            discover_seconds
            + added_read_seconds
            + removed_read_seconds
            + partition_seconds
            + added_load_seconds
            + removed_load_seconds,
            3,
        ),
    }
    return {
        "added_loaded": added_loaded,
        "removed_loaded": removed_loaded,
        "status": "ok",
        "snapshot_date": snap_str,
        "timings": timings,
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
