"""Persistent OpenINTEL availability verification status per TLD."""

from datetime import datetime, timezone

from sqlalchemy import Column, Date, DateTime, String, Text

from app.models.base import Base


class OpenintelTldStatus(Base):
    __tablename__ = "openintel_tld_status"

    tld = Column(String(24), primary_key=True)
    last_verification_at = Column(DateTime(timezone=True), nullable=True)
    last_available_snapshot_date = Column(Date, nullable=True)
    last_ingested_snapshot_date = Column(Date, nullable=True)
    last_probe_outcome = Column(String(64), nullable=True)
    last_error_message = Column(Text, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
