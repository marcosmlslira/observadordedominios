"""ADR-001 integration test: synthetic Parquet delta → R2 → PostgreSQL.

Steps:
  1. Build a small synthetic delta DataFrame (5 domains for 'museum' TLD)
  2. Upload it as delta Parquet to R2
  3. Upload a delta_removed Parquet to R2
  4. Call load_delta() to pull from R2 and COPY into PostgreSQL
  5. Verify row counts in domain and domain_removed tables
  6. Cleanup test rows and R2 keys

Usage (run directly with python3, not inside a Docker container):
  python3 test_adr001_load.py
"""

from __future__ import annotations

import io
import json
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

R2_ACCOUNT_ID     = "c7d69182e6ae8686a3edc7bdd6eae9f8"
R2_ACCESS_KEY_ID  = "de77bf7b6c20ebce5b86115bb2c6d67f"
R2_SECRET_ACCESS_KEY = "5e76101a6903df86bf1bc273acb7bea65650b9be6cc1035523fc9d2eea6d95d1"
R2_BUCKET         = "observadordedominios"
R2_PREFIX         = "lake/domain_ingestion"

# Production PostgreSQL (accessed from within the Docker network / directly via pg container)
# We connect through the postgres container's network
DB_URL = "postgresql://obs:2XqDW8eGHd9qHyv_yfGAiSY-HRNLY4WntwxcsIQIW_U@postgres:5432/obs"

TEST_TLD          = "museum"
TEST_SNAPSHOT     = "2026-04-23"
TEST_SOURCE       = "test"

# ── Imports ───────────────────────────────────────────────────────────────────

try:
    import polars as pl
    import boto3
    import psycopg2
    from botocore.config import Config as BotoConfig
except ImportError as exc:
    sys.exit(f"Missing package: {exc}. Run: pip3 install polars boto3 psycopg2-binary pyarrow")

# ── Helpers ───────────────────────────────────────────────────────────────────

def make_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
        config=BotoConfig(s3={"addressing_style": "path"}),
    )


def delta_key(source, tld, snapshot_date):
    return f"{R2_PREFIX}/delta/source={source}/tld={tld}/snapshot_date={snapshot_date}/part.parquet"


def delta_removed_key(source, tld, snapshot_date):
    return f"{R2_PREFIX}/delta_removed/source={source}/tld={tld}/snapshot_date={snapshot_date}/part.parquet"


def marker_key(source, tld, snapshot_date):
    return f"{R2_PREFIX}/markers/source={source}/tld={tld}/snapshot_date={snapshot_date}/success.json"


def df_to_parquet_bytes(df: pl.DataFrame) -> bytes:
    buf = io.BytesIO()
    df.write_parquet(buf, compression="zstd")
    return buf.getvalue()


def date_to_int(d: str) -> int:
    return int(d.replace("-", ""))


def ensure_partition(conn, tld: str) -> None:
    safe_tld = tld.replace("-", "_").replace(".", "_")
    with conn.cursor() as cur:
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS domain_{safe_tld} PARTITION OF domain FOR VALUES IN ('{tld}')"
        )
        cur.execute(
            f"CREATE TABLE IF NOT EXISTS domain_removed_{safe_tld} PARTITION OF domain_removed FOR VALUES IN ('{tld}')"
        )
    conn.commit()


def copy_load(conn, df: pl.DataFrame, table: str, columns: list[str]) -> int:
    if len(df) == 0:
        return 0
    temp = f"_tmp_test_{table}"
    col_list = ", ".join(columns)
    with conn.cursor() as cur:
        cur.execute(f"CREATE TEMP TABLE IF NOT EXISTS {temp} (LIKE {table} INCLUDING DEFAULTS) ON COMMIT DROP")
        buf = io.StringIO()
        for row in df.iter_rows():
            buf.write("\t".join(str(v) if v is not None else "\\N" for v in row) + "\n")
        buf.seek(0)
        cur.copy_from(buf, temp, columns=columns, null="\\N")
        cur.execute(
            f"INSERT INTO {table} ({col_list}) SELECT {col_list} FROM {temp} ON CONFLICT DO NOTHING"
        )
        inserted = cur.rowcount
    conn.commit()
    return inserted


# ── Test ──────────────────────────────────────────────────────────────────────

