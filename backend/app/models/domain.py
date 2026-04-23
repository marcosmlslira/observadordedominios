"""Domain entity — canonical global domain record (partitioned by TLD).

ADR-001: simplified schema — added_day (YYYYMMDD integer) replaces
first_seen_at/last_seen_at. No timestamps, no is_active, no domain_raw_b64.
"""

from sqlalchemy import Column, Index, Integer, String

from app.models.base import Base


class Domain(Base):
    __tablename__ = "domain"

    name = Column(String(253), primary_key=True)
    tld = Column(String(24), primary_key=True)
    label = Column(String, nullable=False)
    added_day = Column(Integer, nullable=False)  # YYYYMMDD e.g. 20260423

    __table_args__ = (
        Index(
            "ix_domain_label_trgm", "label",
            postgresql_using="gin",
            postgresql_ops={"label": "gin_trgm_ops"},
        ),
        Index("ix_domain_added_day", "added_day"),
    )
