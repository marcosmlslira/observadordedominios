"""IngestionRun — operational record of a single ingest execution."""

import uuid

from sqlalchemy import BigInteger, Column, Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, TimestampMixin


class IngestionRun(Base, TimestampMixin):
    __tablename__ = "ingestion_run"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(32), nullable=False)  # "czds"
    tld = Column(String(24), nullable=False)
    status = Column(String(16), nullable=False, default="running")  # running | success | failed
    started_at = Column(DateTime(timezone=True), nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)

    artifact_id = Column(
        UUID(as_uuid=True),
        ForeignKey("zone_file_artifact.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Counters ────────────────────────────────────────────
    domains_seen = Column(BigInteger, default=0)
    domains_inserted = Column(BigInteger, default=0)
    domains_reactivated = Column(BigInteger, default=0)
    domains_deleted = Column(BigInteger, default=0)

    error_message = Column(Text, nullable=True)
    snapshot_date = Column(Date, nullable=True)

    # ── Indexes ─────────────────────────────────────────────
    __table_args__ = (
        Index("ix_run_source_tld_started", "source", "tld", started_at.desc()),
    )
