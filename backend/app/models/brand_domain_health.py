"""BrandDomainHealth — materialized health state of an official brand domain."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class BrandDomainHealth(Base, TimestampMixin):
    """
    Materialized view of the latest health check results for one official domain.
    Recalculated by the aggregator after each health check event.

    Responsibility: Snapshot — derived state, not source of truth.
    Domain: monitoring
    Who writes: state_aggregator (triggered by health_worker events)
    Who reads: API (brand detail /health endpoint)
    Volume: 1 per brand_domain; stable, grows with domains added
    Growth: very slow
    """
    __tablename__ = "brand_domain_health"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_domain_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand_domain.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(UUID(as_uuid=True), nullable=False)

    # Derived overall status
    overall_status = Column(String(16), nullable=False, default="unknown")
    # "healthy" | "warning" | "critical" | "unknown"

    # Per-tool booleans (None = not checked yet / tool failed)
    dns_ok = Column(Boolean, nullable=True)
    ssl_ok = Column(Boolean, nullable=True)
    ssl_days_remaining = Column(Integer, nullable=True)
    email_security_ok = Column(Boolean, nullable=True)
    spoofing_risk = Column(String(16), nullable=True)  # "none" | "low" | "medium" | "high" | "critical"
    headers_score = Column(String(16), nullable=True)  # "good" | "partial" | "poor"
    takeover_risk = Column(Boolean, nullable=True)
    blacklisted = Column(Boolean, nullable=True)
    safe_browsing_hit = Column(Boolean, nullable=True)
    urlhaus_hit = Column(Boolean, nullable=True)
    phishtank_hit = Column(Boolean, nullable=True)
    suspicious_content = Column(Boolean, nullable=True)

    # Fingerprint and traceability
    state_fingerprint = Column(String(64), nullable=True)
    last_check_at = Column(DateTime(timezone=True), nullable=True)
    last_event_ids = Column(JSONB, nullable=True)  # [event_id, ...] that produced this state

    __table_args__ = (
        Index("ix_health_brand", "brand_id"),
    )
