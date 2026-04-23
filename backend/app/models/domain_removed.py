"""DomainRemoved entity — domains that disappeared from a TLD zone file.

ADR-001: append-only table keyed by (name, tld), recording the day
the domain was no longer observed in the zone snapshot.
"""

from sqlalchemy import Column, Index, Integer, String

from app.models.base import Base


class DomainRemoved(Base):
    __tablename__ = "domain_removed"

    name = Column(String(253), primary_key=True)
    tld = Column(String(24), primary_key=True)
    removed_day = Column(Integer, nullable=False)  # YYYYMMDD e.g. 20260423

    __table_args__ = (
        Index("ix_domain_removed_day", "removed_day"),
    )