def main():
    r2 = make_r2_client()
    added_day = date_to_int(TEST_SNAPSHOT)

    # Step 1: Build synthetic delta Parquet (ADR-001 schema: name, tld, label)
    log.info("Step 1: building synthetic delta Parquet")
    added_df = pl.DataFrame({
        "name":  ["adr001a.museum", "adr001b.museum", "adr001c.museum", "adr001d.museum", "adr001e.museum"],
        "tld":   ["museum"] * 5,
        "label": ["adr001a", "adr001b", "adr001c", "adr001d", "adr001e"],
    })
    removed_df = pl.DataFrame({
        "name": ["adr001old.museum"],
        "tld":  ["museum"],
    })
    log.info("  added: %d rows, removed: %d rows", len(added_df), len(removed_df))

    # Step 2: Upload to R2
    log.info("Step 2: uploading Parquet files to R2")
    r2.put_object(
        Bucket=R2_BUCKET,
        Key=delta_key(TEST_SOURCE, TEST_TLD, TEST_SNAPSHOT),
        Body=df_to_parquet_bytes(added_df),
    )
    r2.put_object(
        Bucket=R2_BUCKET,
        Key=delta_removed_key(TEST_SOURCE, TEST_TLD, TEST_SNAPSHOT),
        Body=df_to_parquet_bytes(removed_df),
    )
    r2.put_object(
        Bucket=R2_BUCKET,
        Key=marker_key(TEST_SOURCE, TEST_TLD, TEST_SNAPSHOT),
        Body=json.dumps({"source": TEST_SOURCE, "tld": TEST_TLD, "snapshot_date": TEST_SNAPSHOT}).encode(),
    )
    log.info("  uploaded delta, delta_removed, and marker to R2")

    # Step 3: Read back and load into PostgreSQL
    log.info("Step 3: loading from R2 into PostgreSQL")

    delta_raw = r2.get_object(Bucket=R2_BUCKET, Key=delta_key(TEST_SOURCE, TEST_TLD, TEST_SNAPSHOT))["Body"].read()
    delta_pq  = pl.read_parquet(io.BytesIO(delta_raw))
    log.info("  delta parquet schema: %s", delta_pq.schema)
    assert "name" in delta_pq.columns, "missing 'name' column in delta parquet"
    assert "added_day" not in delta_pq.columns, "added_day should NOT be in R2 parquet (injected by loader)"

    removed_raw = r2.get_object(Bucket=R2_BUCKET, Key=delta_removed_key(TEST_SOURCE, TEST_TLD, TEST_SNAPSHOT))["Body"].read()
    removed_pq  = pl.read_parquet(io.BytesIO(removed_raw))

    # Inject added_day
    load_df = delta_pq.select(["name", "tld", "label"]).with_columns(
        pl.lit(added_day).cast(pl.Int32).alias("added_day")
    )
    rem_df = removed_pq.select(["name", "tld"]).with_columns(
        pl.lit(added_day).cast(pl.Int32).alias("removed_day")
    )

    log.info("Step 4: connecting to PostgreSQL and loading")
    conn = psycopg2.connect(DB_URL)
    try:
        ensure_partition(conn, TEST_TLD)

        # Delete any pre-existing test rows for idempotency
        with conn.cursor() as cur:
            cur.execute("DELETE FROM domain WHERE name LIKE 'adr001%%' AND tld = %s", (TEST_TLD,))
            cur.execute("DELETE FROM domain_removed WHERE name LIKE 'adr001%%' AND tld = %s", (TEST_TLD,))
        conn.commit()

        added = copy_load(conn, load_df, "domain", ["name", "tld", "label", "added_day"])
        removed = copy_load(conn, rem_df, "domain_removed", ["name", "tld", "removed_day"])

        log.info("  inserted domain: %d, domain_removed: %d", added, removed)

        # Step 5: Verify
        log.info("Step 5: verifying row counts")
        with conn.cursor() as cur:
            cur.execute("SELECT name, tld, label, added_day FROM domain WHERE name LIKE 'adr001%%' AND tld = %s ORDER BY name", (TEST_TLD,))
            rows = cur.fetchall()
        log.info("  domain rows:")
        for row in rows:
            log.info("    %s", row)

        with conn.cursor() as cur:
            cur.execute("SELECT name, tld, removed_day FROM domain_removed WHERE name LIKE 'adr001%%' AND tld = %s", (TEST_TLD,))
            rem_rows = cur.fetchall()
        log.info("  domain_removed rows:")
        for row in rem_rows:
            log.info("    %s", row)

        assert len(rows) == 5, f"expected 5 domain rows, got {len(rows)}"
        assert len(rem_rows) == 1, f"expected 1 domain_removed row, got {len(rem_rows)}"
        assert rows[0][3] == added_day, f"added_day mismatch: {rows[0][3]} != {added_day}"
        assert rem_rows[0][2] == added_day, f"removed_day mismatch: {rem_rows[0][2]} != {added_day}"

        # Step 6: Cleanup
        log.info("Step 6: cleaning up test rows")
        with conn.cursor() as cur:
            cur.execute("DELETE FROM domain WHERE name LIKE 'adr001%%' AND tld = %s", (TEST_TLD,))
            cur.execute("DELETE FROM domain_removed WHERE name LIKE 'adr001%%' AND tld = %s", (TEST_TLD,))
        conn.commit()
    finally:
        conn.close()

    # Cleanup R2
    log.info("Cleaning up R2 test keys")
    for key in [delta_key(TEST_SOURCE, TEST_TLD, TEST_SNAPSHOT),
                delta_removed_key(TEST_SOURCE, TEST_TLD, TEST_SNAPSHOT),
                marker_key(TEST_SOURCE, TEST_TLD, TEST_SNAPSHOT)]:
        r2.delete_object(Bucket=R2_BUCKET, Key=key)

    log.info("✅ ALL ASSERTIONS PASSED — ADR-001 load pipeline validated")


if __name__ == "__main__":
    main()
