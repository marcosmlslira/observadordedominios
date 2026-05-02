"""Write `ingestion_run` records to PostgreSQL via psycopg2.

No backend imports — this module is safe to use from Databricks notebooks
and the standalone ingestion worker.

Column mapping (RunStats → ingestion_run):
  RunStats.added_count    → domains_inserted
  RunStats.removed_count  → domains_deleted
  RunStats.snapshot_count → domains_seen
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import psycopg2

if TYPE_CHECKING:
    from ingestion.core.types import RunStats

log = logging.getLogger(__name__)

_INSERT_SQL = """
INSERT INTO ingestion_run (
    id, source, tld, status, phase,
    started_at, finished_at,
    domains_seen, domains_inserted, domains_reactivated, domains_deleted,
    reason_code,
    error_message,
    created_at, updated_at
) VALUES (
    %s, %s, %s, %s, %s,
    %s, %s,
    %s, %s, %s, %s,
    %s,
    %s,
    %s, %s
)
"""

_UPDATE_SQL = """
UPDATE ingestion_run SET
    status             = %s,
    finished_at        = %s,
    domains_seen       = %s,
    domains_inserted   = %s,
    domains_reactivated = %s,
    domains_deleted    = %s,
    reason_code        = %s,
    error_message      = %s,
    snapshot_date      = %s,
    updated_at         = %s
WHERE id = %s
"""

_TOUCH_SQL = """
UPDATE ingestion_run
SET updated_at = %s
WHERE id = %s
"""


def create_run(
    db_url: str,
    source: str,
    tld: str,
    *,
    phase: str = "full",
    started_at: datetime | None = None,
) -> str:
    """Insert a new `ingestion_run` row with status='running'. Returns run_id (UUID str).

    phase: 'full' (local path, covers R2+PG) | 'r2' (Databricks job) | 'pg' (PG load only)
    """
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    started = started_at or now

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                _INSERT_SQL,
                (run_id, source, tld, "running", phase, started, None, 0, 0, 0, 0, None, None, now, now),
            )
        conn.commit()
    finally:
        conn.close()

    log.debug("run_recorder create run_id=%s source=%s tld=%s phase=%s", run_id, source, tld, phase)
    return run_id


def finish_run(
    db_url: str,
    run_id: str,
    *,
    status: str,
    domains_inserted: int = 0,
    domains_deleted: int = 0,
    domains_seen: int = 0,
    domains_reactivated: int = 0,
    reason_code: str | None = None,
    error_message: str | None = None,
    finished_at: datetime | None = None,
    snapshot_date: str | None = None,
) -> None:
    """Update an existing `ingestion_run` to a terminal state (success | failed)."""
    now = datetime.now(timezone.utc)
    finished = finished_at or now

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                _UPDATE_SQL,
                (
                    status,
                    finished,
                    domains_seen,
                    domains_inserted,
                    domains_reactivated,
                    domains_deleted,
                    reason_code,
                    error_message,
                    snapshot_date,
                    now,
                    run_id,
                ),
            )
        conn.commit()
    finally:
        conn.close()

    log.debug("run_recorder finish run_id=%s status=%s", run_id, status)


def record_stats(db_url: str, stats: "RunStats") -> None:
    """Convenience: create + immediately finish a run from a completed RunStats object."""
    run_id = create_run(
        db_url,
        source=stats.run_key.source.value if hasattr(stats.run_key.source, "value") else str(stats.run_key.source),
        tld=stats.run_key.tld,
    )
    finish_run(
        db_url,
        run_id,
        status="success" if stats.status == "ok" else "failed",
        reason_code="success" if stats.status == "ok" else "unexpected_error",
        domains_inserted=stats.added_count,
        domains_deleted=stats.removed_count,
        domains_seen=stats.snapshot_count,
        error_message=stats.error_message or None,
    )


def touch_run(db_url: str, run_id: str) -> None:
    """Heartbeat a running row to keep updated_at fresh during long steps."""
    now = datetime.now(timezone.utc)
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(_TOUCH_SQL, (now, run_id))
        conn.commit()
    finally:
        conn.close()


# ── Cycle-level tracking ──────────────────────────────────────────────────────


_CYCLE_INSERT_SQL = """
INSERT INTO ingestion_cycle (
    cycle_id, started_at, status, triggered_by, tld_total
) VALUES (
    gen_random_uuid(), %s, 'running', %s, %s
)
RETURNING cycle_id::text
"""

_CYCLE_UPDATE_SQL = """
UPDATE ingestion_cycle SET
    status            = %s,
    finished_at       = %s,
    tld_success       = %s,
    tld_failed        = %s,
    tld_skipped       = %s,
    tld_load_only     = %s,
    last_heartbeat_at = %s
