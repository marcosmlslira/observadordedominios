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
        error_message: str | None = None,
        artifact_id: uuid.UUID | None = None,
    ) -> IngestionRun:
        now = datetime.now(timezone.utc)
        run.status = status
        run.finished_at = now
        run.updated_at = now
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
    ) -> list[IngestionRun]:
        """List ingestion runs ordered by newest first, with optional filters."""
        query = self.db.query(IngestionRun)
        if source:
            query = query.filter(IngestionRun.source == source)
        if status:
            query = query.filter(IngestionRun.status == status)
        return (
            query.order_by(IngestionRun.started_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

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
                IngestionRun.started_at < cutoff,
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

        self.db.flush()
        return stale_runs

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
