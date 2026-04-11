"""IngestionTldPolicy — generic per-source TLD enable/disable (OpenINTEL, CertStream)."""

from sqlalchemy import Boolean, Column, Integer, String

from app.models.base import Base, TimestampMixin


class IngestionTldPolicy(Base, TimestampMixin):
    __tablename__ = "ingestion_tld_policy"

    source = Column(String(32), primary_key=True)
    tld = Column(String(24), primary_key=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=True)