WHERE cycle_id = %s::uuid
"""

_CYCLE_HEARTBEAT_SQL = """
UPDATE ingestion_cycle
SET last_heartbeat_at = %s
WHERE cycle_id = %s::uuid
"""


def open_cycle(
    db_url: str,
    *,
    triggered_by: str = "cron",
    tld_total: int | None = None,
    started_at: datetime | None = None,
) -> str:
    """Insert a new ingestion_cycle row with status='running'. Returns cycle_id (UUID str)."""
    now = started_at or datetime.now(timezone.utc)
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(_CYCLE_INSERT_SQL, (now, triggered_by, tld_total))
            cycle_id = cur.fetchone()[0]
        conn.commit()
    finally:
        conn.close()
    log.debug("run_recorder open_cycle cycle_id=%s triggered_by=%s", cycle_id, triggered_by)
    return cycle_id


def close_cycle(
    db_url: str,
    cycle_id: str,
    *,
    status: str,
    tld_success: int = 0,
    tld_failed: int = 0,
    tld_skipped: int = 0,
    tld_load_only: int = 0,
    finished_at: datetime | None = None,
) -> None:
    """Close an ingestion_cycle row with a terminal status."""
    now = datetime.now(timezone.utc)
    finished = finished_at or now
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                _CYCLE_UPDATE_SQL,
                (status, finished, tld_success, tld_failed, tld_skipped, tld_load_only, now, cycle_id),
            )
        conn.commit()
    finally:
        conn.close()
    log.debug("run_recorder close_cycle cycle_id=%s status=%s", cycle_id, status)


def heartbeat_cycle(db_url: str, cycle_id: str) -> None:
    """Refresh last_heartbeat_at on a running cycle row."""
    now = datetime.now(timezone.utc)
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(_CYCLE_HEARTBEAT_SQL, (now, cycle_id))
        conn.commit()
    finally:
        conn.close()


def get_last_cycle(db_url: str) -> dict | None:
    """Return the most recent ingestion_cycle row as a dict, or None."""
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    cycle_id::text, started_at, finished_at, status, triggered_by,
                    tld_total, tld_success, tld_failed, tld_skipped, tld_load_only,
                    last_heartbeat_at
                FROM ingestion_cycle
                ORDER BY started_at DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            if row is None:
                return None
            cols = [
                "cycle_id", "started_at", "finished_at", "status", "triggered_by",
                "tld_total", "tld_success", "tld_failed", "tld_skipped", "tld_load_only",
                "last_heartbeat_at",
            ]
            return {k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in zip(cols, row)}
    finally:
        conn.close()


def recover_stale_running_cycles(db_url: str, *, stale_after_minutes: int) -> int:
    """Close orphaned running cycles via heartbeat staleness."""
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ingestion_cycle
                SET
                    status = 'interrupted',
                    finished_at = now(),
                    last_heartbeat_at = now()
                WHERE status = 'running'
                  AND COALESCE(last_heartbeat_at, started_at) < (now() - (%s || ' minutes')::interval)
                """,
                (stale_after_minutes,),
            )
            affected = cur.rowcount
        conn.commit()
        return affected
    finally:
        conn.close()


def count_enabled_tlds(db_url: str) -> int:
    """Return total number of enabled TLDs across all sources in ingestion_tld_policy."""
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM ingestion_tld_policy WHERE is_enabled = true"
            )
            row = cur.fetchone()
            return row[0] if row else 0
    finally:
        conn.close()


def czds_ran_today(db_url: str) -> bool:
    """Return True if at least one CZDS run completed successfully today (UTC)."""
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM ingestion_run
                WHERE source = 'czds'
                  AND status = 'success'
                  AND finished_at >= (NOW() AT TIME ZONE 'UTC')::date
                LIMIT 1
                """
            )
            return cur.fetchone() is not None
    finally:
        conn.close()


# ── ingestion_cycle_tld helpers ──────────────────────────────────────────────


def plan_cycle_tlds(
    db_url: str,
    cycle_id: str,
    source: str,
    tlds: list[dict],
) -> None:
    """Insert one 'planned' row per TLD at cycle start.

    Each item in `tlds` must have: tld (str), priority (int|None),
    planned_position (int), planned_phase (str).
    Uses ON CONFLICT DO NOTHING so retries are safe.
    """
    if not tlds:
        return
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO ingestion_cycle_tld
                    (cycle_id, source, tld, priority, planned_position,
                     planned_phase, execution_status)
                VALUES (%s, %s, %s, %s, %s, %s, 'planned')
                ON CONFLICT (cycle_id, source, tld) DO NOTHING
                """,
                [
                    (
                        cycle_id,
                        source,
                        t["tld"],
                        t.get("priority"),
                        t.get("planned_position"),
                        t.get("planned_phase", "full_run"),
                    )
                    for t in tlds
                ],
            )
        conn.commit()
    finally:
        conn.close()


