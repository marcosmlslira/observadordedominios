"""Chunk status for crt.sh bulk jobs."""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, TimestampMixin


class CtBulkChunk(Base, TimestampMixin):
    __tablename__ = "ct_bulk_chunk"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ct_bulk_job.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_chunk_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ct_bulk_chunk.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_tld = Column(String(24), nullable=False)
    chunk_key = Column(String(160), nullable=False)
    query_pattern = Column(String(255), nullable=False)
    prefix = Column(String(24), nullable=False, default="")
    depth = Column(Integer, nullable=False, default=0)
    status = Column(String(24), nullable=False, default="pending")
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error_type = Column(String(64), nullable=True)
    last_error_excerpt = Column(Text, nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    raw_domains = Column(BigInteger, nullable=False, default=0)
    inserted_domains = Column(BigInteger, nullable=False, default=0)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("job_id", "chunk_key", name="uq_ct_bulk_chunk_job_key"),
        Index("ix_ct_bulk_chunk_job_status", "job_id", "status"),
        Index("ix_ct_bulk_chunk_job_retry", "job_id", "next_retry_at"),
        Index("ix_ct_bulk_chunk_tld_status", "target_tld", "status"),
    )
