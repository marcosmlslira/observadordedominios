"""Service for managing the lifecycle of a monitoring cycle."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.monitoring_cycle_repository import MonitoringCycleRepository


class MonitoringCycleService:
    """
    Manages stage transitions for a monitoring_cycle record.
    Workers call begin_stage/finish_stage to record progress.
    """

    def __init__(
        self,
        db: Session,
        *,
        cycle_repo: MonitoringCycleRepository | None = None,
    ) -> None:
        self.db = db
        self.repo = cycle_repo or MonitoringCycleRepository(db)

    def begin_stage(self, cycle_id: UUID, *, stage: str) -> None:
        """Mark a stage as running and record start timestamp. Caller must commit."""
        self.repo.update_stage(
            cycle_id,
            stage=stage,
            status="running",
            started_at=datetime.now(timezone.utc),
        )

    def finish_stage(
        self,
        cycle_id: UUID,
        *,
        stage: str,
        success: bool,
        scan_job_id: UUID | None = None,
    ) -> None:
        """Mark a stage as completed or failed and record end timestamp. Caller must commit."""
        self.repo.update_stage(
            cycle_id,
            stage=stage,
            status="completed" if success else "failed",
            finished_at=datetime.now(timezone.utc),
            scan_job_id=scan_job_id,
        )

    def skip_stage(self, cycle_id: UUID, *, stage: str) -> None:
        """Mark a stage as skipped (e.g., brand has no official domains). Caller must commit."""
        self.repo.update_stage(cycle_id, stage=stage, status="skipped")

    def record_new_match(self, cycle_id: UUID) -> None:
        """Increment new_matches_count. Caller must commit at batch boundary."""
        self.repo.increment_counter(cycle_id, field="new_matches_count")

    def record_threat_detected(self, cycle_id: UUID) -> None:
        """Increment threats_detected. Caller must commit at batch boundary."""
        self.repo.increment_counter(cycle_id, field="threats_detected")

    def record_dismissed(self, cycle_id: UUID) -> None:
        """Increment dismissed_count. Caller must commit at batch boundary."""
        self.repo.increment_counter(cycle_id, field="dismissed_count")

    def record_escalated(self, cycle_id: UUID) -> None:
        """Increment escalated_count. Caller must commit at batch boundary."""
        self.repo.increment_counter(cycle_id, field="escalated_count")
