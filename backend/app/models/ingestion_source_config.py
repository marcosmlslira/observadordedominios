"""IngestionSourceConfig — persisted cron schedule per ingestion source."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String

from app.models.base import Base


class IngestionSourceConfig(Base):
    __tablename__ = "ingestion_source_config"

    source = Column(String(32), primary_key=True)  # "czds" | "certstream" | "openintel"
    cron_expression = Column(String(64), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
