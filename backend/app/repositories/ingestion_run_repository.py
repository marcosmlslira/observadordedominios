"""Repository for ingestion_run and ingestion_checkpoint."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

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

    def list_runs(self, limit: int = 20, offset: int = 0) -> list[IngestionRun]:
        """List ingestion runs ordered by newest first."""
        return (
            self.db.query(IngestionRun)
            .order_by(IngestionRun.started_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

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
