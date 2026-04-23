"""SimilarityScanCursor — tracks scan progress per brand × TLD."""

import sqlalchemy as sa
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class SimilarityScanCursor(Base):
    __tablename__ = "similarity_scan_cursor"

    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tld = Column(String(24), primary_key=True)

    scan_phase = Column(String(16), nullable=False, default="initial")
    # initial = first full scan, delta = incremental scans
    status = Column(String(16), nullable=False, default="pending")
    # pending | running | complete | failed

    watermark_at = Column(DateTime(timezone=True), nullable=True)
    watermark_day = Column(sa.Integer, nullable=True)  # YYYYMMDD — ADR-001
    resume_after = Column(String(253), nullable=True)

    domains_scanned = Column(BigInteger, nullable=False, default=0)
    domains_matched = Column(BigInteger, nullable=False, default=0)

    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_cursor_status", "status"),
    )
