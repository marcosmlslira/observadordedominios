"""MatchStateSnapshot — materialized threat state of a similarity match."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class MatchStateSnapshot(Base, TimestampMixin):
    """
    Materialized projection of the current threat state for one similarity match.
    Recalculated by the aggregator each time a new monitoring_event arrives for this match.

    Responsibility: Snapshot — derived state. Source of truth for current risk level.
    Domain: monitoring
    Who writes: state_aggregator (triggered by enrichment_worker events)
    Who reads: API (matches list, match drawer), assessment_worker
    Volume: 1 per similarity_match that has been enriched; ~hundreds to low thousands
    Growth: mirrors enriched matches count
    """
    __tablename__ = "match_state_snapshot"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(
        UUID(as_uuid=True),
        ForeignKey("similarity_match.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(UUID(as_uuid=True), nullable=False)

    # Derived scores (recalculated from lexical score + signal adjustments)
    derived_score = Column(Float, nullable=False, default=0.0)
    derived_bucket = Column(String(32), nullable=False, default="watchlist")
    # "immediate_attention" | "defensive_gap" | "watchlist"
    derived_risk = Column(String(16), nullable=False, default="low")
    # "low" | "medium" | "high" | "critical"
    derived_disposition = Column(String(32), nullable=True)

    # Aggregated signals from all active events
    active_signals = Column(JSONB, nullable=False, default=list)
    # [{code, severity, source_tool, source_event_id, score_adjustment}]
    signal_codes = Column(ARRAY(String), nullable=True)  # flat list for fast queries

    # LLM assessment (written by assessment_worker via aggregator)
    llm_assessment = Column(JSONB, nullable=True)
    llm_event_id = Column(UUID(as_uuid=True), nullable=True)
    llm_source_fingerprint = Column(String(64), nullable=True)
    # When llm_source_fingerprint != state_fingerprint, LLM reassessment is needed

    # Fingerprint for LLM staleness detection
    state_fingerprint = Column(String(64), nullable=False, default="")
    events_hash = Column(String(64), nullable=True)
    last_derived_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_snapshot_brand_bucket", "brand_id", "derived_bucket", "derived_score"),
        Index("ix_snapshot_brand_risk", "brand_id", "derived_risk", "derived_score"),
        # Partial index for needs_llm_assessment() query — avoids full table scan
        Index(
            "ix_snapshot_needs_llm",
            "brand_id",
            postgresql_where=text("llm_source_fingerprint IS DISTINCT FROM state_fingerprint"),
        ),
    )
