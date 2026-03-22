"""Domain entity — canonical global domain record (partitioned by TLD)."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, String

from app.models.base import Base


class Domain(Base):
    __tablename__ = "domain"

    name = Column(String(253), primary_key=True)
    tld = Column(String(24), primary_key=True)
    label = Column(String, nullable=False)
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

    __table_args__ = (
        Index("ix_domain_label_trgm", "label", postgresql_using="gin",
              postgresql_ops={"label": "gin_trgm_ops"}),
        Index("ix_domain_first_seen", "tld", first_seen_at.desc()),
        Index("ix_domain_last_seen", "tld", last_seen_at.desc()),
    )
