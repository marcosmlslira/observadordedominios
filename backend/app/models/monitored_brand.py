"""MonitoredBrand — a brand being monitored for domain similarity threats."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID

from app.models.base import Base, TimestampMixin


class MonitoredBrand(Base, TimestampMixin):
    __tablename__ = "monitored_brand"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    brand_name = Column(String(253), nullable=False)
    brand_label = Column(String(253), nullable=False)  # normalized lowercase
    keywords = Column(ARRAY(Text), nullable=False, server_default="{}")
    tld_scope = Column(ARRAY(Text), nullable=False, server_default="{}")  # empty = all
    is_active = Column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("uq_brand_org_name", "organization_id", "brand_name", unique=True),
        Index("ix_brand_active", "is_active"),
    )
