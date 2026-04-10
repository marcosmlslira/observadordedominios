"""IngestionTldPolicy — generic per-source TLD enable/disable (OpenINTEL, CertStream)."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String

from app.models.base import Base


class IngestionTldPolicy(Base):
    __tablename__ = "ingestion_tld_policy"

    source = Column(String(32), primary_key=True)
    tld = Column(String(64), primary_key=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
