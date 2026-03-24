"""Aliases, phrases, and support keywords attached to a monitored brand/profile."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class MonitoredBrandAlias(Base):
    __tablename__ = "monitored_brand_alias"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias_value = Column(String(253), nullable=False)
    alias_normalized = Column(String(253), nullable=False)
    alias_type = Column(String(24), nullable=False)
    weight_override = Column(Float, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    brand = relationship("MonitoredBrand", back_populates="aliases")

    __table_args__ = (
        Index(
            "uq_brand_alias_value",
            "brand_id",
            "alias_normalized",
            "alias_type",
            unique=True,
        ),
        Index("ix_brand_alias_type", "brand_id", "alias_type"),
    )
