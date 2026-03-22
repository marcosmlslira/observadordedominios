"""Repository for monitored_brand CRUD operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.monitored_brand import MonitoredBrand


class MonitoredBrandRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        organization_id: uuid.UUID,
        brand_name: str,
        brand_label: str,
        keywords: list[str] | None = None,
        tld_scope: list[str] | None = None,
    ) -> MonitoredBrand:
        now = datetime.now(timezone.utc)
        brand = MonitoredBrand(
            id=uuid.uuid4(),
            organization_id=organization_id,
            brand_name=brand_name,
            brand_label=brand_label.lower().strip(),
            keywords=keywords or [],
            tld_scope=tld_scope or [],
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self.db.add(brand)
        self.db.flush()
        return brand

    def get(self, brand_id: uuid.UUID) -> MonitoredBrand | None:
        return self.db.get(MonitoredBrand, brand_id)

    def get_by_org_and_name(
        self, organization_id: uuid.UUID, brand_name: str,
    ) -> MonitoredBrand | None:
        return (
            self.db.query(MonitoredBrand)
            .filter(
                MonitoredBrand.organization_id == organization_id,
                MonitoredBrand.brand_name == brand_name,
            )
            .first()
        )

    def list_by_org(
        self, organization_id: uuid.UUID, active_only: bool = True,
    ) -> list[MonitoredBrand]:
        q = self.db.query(MonitoredBrand).filter(
            MonitoredBrand.organization_id == organization_id,
        )
        if active_only:
            q = q.filter(MonitoredBrand.is_active == True)  # noqa: E712
        return q.order_by(MonitoredBrand.brand_name).all()

    def list_active(self) -> list[MonitoredBrand]:
        """All active brands across all orgs (for the similarity worker)."""
        return (
            self.db.query(MonitoredBrand)
            .filter(MonitoredBrand.is_active == True)  # noqa: E712
            .order_by(MonitoredBrand.created_at)
            .all()
        )

    def update(
        self,
        brand: MonitoredBrand,
        *,
        brand_name: str | None = None,
        brand_label: str | None = None,
        keywords: list[str] | None = None,
        tld_scope: list[str] | None = None,
        is_active: bool | None = None,
    ) -> MonitoredBrand:
        if brand_name is not None:
            brand.brand_name = brand_name
        if brand_label is not None:
            brand.brand_label = brand_label.lower().strip()
        if keywords is not None:
            brand.keywords = keywords
        if tld_scope is not None:
            brand.tld_scope = tld_scope
        if is_active is not None:
            brand.is_active = is_active
        brand.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return brand

    def delete(self, brand: MonitoredBrand) -> None:
        self.db.delete(brand)
        self.db.flush()
