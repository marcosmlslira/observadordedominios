"""MonitoringEvent — immutable record of a tool execution or state change."""
from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, text
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class MonitoringEvent(Base):
    """
    Immutable event sourced from tool executions, LLM assessments, or state changes.

    Responsibility: Entity — one record per tool execution against one target.
    Domain: monitoring
    Who writes: health_worker, enrichment_worker, assessment_worker, scan_worker
    Who reads: aggregator, API (events timeline)
    Volume: ~2300/day across all brands; max ~210k rows at 90-day retention
    Growth: linear with number of brands × tools per cycle

    NOTE: Does NOT inherit TimestampMixin — events are immutable and have no updated_at.
    TimestampMixin uses bare Column definitions (not @declared_attr), so it cannot be
    overridden per-subclass. We define created_at manually here.
    """
    __tablename__ = "monitoring_event"

    # Events are write-once — only created_at, no updated_at
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand.id", ondelete="CASCADE"),
        nullable=False,
    )
    cycle_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_cycle.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Polymorphic target: exactly one must be non-null (enforced by DB constraint)
    match_id = Column(
        UUID(as_uuid=True),
        ForeignKey("similarity_match.id", ondelete="CASCADE"),
        nullable=True,
    )
    brand_domain_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand_domain.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Event classification
    event_type = Column(
        String(48), nullable=False
    )  # "tool_execution" | "llm_assessment" | "state_change" | "auto_disposition"
    event_source = Column(
        String(32), nullable=False
    )  # "health_check" | "enrichment" | "manual" | "scan"

    # Tool data (nullable for non-tool events like state_change)
    tool_name = Column(String(48), nullable=True)
    tool_version = Column(String(16), nullable=True)

    # Payload
    result_data = Column(JSONB, nullable=False, default=dict)
    signals = Column(JSONB, nullable=True)       # [{code, severity, score_adjustment, description}]
    score_snapshot = Column(JSONB, nullable=True)  # score at time of event

    # Cache TTL (when this data becomes stale and needs re-execution)
    ttl_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    brand = relationship("MonitoredBrand", back_populates=None, lazy="raise")
    match = relationship("SimilarityMatch", back_populates=None, lazy="raise")
    brand_domain = relationship("MonitoredBrandDomain", back_populates=None, lazy="raise")

    __table_args__ = (
        CheckConstraint(
            "(match_id IS NOT NULL AND brand_domain_id IS NULL) OR "
            "(match_id IS NULL AND brand_domain_id IS NOT NULL)",
            name="chk_event_target",
        ),
        Index("ix_event_match", "match_id", "created_at"),
        Index("ix_event_brand_domain", "brand_domain_id", "created_at"),
        Index("ix_event_brand_cycle", "brand_id", "cycle_id"),
        Index("ix_event_tool_latest", "match_id", "tool_name", "created_at"),
    )
