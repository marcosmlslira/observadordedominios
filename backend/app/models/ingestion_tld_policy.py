"""IngestionTldPolicy — generic per-source TLD enable/disable (OpenINTEL, CertStream)."""

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Integer, String

from app.models.base import Base, TimestampMixin


class IngestionTldPolicy(Base, TimestampMixin):
    __tablename__ = "ingestion_tld_policy"

    source = Column(String(32), primary_key=True)
    tld = Column(String(24), primary_key=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=True)
    domains_inserted = Column(BigInteger, nullable=False, server_default="0")
    last_seen_at = Column(DateTime(timezone=True), nullable=True)

