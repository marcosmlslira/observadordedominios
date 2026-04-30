"""Repository for ingestion_run and ingestion_checkpoint."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.ingestion_checkpoint import IngestionCheckpoint
from app.models.ingestion_run import IngestionRun


class IngestionRunRepository:
    """CRUD helpers for IngestionRun and IngestionCheckpoint."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Run lifecycle ───────────────────────────────────────
    def create_run(self, source: str, tld: str) -> IngestionRun:
        now = datetime.now(timezone.utc)
        run = IngestionRun(
            id=uuid.uuid4(),
            source=source,
            tld=tld,
            status="running",
            started_at=now,
            created_at=now,
            updated_at=now,
        )
        self.db.add(run)
        self.db.flush()
        return run

    def finish_run(
        self,
        run: IngestionRun,
        *,
        status: str,
        metrics: dict[str, int] | None = None,
        reason_code: str | None = None,
        error_message: str | None = None,
        artifact_id: uuid.UUID | None = None,
    ) -> IngestionRun:
        now = datetime.now(timezone.utc)
        run.status = status
        run.finished_at = now
        run.updated_at = now
        run.reason_code = reason_code
        run.error_message = error_message
        if artifact_id:
            run.artifact_id = artifact_id
        if metrics:
            run.domains_seen = metrics.get("seen", 0)
            run.domains_inserted = metrics.get("inserted", 0)
            run.domains_reactivated = metrics.get("reactivated", 0)
            run.domains_deleted = metrics.get("deleted", 0)
        self.db.flush()
        return run

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

    def list_checkpoint_tlds(self, source: str) -> set[str]:
        """Return the set of TLDs that already have a successful checkpoint."""
        rows = (
            self.db.query(IngestionCheckpoint.tld)
            .filter(IngestionCheckpoint.source == source)
            .all()
        )
        return {row[0] for row in rows}

    def has_running_run(self, source: str, tld: str, exclude_run_id: uuid.UUID | None = None) -> bool:
        """Check if there is already a running run for this source/TLD."""
        query = (
            self.db.query(IngestionRun)
            .filter(
                IngestionRun.source == source,
                IngestionRun.tld == tld,
                IngestionRun.status == "running",
            )
        )
        if exclude_run_id:
            query = query.filter(IngestionRun.id != exclude_run_id)
            
        return query.first() is not None

    def recover_stale_runs(
        self,
        source: str,
        tld: str,
        *,
        stale_after_minutes: int,
        exclude_run_id: uuid.UUID | None = None,
    ) -> list[IngestionRun]:
        """Mark orphaned running runs as failed so the TLD can progress again."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_after_minutes)
        query = (
            self.db.query(IngestionRun)
            .filter(
                IngestionRun.source == source,
                IngestionRun.tld == tld,
                IngestionRun.status == "running",
                IngestionRun.updated_at < cutoff,
            )
            .order_by(IngestionRun.started_at.asc())
        )
        if exclude_run_id:
            query = query.filter(IngestionRun.id != exclude_run_id)

        stale_runs = query.all()
        if not stale_runs:
            return []

        now = datetime.now(timezone.utc)
        for run in stale_runs:
            run.status = "failed"
            run.finished_at = now
            run.updated_at = now
            age_minutes = int((now - run.started_at).total_seconds() // 60)
            run.error_message = (
                f"Run marked as failed automatically after exceeding the stale timeout "
                f"({age_minutes} minutes without completion)"
            )
            run.reason_code = "stale_recovered"

        self.db.flush()
        return stale_runs

    def recover_all_stale_for_source(
        self,
        source: str,
        *,
        stale_after_minutes: int,
    ) -> list[IngestionRun]:
        """Mark runs with no progress for stale_after_minutes as failed.

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

    def touch_run(self, run: IngestionRun) -> IngestionRun:
        """Refresh run heartbeat without changing business status."""
        run.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return run

    def mark_running_runs_failed(
        self,
        source: str,
        tld: str,
        *,
        error_message: str,
        exclude_run_id: uuid.UUID | None = None,
    ) -> list[IngestionRun]:
        """Fail all currently running runs for a source/TLD pair."""
        query = (
            self.db.query(IngestionRun)
            .filter(
                IngestionRun.source == source,
                IngestionRun.tld == tld,
                IngestionRun.status == "running",
            )
            .order_by(IngestionRun.started_at.asc())
        )
        if exclude_run_id:
            query = query.filter(IngestionRun.id != exclude_run_id)

        runs = query.all()
        if not runs:
            return []

        now = datetime.now(timezone.utc)
        for run in runs:
            run.status = "failed"
            run.finished_at = now
            run.updated_at = now
            run.error_message = error_message
            run.reason_code = "unexpected_error"

        self.db.flush()
        return runs

    def mark_running_source_runs_failed(
        self,
        source: str,
        *,
        error_message: str,
    ) -> list[IngestionRun]:
        """Fail all currently running runs for a source regardless of TLD."""
        runs = (
            self.db.query(IngestionRun)
            .filter(
                IngestionRun.source == source,
                IngestionRun.status == "running",
            )
            .order_by(IngestionRun.started_at.asc())
            .all()
        )
        if not runs:
            return []

        now = datetime.now(timezone.utc)
        for run in runs:
            run.status = "failed"
            run.finished_at = now
            run.updated_at = now
            run.error_message = error_message
            run.reason_code = "unexpected_error"

        self.db.flush()
        return runs

    def update_progress(self, run_id: uuid.UUID, *, domains_seen: int) -> None:
        """Persist progress counters and refresh heartbeat for long-running syncs."""
        self.db.execute(
            text(
                """
                UPDATE ingestion_run
                SET domains_seen = :domains_seen,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": run_id,
                "domains_seen": domains_seen,
                "updated_at": datetime.now(timezone.utc),
            },
        )

    def add_progress(
        self,
        run_id: uuid.UUID,
        *,
        domains_seen_delta: int = 0,
        domains_inserted_delta: int = 0,
    ) -> None:
        """Accumulate metrics and refresh heartbeat for streaming ingestors."""
        self.db.execute(
            text(
                """
                UPDATE ingestion_run
                SET domains_seen = COALESCE(domains_seen, 0) + :domains_seen_delta,
                    domains_inserted = COALESCE(domains_inserted, 0) + :domains_inserted_delta,
                    updated_at = :updated_at
                WHERE id = :id
                """
            ),
            {
                "id": run_id,
                "domains_seen_delta": domains_seen_delta,
                "domains_inserted_delta": domains_inserted_delta,
                "updated_at": datetime.now(timezone.utc),
            },
        )

    # ── Checkpoint ──────────────────────────────────────────
    def upsert_checkpoint(self, source: str, tld: str, run: IngestionRun) -> None:
        """Update (or insert) the checkpoint for a successful run."""
        self.db.execute(
            text("""
                INSERT INTO ingestion_checkpoint (source, tld, last_successful_run_id, last_successful_run_at)
                VALUES (:source, :tld, :run_id, :run_at)
                ON CONFLICT (source, tld) DO UPDATE SET
                    last_successful_run_id = EXCLUDED.last_successful_run_id,
                    last_successful_run_at = EXCLUDED.last_successful_run_at
            """),
            {
                "source": source,
                "tld": tld,
                "run_id": run.id,
                "run_at": run.finished_at,
            },
        )
        self.db.flush()

    def get_checkpoint(self, source: str, tld: str) -> IngestionCheckpoint | None:
        return self.db.get(IngestionCheckpoint, (source, tld))

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

    def has_any_source_running(self, source: str) -> bool:
        """True if any run for this source is currently in 'running' status (any TLD)."""
        return (
            self.db.query(IngestionRun)
            .filter(IngestionRun.source == source, IngestionRun.status == "running")
            .first()
        ) is not None

    def has_successful_run_after(self, source: str, tld: str, after: "date") -> bool:
        """True if a successful run for source/tld was started on or after `after` (00:00 UTC)."""
        from datetime import date as _date
        after_dt = datetime(after.year, after.month, after.day, tzinfo=timezone.utc)
        return (
            self.db.query(IngestionRun)
            .filter(
                IngestionRun.source == source,
                IngestionRun.tld == tld,
                IngestionRun.status == "success",
                IngestionRun.started_at >= after_dt,
            )
            .first()
        ) is not None
