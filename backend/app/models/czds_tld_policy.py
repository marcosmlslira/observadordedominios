"""CzdsTldPolicy — configuration table for enabled TLDs."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.models.base import Base


class CzdsTldPolicy(Base):
    __tablename__ = "czds_tld_policy"

    tld = Column(String(24), primary_key=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    priority = Column(Integer, nullable=False, default=100)
    cooldown_hours = Column(Integer, nullable=False, default=24)
    failure_count = Column(Integer, nullable=False, default=0)
    last_error_code = Column(Integer, nullable=True)
    last_error_at = Column(DateTime(timezone=True), nullable=True)
    suspended_until = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
