"""Durable manual similarity scan jobs."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, TimestampMixin


class SimilarityScanJob(TimestampMixin, Base):
    __tablename__ = "similarity_scan_job"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_tld = Column(String(24), nullable=True)
    effective_tlds = Column(JSONB, nullable=False, default=list)
    tld_results = Column(JSONB, nullable=False, default=dict)
    force_full = Column(Boolean, nullable=False, default=False)
    status = Column(String(24), nullable=False, default="queued")
    initiated_by = Column(String(128), nullable=True)
    queued_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_similarity_scan_job_status_queue", "status", "queued_at"),
        Index("ix_similarity_scan_job_brand_created", "brand_id", "created_at"),
    )
