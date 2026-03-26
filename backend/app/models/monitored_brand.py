"""MonitoredBrand — compatibility root for monitoring profiles."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class MonitoredBrand(Base, TimestampMixin):
    __tablename__ = "monitored_brand"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    brand_name = Column(String(253), nullable=False)  # display_name compatibility
    primary_brand_name = Column(String(253), nullable=False)
    brand_label = Column(String(253), nullable=False)  # primary normalized search label
    keywords = Column(ARRAY(Text), nullable=False, server_default="{}")
    tld_scope = Column(ARRAY(Text), nullable=False, server_default="{}")  # empty = all
    noise_mode = Column(String(16), nullable=False, default="standard")
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    alert_webhook_url = Column(Text, nullable=True)

    domains = relationship(
        "MonitoredBrandDomain",
        back_populates="brand",
        cascade="all, delete-orphan",
        order_by="MonitoredBrandDomain.created_at",
    )
    aliases = relationship(
        "MonitoredBrandAlias",
        back_populates="brand",
        cascade="all, delete-orphan",
        order_by="MonitoredBrandAlias.created_at",
    )
    seeds = relationship(
        "MonitoredBrandSeed",
        back_populates="brand",
        cascade="all, delete-orphan",
        order_by="MonitoredBrandSeed.base_weight.desc()",
    )

    __table_args__ = (
        Index("uq_brand_org_name", "organization_id", "brand_name", unique=True),
        Index("ix_brand_active", "is_active"),
    )
