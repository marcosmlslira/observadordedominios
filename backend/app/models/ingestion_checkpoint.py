"""IngestionCheckpoint — last successful sync per source/TLD pair."""

from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class IngestionCheckpoint(Base):
    __tablename__ = "ingestion_checkpoint"

    source = Column(String(32), primary_key=True)
    tld = Column(String(24), primary_key=True)
    last_successful_run_id = Column(UUID(as_uuid=True), nullable=True)
    last_successful_run_at = Column(DateTime(timezone=True), nullable=True)
