"""IngestionTldPolicy — generic per-source TLD enable/disable (active sources)."""

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
    # NULL = use global INGESTION_STALE_TIMEOUT_MINUTES; otherwise the watchdog
    # uses this many seconds before marking a running run as stale_recovered.
    stale_timeout_seconds = Column(Integer, nullable=True)

