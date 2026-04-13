"""Repository for monitored_brand CRUD operations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session, selectinload

from app.models.monitored_brand_alias import MonitoredBrandAlias
from app.models.monitored_brand import MonitoredBrand
from app.models.monitored_brand_domain import MonitoredBrandDomain
from app.models.monitored_brand_seed import MonitoredBrandSeed


class MonitoredBrandRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        organization_id: uuid.UUID,
        brand_name: str,
        primary_brand_name: str,
        brand_label: str,
        keywords: list[str] | None = None,
        tld_scope: list[str] | None = None,
        noise_mode: str = "standard",
        notes: str | None = None,
    ) -> MonitoredBrand:
        now = datetime.now(timezone.utc)
        brand = MonitoredBrand(
            id=uuid.uuid4(),
            organization_id=organization_id,
            brand_name=brand_name,
            primary_brand_name=primary_brand_name,
            brand_label=brand_label.lower().strip(),
            keywords=keywords or [],
            tld_scope=tld_scope or [],
            noise_mode=noise_mode,
            notes=notes,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        self.db.add(brand)
        self.db.flush()
        return brand

    def get(self, brand_id: uuid.UUID) -> MonitoredBrand | None:
        return (
            self.db.query(MonitoredBrand)
            .options(
                selectinload(MonitoredBrand.domains),
                selectinload(MonitoredBrand.aliases),
                selectinload(MonitoredBrand.seeds),
            )
            .filter(MonitoredBrand.id == brand_id)
            .first()
        )

    def get_by_org_and_name(
        self, organization_id: uuid.UUID, brand_name: str,
    ) -> MonitoredBrand | None:
        return (
            self.db.query(MonitoredBrand)
            .options(
                selectinload(MonitoredBrand.domains),
                selectinload(MonitoredBrand.aliases),
                selectinload(MonitoredBrand.seeds),
            )
            .filter(
                MonitoredBrand.organization_id == organization_id,
                MonitoredBrand.brand_name == brand_name,
            )
            .first()
        )

    def list_by_org(
        self, organization_id: uuid.UUID, active_only: bool = True,
    ) -> list[MonitoredBrand]:
        q = (
            self.db.query(MonitoredBrand)
            .options(
                selectinload(MonitoredBrand.domains),
                selectinload(MonitoredBrand.aliases),
                selectinload(MonitoredBrand.seeds),
            )
            .filter(MonitoredBrand.organization_id == organization_id)
        )
        if active_only:
            q = q.filter(MonitoredBrand.is_active == True)  # noqa: E712
        return q.order_by(MonitoredBrand.brand_name).all()

    def list_active(self) -> list[MonitoredBrand]:
        """All active brands across all orgs (for the similarity worker)."""
        return (
            self.db.query(MonitoredBrand)
            .options(
                selectinload(MonitoredBrand.domains),
                selectinload(MonitoredBrand.aliases),
                selectinload(MonitoredBrand.seeds),
            )
            .filter(MonitoredBrand.is_active == True)  # noqa: E712
            .order_by(MonitoredBrand.created_at)
            .all()
        )

    def update(
        self,
        brand: MonitoredBrand,
        *,
        brand_name: str | None = None,
        primary_brand_name: str | None = None,
        brand_label: str | None = None,
        keywords: list[str] | None = None,
        tld_scope: list[str] | None = None,
        noise_mode: str | None = None,
        notes: str | None = None,
        is_active: bool | None = None,
        trusted_registrants: dict | None = None,
    ) -> MonitoredBrand:
        if brand_name is not None:
            brand.brand_name = brand_name
        if primary_brand_name is not None:
            brand.primary_brand_name = primary_brand_name
        if brand_label is not None:
            brand.brand_label = brand_label.lower().strip()
        if keywords is not None:
            brand.keywords = keywords
        if tld_scope is not None:
            brand.tld_scope = tld_scope
        if noise_mode is not None:
            brand.noise_mode = noise_mode
        if notes is not None:
            brand.notes = notes
        if is_active is not None:
            brand.is_active = is_active
        if trusted_registrants is not None:
            brand.trusted_registrants = trusted_registrants
        brand.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return brand

    def replace_domains(
        self,
        brand: MonitoredBrand,
        domains: list[dict],
    ) -> list[MonitoredBrandDomain]:
        brand.domains[:] = []
        now = datetime.now(timezone.utc)
        for item in domains:
            brand.domains.append(
                MonitoredBrandDomain(
                    id=uuid.uuid4(),
                    brand_id=brand.id,
                    created_at=now,
                    updated_at=now,
                    **item,
                )
            )
        self.db.flush()
        return list(brand.domains)

    def replace_aliases(
        self,
        brand: MonitoredBrand,
        aliases: list[dict],
    ) -> list[MonitoredBrandAlias]:
        brand.aliases[:] = []
        now = datetime.now(timezone.utc)
        for item in aliases:
            brand.aliases.append(
                MonitoredBrandAlias(
                    id=uuid.uuid4(),
                    brand_id=brand.id,
                    created_at=now,
                    updated_at=now,
                    **item,
                )
            )
        self.db.flush()
        return list(brand.aliases)

    def replace_seeds(
        self,
        brand: MonitoredBrand,
        seeds: list[dict],
    ) -> list[MonitoredBrandSeed]:
        brand.seeds[:] = []
        now = datetime.now(timezone.utc)
        for item in seeds:
            brand.seeds.append(
                MonitoredBrandSeed(
                    id=uuid.uuid4(),
                    brand_id=brand.id,
                    created_at=now,
                    updated_at=now,
                    **item,
                )
            )
        self.db.flush()
        return list(brand.seeds)

    def delete(self, brand: MonitoredBrand) -> None:
        self.db.delete(brand)
        self.db.flush()
