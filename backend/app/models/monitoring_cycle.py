"""MonitoringCycle — daily per-brand monitoring progress tracker."""
from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class MonitoringCycle(Base, TimestampMixin):
    """
    One record per brand per day. Aggregates progress of all pipeline stages.

    Responsibility: Configuration/Event — daily pipeline state.
    Domain: monitoring
    Who writes: health_worker, scan_worker, enrichment_worker
    Who reads: API (brand detail), assessment_worker
    Volume: 1 per active brand per day; retained 180 days
    Growth: linear with number of brands
    """
    __tablename__ = "monitoring_cycle"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    cycle_date = Column(Date, nullable=False)
    cycle_type = Column(String(16), nullable=False, default="scheduled")  # "scheduled" | "manual"

    # Stage statuses
    health_status = Column(String(16), nullable=False, default="pending")
    health_started_at = Column(DateTime(timezone=True), nullable=True)
    health_finished_at = Column(DateTime(timezone=True), nullable=True)

    scan_status = Column(String(16), nullable=False, default="pending")
    scan_started_at = Column(DateTime(timezone=True), nullable=True)
    scan_finished_at = Column(DateTime(timezone=True), nullable=True)
    scan_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("similarity_scan_job.id", ondelete="SET NULL"),
        nullable=True,
    )

    enrichment_status = Column(String(16), nullable=False, default="pending")
    enrichment_started_at = Column(DateTime(timezone=True), nullable=True)
    enrichment_finished_at = Column(DateTime(timezone=True), nullable=True)
    enrichment_budget = Column(Integer, nullable=False, default=0)
    enrichment_total = Column(Integer, nullable=False, default=0)

    # Summary counters (updated incrementally)
    new_matches_count = Column(Integer, nullable=False, default=0)
    escalated_count = Column(Integer, nullable=False, default=0)
    dismissed_count = Column(Integer, nullable=False, default=0)
    threats_detected = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("brand_id", "cycle_date", name="uq_cycle_brand_date"),
        Index("ix_cycle_brand_date", "brand_id", "cycle_date"),
    )
