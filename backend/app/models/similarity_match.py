"""SimilarityMatch — a detected similarity match between a brand and a domain."""

import uuid

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.models.base import Base


class SimilarityMatch(Base):
    __tablename__ = "similarity_match"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand.id", ondelete="CASCADE"),
        nullable=False,
    )
    domain_name = Column(String(253), nullable=False)
    tld = Column(String(24), nullable=False)
    label = Column(Text, nullable=False)

    # Scores
    score_final = Column(Float, nullable=False)
    score_trigram = Column(Float, nullable=True)
    score_levenshtein = Column(Float, nullable=True)
    score_brand_hit = Column(Float, nullable=True)
    score_keyword = Column(Float, nullable=True)
    score_homograph = Column(Float, nullable=True)

    # Metadata
    reasons = Column(ARRAY(Text), nullable=False)
    risk_level = Column(String(16), nullable=False)  # low | medium | high | critical
    first_detected_at = Column(DateTime(timezone=True), nullable=False)
    domain_first_seen = Column(DateTime(timezone=True), nullable=False)

    # Review workflow
    status = Column(String(16), nullable=False, default="new")
    # new | reviewing | dismissed | confirmed_threat
    reviewed_by = Column(UUID(as_uuid=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    # Detection provenance
    matched_channel = Column(String(32), nullable=True)
    matched_seed_id = Column(UUID(as_uuid=True), nullable=True)
    matched_seed_value = Column(String(253), nullable=True)
    matched_seed_type = Column(String(32), nullable=True)
    matched_rule = Column(String(32), nullable=True)
    source_stream = Column(String(32), nullable=True)

    __table_args__ = (
        Index("uq_match_brand_domain", "brand_id", "domain_name", unique=True),
        Index("ix_match_brand_risk", "brand_id", "risk_level", score_final.desc()),
        Index("ix_match_brand_status", "brand_id", "status"),
    )
