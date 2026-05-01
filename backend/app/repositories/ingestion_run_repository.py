"""Repository for ingestion_run and ingestion_checkpoint.

Read-side helpers used by the admin API. The write-side (creating runs,
finishing them, updating progress, upserting checkpoints, recovering stale
runs) lives in the new ingestion package
(``ingestion/observability/run_recorder.py``), which talks to PostgreSQL
directly via psycopg2.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.ingestion_checkpoint import IngestionCheckpoint
from app.models.ingestion_run import IngestionRun


class IngestionRunRepository:
    """Read helpers for IngestionRun + IngestionCheckpoint, plus a stale-run
    recovery used by the API startup hook."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_run(self, run_id: uuid.UUID) -> IngestionRun | None:
        """Fetch a specific ingestion run."""
        return self.db.get(IngestionRun, run_id)

    def list_runs(
        self,
        limit: int = 20,
        offset: int = 0,
        source: str | None = None,
        status: str | None = None,
        tld: str | None = None,
        started_from: datetime | None = None,
        started_to: datetime | None = None,
    ) -> list[IngestionRun]:
        """List ingestion runs ordered by newest first, with optional filters."""
        query = self.db.query(IngestionRun)
        if source:
            query = query.filter(IngestionRun.source == source)
        if status:
            query = query.filter(IngestionRun.status == status)
        if tld:
            query = query.filter(IngestionRun.tld == tld)
        if started_from:
            query = query.filter(IngestionRun.started_at >= started_from)
        if started_to:
            query = query.filter(IngestionRun.started_at <= started_to)
        return (
            query.order_by(IngestionRun.started_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_today_runs_agg(self, source: str, today_start: datetime) -> dict:
        """Return aggregated counts of today's runs for a source without a row-count limit."""
        row = self.db.execute(
            text("""
                SELECT
                    count(*) FILTER (WHERE status = 'success') AS completed,
                    count(*) FILTER (WHERE status = 'failed')  AS failed,
                    count(*) FILTER (WHERE status = 'running') AS running,
                    min(started_at) AS cycle_started_at,
                    avg(EXTRACT(EPOCH FROM (finished_at - started_at)))
                        FILTER (WHERE status = 'success' AND finished_at IS NOT NULL) AS avg_duration_s,
                    (array_agg(tld) FILTER (WHERE status = 'running'))[1] AS current_tld
                FROM ingestion_run
                WHERE source = :source
                  AND started_at >= :today_start
            """),
            {"source": source, "today_start": today_start},
        ).fetchone()
        return {
            "completed": row.completed or 0,
            "failed": row.failed or 0,
            "running": row.running or 0,
            "cycle_started_at": row.cycle_started_at,
            "avg_duration_s": float(row.avg_duration_s) if row.avg_duration_s else None,
            "current_tld": row.current_tld,
        }

    def get_source_summary(self) -> list[dict]:
        """Aggregate stats per ingestion source."""
        rows = self.db.execute(
            text("""
                SELECT
                    source,
                    count(*) AS total_runs,
                    count(*) FILTER (WHERE status = 'success') AS successful_runs,
                    count(*) FILTER (WHERE status = 'failed') AS failed_runs,
                    count(*) FILTER (WHERE status = 'running') AS running_now,
                    max(started_at) AS last_run_at,
                    max(finished_at) FILTER (WHERE status = 'success') AS last_success_at,
                    coalesce(sum(domains_seen), 0) AS total_domains_seen,
                    coalesce(sum(domains_inserted), 0) AS total_domains_inserted
                FROM ingestion_run
                GROUP BY source
                ORDER BY source
            """)
        ).fetchall()
        results = []
        for row in rows:
            # Get the status of the most recent run
            latest = (
                self.db.query(IngestionRun)
                .filter(IngestionRun.source == row.source)
                .order_by(IngestionRun.started_at.desc())
                .first()
            )
            results.append({
                "source": row.source,
                "total_runs": row.total_runs,
                "successful_runs": row.successful_runs,
                "failed_runs": row.failed_runs,
                "running_now": row.running_now,
                "last_run_at": row.last_run_at,
                "last_success_at": row.last_success_at,
                "last_status": latest.status if latest else None,
                "total_domains_seen": int(row.total_domains_seen),
                "total_domains_inserted": int(row.total_domains_inserted),
            })
        return results

    def list_checkpoints(self, source: str | None = None) -> list[IngestionCheckpoint]:
        """List all checkpoints, optionally filtered by source."""
        query = self.db.query(IngestionCheckpoint)
        if source:
            query = query.filter(IngestionCheckpoint.source == source)
        return query.order_by(IngestionCheckpoint.source, IngestionCheckpoint.tld).all()

    def recover_all_stale_for_source(
        self,
        source: str,
        *,
        stale_after_minutes: int,
    ) -> list[IngestionRun]:
        """Mark runs with no progress for stale_after_minutes as failed.

        Used by the API startup hook (``app.main._recover_all_stale_on_startup``)
        so that runs orphaned by API-only restarts get cleaned up.

        Uses updated_at (last heartbeat / progress update) as the staleness
        criterion so that large-but-active runs (e.g. .com) are never killed
        while genuinely stuck runs (no writes for N minutes) are recovered.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_after_minutes)
        stale_runs = (
            self.db.query(IngestionRun)
            .filter(
                IngestionRun.source == source,
                IngestionRun.status == "running",
                IngestionRun.updated_at < cutoff,
            )
            .all()
        )
        if not stale_runs:
            return []
        now = datetime.now(timezone.utc)
        for run in stale_runs:
            no_progress_minutes = int((now - run.updated_at).total_seconds() // 60)
            run.status = "failed"
            run.finished_at = now
            run.updated_at = now
            run.error_message = (
                f"Automatically marked failed: no progress for {no_progress_minutes}m "
                f"(threshold: {stale_after_minutes}m)"
            )
            run.reason_code = "stale_recovered"
        self.db.flush()
        return stale_runs

    def get_tld_run_metrics(self, source: str, runs_per_tld: int = 10) -> list[dict]:
        """Return last N runs per TLD for a source in a single window-function query.

        Result is a list of dicts keyed by tld, each with a 'runs' list (newest first).
        """
        rows = self.db.execute(
            text("""
                WITH ranked AS (
                    SELECT
                        tld,
                        status,
                        started_at,
                        finished_at,
                        domains_inserted,
                        ROW_NUMBER() OVER (PARTITION BY tld ORDER BY started_at DESC) AS rn
                    FROM ingestion_run
                    WHERE source = :source
                )
                SELECT tld, status, started_at, finished_at, domains_inserted
                FROM ranked
                WHERE rn <= :runs_per_tld
                ORDER BY tld, started_at DESC
            """),
            {"source": source, "runs_per_tld": runs_per_tld},
        ).fetchall()

        grouped: dict[str, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row.tld, []).append({
                "status": row.status,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
                "domains_inserted": row.domains_inserted,
            })

        return [{"tld": tld, "runs": runs} for tld, runs in grouped.items()]
