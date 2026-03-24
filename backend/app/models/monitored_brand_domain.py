"""Official domains attached to a monitored brand/profile."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class MonitoredBrandDomain(Base):
    __tablename__ = "monitored_brand_domain"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand.id", ondelete="CASCADE"),
        nullable=False,
    )
    domain_name = Column(String(253), nullable=False)
    registrable_domain = Column(String(253), nullable=False)
    registrable_label = Column(String(228), nullable=False)
    public_suffix = Column(String(24), nullable=False)
    hostname_stem = Column(String(228), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    brand = relationship("MonitoredBrand", back_populates="domains")

    __table_args__ = (
        Index("uq_brand_domain_name", "brand_id", "domain_name", unique=True),
        Index("ix_brand_domain_primary", "brand_id", "is_primary"),
    )