def update_cycle_tld(
    db_url: str,
    cycle_id: str,
    source: str,
    tld: str,
    *,
    execution_status: str,
    reason_code: str | None = None,
    error_message: str | None = None,
    snapshot_date: str | None = None,
    r2_marker_date: str | None = None,
    r2_run_id: str | None = None,
    pg_run_id: str | None = None,
    databricks_run_id: int | None = None,
    databricks_run_url: str | None = None,
    databricks_result_state: str | None = None,
    started_at: datetime | None = None,
) -> None:
    """Update an existing cycle_tld row to a terminal (or running) status."""
    conn = psycopg2.connect(db_url)
    now = datetime.now(timezone.utc)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ingestion_cycle_tld
                SET
                    execution_status        = %s,
                    reason_code             = %s,
                    error_message           = %s,
                    snapshot_date           = %s,
                    r2_marker_date          = %s,
                    r2_run_id               = COALESCE(%s::uuid, r2_run_id),
                    pg_run_id               = COALESCE(%s::uuid, pg_run_id),
                    databricks_run_id       = COALESCE(%s, databricks_run_id),
                    databricks_run_url      = COALESCE(%s, databricks_run_url),
                    databricks_result_state = COALESCE(%s, databricks_result_state),
                    started_at              = COALESCE(%s, started_at),
                    finished_at             = CASE
                        WHEN %s NOT IN ('planned', 'running') THEN %s
                        ELSE finished_at END,
                    duration_seconds        = CASE
                        WHEN %s NOT IN ('planned', 'running') AND started_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (%s - COALESCE(%s, started_at)))::INT
                        ELSE duration_seconds END
                WHERE cycle_id = %s::uuid
                  AND source   = %s
                  AND tld      = %s
                """,
                (
                    execution_status,
                    reason_code,
                    error_message,
                    snapshot_date,
                    r2_marker_date,
                    r2_run_id,
                    pg_run_id,
                    databricks_run_id,
                    databricks_run_url,
                    databricks_result_state,
                    started_at,
                    # finished_at CASE
                    execution_status, now,
                    # duration CASE
                    execution_status, now, started_at,
                    # WHERE
                    cycle_id, source, tld,
                ),
            )
        conn.commit()
    finally:
        conn.close()


def close_cycle_tld_pending(
    db_url: str,
    cycle_id: str,
    *,
    reason_code: str = "not_reached",
    source: str | None = None,
) -> int:
    """Mark 'planned'/'running' cycle_tld rows as 'not_reached'.

    Pass `source` to restrict to a single source (e.g. when only openintel crashed).
    Returns count of rows updated.
    """
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            if source:
                cur.execute(
                    """
                    UPDATE ingestion_cycle_tld
                    SET execution_status = 'not_reached',
                        reason_code      = %s,
                        finished_at      = now()
                    WHERE cycle_id = %s::uuid
                      AND source   = %s
                      AND execution_status IN ('planned', 'running')
                    """,
                    (reason_code, cycle_id, source),
                )
            else:
                cur.execute(
                    """
                    UPDATE ingestion_cycle_tld
                    SET execution_status = 'not_reached',
                        reason_code      = %s,
                        finished_at      = now()
                    WHERE cycle_id = %s::uuid
                      AND execution_status IN ('planned', 'running')
                    """,
                    (reason_code, cycle_id),
                )
            affected = cur.rowcount
        conn.commit()
        return affected
    finally:
        conn.close()


def recover_stale_running_runs(
    db_url: str,
    source: str,
    *,
    stale_after_minutes: int,
) -> int:
    """Close orphaned running runs for source using updated_at heartbeat staleness.

    The threshold is per-TLD when ingestion_tld_policy.stale_timeout_seconds is
    populated for the (source, tld) pair, otherwise falls back to the global
    *stale_after_minutes* (multiplied by 60 to compare against seconds).

    Large CZDS zones (xyz, info, org) routinely take more than 60 minutes to
    finish loading; without a per-TLD override the watchdog used to kill them
    while they were still making progress.
    """
    default_seconds = stale_after_minutes * 60
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ingestion_run AS r
                SET
                    status = 'failed',
                    reason_code = 'stale_recovered',
                    error_message = COALESCE(
                        NULLIF(error_message, ''),
                        'Run recovered automatically after stale timeout'
                    ),
                    finished_at = now(),
                    updated_at = now()
                WHERE r.source = %s
                  AND r.status = 'running'
                  AND r.updated_at < (
                      now() - (
                          COALESCE(
                              (
                                  SELECT p.stale_timeout_seconds
                                    FROM ingestion_tld_policy p
                                   WHERE p.source = r.source AND p.tld = r.tld
                              ),
                              %s
                          ) || ' seconds'
                      )::interval
                  )
                """,
                (source, default_seconds),
            )
            affected = cur.rowcount
        conn.commit()
        return affected
    finally:
        conn.close()


def recover_conflicting_running_runs(
    db_url: str,
    source: str,
    *,
    reason_code: str = "source_restarted",
    error_message: str = "Run closed automatically because a new source cycle started",
) -> int:
    """Close all still-running rows for *source* before a fresh source cycle starts.

    The ingestion worker processes one source at a time, so a new `run_cycle(source)`
    should never overlap with older `ingestion_run` rows from the same source. If the
    worker was restarted mid-run, those rows become stale immediately even if their
    generic timeout has not elapsed yet.
    """
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE ingestion_run
                SET
                    status = 'failed',
                    reason_code = %s,
                    error_message = COALESCE(NULLIF(error_message, ''), %s),
                    finished_at = now(),
                    updated_at = now()
                WHERE source = %s
                  AND status = 'running'
                """,
                (reason_code, error_message, source),
            )
            affected = cur.rowcount
        conn.commit()
        return affected
    finally:
        conn.close()
