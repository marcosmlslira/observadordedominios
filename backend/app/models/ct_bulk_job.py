"""Persistent crt.sh bulk job for resumable historical backfills."""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, TimestampMixin


class CtBulkJob(Base, TimestampMixin):
    __tablename__ = "ct_bulk_job"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(String(24), nullable=False, default="pending")
    requested_tlds = Column(JSONB, nullable=False, default=list)
    resolved_tlds = Column(JSONB, nullable=False, default=list)
    priority_tlds = Column(JSONB, nullable=False, default=list)
    dry_run = Column(Boolean, nullable=False, default=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    initiated_by = Column(String(128), nullable=True)
    last_error = Column(Text, nullable=True)

    total_chunks = Column(Integer, nullable=False, default=0)
    pending_chunks = Column(Integer, nullable=False, default=0)
    running_chunks = Column(Integer, nullable=False, default=0)
    done_chunks = Column(Integer, nullable=False, default=0)
    error_chunks = Column(Integer, nullable=False, default=0)
    total_raw_domains = Column(BigInteger, nullable=False, default=0)
    total_inserted_domains = Column(BigInteger, nullable=False, default=0)

    __table_args__ = (
        Index("ix_ct_bulk_job_status_created", "status", "created_at"),
    )
