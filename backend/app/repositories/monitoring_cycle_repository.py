# backend/app/repositories/monitoring_cycle_repository.py
"""Repository for monitoring cycles — one record per brand per day."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.monitoring_cycle import MonitoringCycle


class MonitoringCycleRepository:
    """CRUD for monitoring_cycle records."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_today(
        self,
        *,
        brand_id: UUID,
        organization_id: UUID,
        cycle_type: str = "scheduled",
    ) -> tuple[MonitoringCycle, bool]:
        """
        Return (cycle, created). If a cycle for today already exists, return it.
        Idempotent — safe to call multiple times per day.
        """
        today = date.today()
        existing = (
            self.db.query(MonitoringCycle)
            .filter(
                MonitoringCycle.brand_id == brand_id,
                MonitoringCycle.cycle_date == today,
            )
            .first()
        )
        if existing:
            return existing, False

        cycle = MonitoringCycle(
            id=uuid.uuid4(),
            brand_id=brand_id,
            organization_id=organization_id,
            cycle_date=today,
            cycle_type=cycle_type,
        )
        self.db.add(cycle)
        self.db.flush()
        return cycle, True

    def get_latest_for_brand(self, brand_id: UUID) -> MonitoringCycle | None:
        """Return the most recent cycle for a brand."""
        return (
            self.db.query(MonitoringCycle)
            .filter(MonitoringCycle.brand_id == brand_id)
            .order_by(MonitoringCycle.cycle_date.desc())
            .first()
        )

    def list_for_brand(
        self,
        brand_id: UUID,
        *,
        limit: int = 30,
        offset: int = 0,
    ) -> list[MonitoringCycle]:
        return (
            self.db.query(MonitoringCycle)
            .filter(MonitoringCycle.brand_id == brand_id)
            .order_by(MonitoringCycle.cycle_date.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def update_stage(
        self,
        cycle_id: UUID,
        *,
        stage: str,
        status: str,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        scan_job_id: UUID | None = None,
    ) -> None:
        """Update one stage's status and timestamps. Caller must commit."""
        updates: dict = {f"{stage}_status": status}
        if started_at:
            updates[f"{stage}_started_at"] = started_at
        if finished_at:
            updates[f"{stage}_finished_at"] = finished_at
        if scan_job_id and stage == "scan":
            updates["scan_job_id"] = scan_job_id
        updates["updated_at"] = datetime.now(timezone.utc)
        self.db.query(MonitoringCycle).filter(
            MonitoringCycle.id == cycle_id
        ).update(updates)

    _ALLOWED_COUNTERS = frozenset({
        "new_matches_count", "escalated_count", "dismissed_count", "threats_detected"
    })

    def increment_counter(
        self,
        cycle_id: UUID,
        *,
        field: str,
        amount: int = 1,
    ) -> None:
        """Atomically increment a summary counter. Caller must commit."""
        if field not in self._ALLOWED_COUNTERS:
            raise ValueError(f"Invalid counter field: {field!r}. Allowed: {self._ALLOWED_COUNTERS}")
        from sqlalchemy import text
        self.db.execute(
            text(f"UPDATE monitoring_cycle SET {field} = {field} + :amt, updated_at = now() WHERE id = :id"),
            {"amt": amount, "id": cycle_id},
        )
