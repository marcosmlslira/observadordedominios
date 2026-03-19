"""Domain entity — canonical global domain record."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class Domain(Base, TimestampMixin):
    __tablename__ = "domain"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(253), unique=True, nullable=False, index=True)
    tld = Column(String(24), nullable=False)
    status = Column(String(16), nullable=False, default="active")  # active | deleted
    first_seen_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    last_seen_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # ── Relationships ───────────────────────────────────────
    observations = relationship(
        "DomainObservation", back_populates="domain", cascade="all, delete-orphan"
    )

    # ── Indexes ─────────────────────────────────────────────
    __table_args__ = (
        Index("ix_domain_tld_last_seen", "tld", last_seen_at.desc()),
        Index("ix_domain_status_tld", "status", "tld"),
    )
