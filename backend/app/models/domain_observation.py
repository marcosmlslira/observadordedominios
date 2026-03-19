"""DomainObservation — append-only evidence of a domain being seen."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class DomainObservation(Base):
    __tablename__ = "domain_observation"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    domain_id = Column(
        UUID(as_uuid=True),
        ForeignKey("domain.id", ondelete="CASCADE"),
        nullable=False,
    )
    source = Column(String(32), nullable=False)  # e.g. "czds"
    tld = Column(String(24), nullable=False)
    observed_at = Column(DateTime(timezone=True), nullable=False)
    ingestion_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_run.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationships ───────────────────────────────────────
    domain = relationship("Domain", back_populates="observations")

    # ── Constraints & Indexes ───────────────────────────────
    __table_args__ = (
        UniqueConstraint(
            "domain_id", "source", "observed_at", "ingestion_run_id",
            name="uq_domain_obs_natural",
        ),
        Index("ix_domain_obs_tld_observed", "tld", observed_at.desc()),
    )
