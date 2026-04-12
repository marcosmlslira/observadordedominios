# backend/app/repositories/brand_domain_health_repository.py
"""Repository for brand_domain_health — upsert derived health state."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.brand_domain_health import BrandDomainHealth


class BrandDomainHealthRepository:
    """Upsert-only access to brand_domain_health records."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(
        self,
        *,
        brand_domain_id: UUID,
        brand_id: UUID,
        organization_id: UUID,
        **health_fields,
    ) -> BrandDomainHealth:
        """
        Upsert health state for a domain. Pass any health field as a keyword argument.
        Always updates updated_at. Caller must commit.
        """
        now = datetime.now(timezone.utc)

        stmt = insert(BrandDomainHealth).values(
            id=uuid.uuid4(),
            brand_domain_id=brand_domain_id,
            brand_id=brand_id,
            organization_id=organization_id,
            created_at=now,
            updated_at=now,
            **health_fields,
        ).on_conflict_do_update(
            index_elements=["brand_domain_id"],
            set_={**health_fields, "updated_at": now},
        ).returning(BrandDomainHealth)

        result = self.db.execute(stmt)
        self.db.flush()
        return result.scalar_one()

    def get_by_domain(self, brand_domain_id: UUID) -> BrandDomainHealth | None:
        return (
            self.db.query(BrandDomainHealth)
            .filter(BrandDomainHealth.brand_domain_id == brand_domain_id)
            .first()
        )

    def list_for_brand(self, brand_id: UUID) -> list[BrandDomainHealth]:
        return (
            self.db.query(BrandDomainHealth)
            .filter(BrandDomainHealth.brand_id == brand_id)
            .all()
        )
