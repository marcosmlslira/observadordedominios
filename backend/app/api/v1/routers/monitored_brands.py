"""Monitored brands API — CRUD + trigger similarity scan."""

from __future__ import annotations

import logging
import threading
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin

from app.infra.db.session import SessionLocal, get_db
from app.repositories.monitored_brand_repository import MonitoredBrandRepository
from app.repositories.similarity_repository import SimilarityRepository
from app.schemas.monitored_brand import (
    BrandAliasResponse,
    BrandDomainResponse,
    BrandListResponse,
    BrandResponse,
    BrandSeedListResponse,
    BrandSeedResponse,
    CreateBrandRequest,
    UpdateBrandRequest,
)
from app.schemas.similarity import ScanResultResponse, ScanSummaryResponse
from app.services.use_cases.sync_monitoring_profile import (
    create_monitoring_profile,
    ensure_monitoring_profile_integrity,
    update_monitoring_profile,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/brands",
    tags=["Monitored Brands"],
    dependencies=[Depends(get_current_admin)],
)

# TODO: Replace with real auth dependency when identity domain is built
PLACEHOLDER_ORG_ID = UUID("00000000-0000-0000-0000-000000000001")


def _to_brand_response(brand) -> BrandResponse:
    return BrandResponse(
        id=brand.id,
        organization_id=brand.organization_id,
        brand_name=brand.brand_name,
        primary_brand_name=brand.primary_brand_name,
        brand_label=brand.brand_label,
        keywords=list(brand.keywords or []),
        tld_scope=list(brand.tld_scope or []),
        noise_mode=brand.noise_mode,
        notes=brand.notes,
        official_domains=[BrandDomainResponse.model_validate(item) for item in brand.domains],
        aliases=[BrandAliasResponse.model_validate(item) for item in brand.aliases],
        seeds=[BrandSeedResponse.model_validate(item) for item in brand.seeds],
        is_active=brand.is_active,
        created_at=brand.created_at,
        updated_at=brand.updated_at,
    )


@router.post(
    "",
    response_model=BrandResponse,
    status_code=201,
    summary="Create a monitored brand",
)
def create_brand(
    body: CreateBrandRequest,
    db: Session = Depends(get_db),
):
    repo = MonitoredBrandRepository(db)

    # Check for duplicate
    existing = repo.get_by_org_and_name(PLACEHOLDER_ORG_ID, body.brand_name)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Brand '{body.brand_name}' already exists for this organization",
        )

    brand = create_monitoring_profile(
        repo,
        organization_id=PLACEHOLDER_ORG_ID,
        display_name=body.brand_name,
        primary_brand_name=body.primary_brand_name,
        official_domains=body.official_domains,
        aliases=body.aliases,
        keywords=body.keywords,
        tld_scope=body.tld_scope,
        noise_mode=body.noise_mode,
        notes=body.notes,
    )
    db.commit()
    return _to_brand_response(brand)


@router.get(
    "",
    response_model=BrandListResponse,
    summary="List monitored brands",
)
def list_brands(
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    repo = MonitoredBrandRepository(db)
    brands = repo.list_by_org(PLACEHOLDER_ORG_ID, active_only=active_only)
    hydrated = []
    for brand in brands:
        ensure_monitoring_profile_integrity(repo, brand)
        hydrated.append(_to_brand_response(brand))
    db.commit()
    return BrandListResponse(items=hydrated, total=len(hydrated))


@router.get(
    "/{brand_id}",
    response_model=BrandResponse,
    summary="Get a monitored brand",
)
def get_brand(
    brand_id: UUID,
    db: Session = Depends(get_db),
):
    repo = MonitoredBrandRepository(db)
    brand = repo.get(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    ensure_monitoring_profile_integrity(repo, brand)
    db.commit()
    return _to_brand_response(brand)


@router.patch(
    "/{brand_id}",
    response_model=BrandResponse,
    summary="Update a monitored brand",
)
def update_brand(
    brand_id: UUID,
    body: UpdateBrandRequest,
    db: Session = Depends(get_db),
):
    repo = MonitoredBrandRepository(db)
    brand = repo.get(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    update_monitoring_profile(
        repo,
        brand,
        display_name=body.brand_name,
        primary_brand_name=body.primary_brand_name,
        official_domains=body.official_domains,
        aliases=body.aliases,
        keywords=body.keywords,
        tld_scope=body.tld_scope,
        noise_mode=body.noise_mode,
        notes=body.notes,
        is_active=body.is_active,
    )
    db.commit()
    return _to_brand_response(brand)


@router.delete(
    "/{brand_id}",
    status_code=204,
    summary="Delete a monitored brand",
)
def delete_brand(
    brand_id: UUID,
    db: Session = Depends(get_db),
):
    repo = MonitoredBrandRepository(db)
    brand = repo.get(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    repo.delete(brand)
    db.commit()


@router.get(
    "/{brand_id}/seeds",
    response_model=BrandSeedListResponse,
    summary="List derived monitoring seeds for a brand/profile",
)
def list_brand_seeds(
    brand_id: UUID,
    db: Session = Depends(get_db),
):
    repo = MonitoredBrandRepository(db)
    brand = repo.get(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    ensure_monitoring_profile_integrity(repo, brand)
    db.commit()
    return BrandSeedListResponse(
        items=[BrandSeedResponse.model_validate(item) for item in brand.seeds],
        total=len(brand.seeds),
    )


def _run_scan_in_background(brand_id: UUID, tld: str | None, force_full: bool) -> None:
    """Execute similarity scan in a background thread."""
    db = SessionLocal()
    try:
        from app.models.monitored_brand import MonitoredBrand
        from app.services.use_cases.run_similarity_scan import (
            run_similarity_scan,
            run_similarity_scan_all,
        )

        brand = db.get(MonitoredBrand, brand_id)
        if not brand:
            logger.error("Brand %s not found for background scan", brand_id)
            return

        ensure_monitoring_profile_integrity(MonitoredBrandRepository(db), brand)
        db.commit()

        if tld:
            run_similarity_scan(db, brand, tld, force_full=force_full)
        else:
            run_similarity_scan_all(db, brand, force_full=force_full)
    except Exception:
        logger.exception("Background scan failed for brand=%s", brand_id)
    finally:
        db.close()


@router.post(
    "/{brand_id}/scan",
    response_model=ScanSummaryResponse,
    status_code=202,
    summary="Trigger a similarity scan for a brand",
)
def trigger_scan(
    brand_id: UUID,
    tld: str | None = Query(None, description="Specific TLD to scan"),
    force_full: bool = Query(
        False,
        description="Reprocess current domains for the target TLDs and reconcile old matches",
    ),
    db: Session = Depends(get_db),
):
    repo = MonitoredBrandRepository(db)
    brand = repo.get(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    # Dispatch to background thread
    thread = threading.Thread(
        target=_run_scan_in_background,
        args=(brand_id, tld, force_full),
        daemon=True,
    )
    thread.start()

    # Return immediate response
    tlds = [tld] if tld else (brand.tld_scope or ["net", "org", "info"])
    results = [
        ScanResultResponse(
            brand_id=brand_id,
            tld=t,
            candidates=0,
            matched=0,
            removed=0,
            status="queued",
        )
        for t in tlds
    ]
    return ScanSummaryResponse(results=results)
