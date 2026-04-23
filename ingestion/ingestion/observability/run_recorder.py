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
    id, source, tld, status,
    started_at, finished_at,
    domains_seen, domains_inserted, domains_reactivated, domains_deleted,
    error_message,
    created_at, updated_at
) VALUES (
    %s, %s, %s, %s,
    %s, %s,
    %s, %s, %s, %s,
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
    error_message      = %s,
    updated_at         = %s
WHERE id = %s
"""


def create_run(
    db_url: str,
    source: str,
    tld: str,
    *,
    started_at: datetime | None = None,
) -> str:
    """Insert a new `ingestion_run` row with status='running'. Returns run_id (UUID str)."""
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    started = started_at or now

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                _INSERT_SQL,
                (run_id, source, tld, "running", started, None, 0, 0, 0, 0, None, now, now),
            )
        conn.commit()
    finally:
        conn.close()

    log.debug("run_recorder create run_id=%s source=%s tld=%s", run_id, source, tld)
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
    error_message: str | None = None,
    finished_at: datetime | None = None,
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
                    error_message,
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
        domains_inserted=stats.added_count,
        domains_deleted=stats.removed_count,
        domains_seen=stats.snapshot_count,
        error_message=stats.error_message or None,
    )
