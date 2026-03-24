"""Derived or manual search seeds used by the similarity engine."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class MonitoredBrandSeed(Base):
    __tablename__ = "monitored_brand_seed"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_ref_type = Column(String(24), nullable=False)
    source_ref_id = Column(UUID(as_uuid=True), nullable=True)
    seed_value = Column(String(253), nullable=False)
    seed_type = Column(String(32), nullable=False)
    channel_scope = Column(String(32), nullable=False)
    base_weight = Column(Float, nullable=False)
    is_manual = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    brand = relationship("MonitoredBrand", back_populates="seeds")

    __table_args__ = (
        Index(
            "uq_brand_seed_unique",
            "brand_id",
            "seed_value",
            "seed_type",
            "channel_scope",
            unique=True,
        ),
        Index("ix_brand_seed_channel", "brand_id", "channel_scope", "is_active"),
    )
