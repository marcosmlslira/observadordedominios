"""IngestionSourceConfig — persisted cron schedule per ingestion source."""

from sqlalchemy import Column, String

from app.models.base import Base, TimestampMixin


class IngestionSourceConfig(Base, TimestampMixin):
    __tablename__ = "ingestion_source_config"

    source = Column(String(32), primary_key=True)  # "czds" | "certstream" | "openintel"
    cron_expression = Column(String(64), nullable=False)
