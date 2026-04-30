"""IngestionCycleTld — per-TLD plan row for every ingestion cycle."""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class IngestionCycleTld(Base):
    __tablename__ = "ingestion_cycle_tld"

    cycle_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_cycle.cycle_id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    source = Column(String(32), primary_key=True, nullable=False)
    tld = Column(String(64), primary_key=True, nullable=False)

    # Planning
    priority = Column(Integer, nullable=True)
    planned_position = Column(Integer, nullable=True)
    planned_phase = Column(String(16), nullable=True)

    # Execution state
    execution_status = Column(String(16), nullable=False, default="planned")
    blocked_by_source = Column(String(32), nullable=True)
    blocked_by_tld = Column(String(64), nullable=True)

    # Error detail
    reason_code = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)

    # Run linkage
    r2_run_id = Column(UUID(as_uuid=True), nullable=True)
    pg_run_id = Column(UUID(as_uuid=True), nullable=True)

    # Databricks metadata
    databricks_run_id = Column(BigInteger, nullable=True)
    databricks_run_url = Column(Text, nullable=True)
    databricks_result_state = Column(String(32), nullable=True)

    # Snapshot info
    r2_marker_date = Column(Date, nullable=True)
    snapshot_date = Column(Date, nullable=True)

    # Timing
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Integer, nullable=True)
