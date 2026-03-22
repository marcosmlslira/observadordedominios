"""Monitored brands API — CRUD + trigger similarity scan."""

from __future__ import annotations

import logging
import threading
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.infra.db.session import SessionLocal, get_db
from app.repositories.monitored_brand_repository import MonitoredBrandRepository
from app.repositories.similarity_repository import SimilarityRepository
from app.schemas.monitored_brand import (
    BrandListResponse,
    BrandResponse,
    CreateBrandRequest,
    UpdateBrandRequest,
)
from app.schemas.similarity import ScanResultResponse, ScanSummaryResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/brands", tags=["Monitored Brands"])

# TODO: Replace with real auth dependency when identity domain is built
PLACEHOLDER_ORG_ID = UUID("00000000-0000-0000-0000-000000000001")


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

    # Derive label from brand_name
    brand_label = body.brand_name.lower().strip().replace(" ", "")

    brand = repo.create(
        organization_id=PLACEHOLDER_ORG_ID,
        brand_name=body.brand_name,
        brand_label=brand_label,
        keywords=body.keywords,
        tld_scope=body.tld_scope,
    )
    db.commit()
    return brand


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
    return BrandListResponse(items=brands, total=len(brands))


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
    return brand


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

    # Derive label if brand_name changed
    brand_label = None
    if body.brand_name:
        brand_label = body.brand_name.lower().strip().replace(" ", "")

    repo.update(
        brand,
        brand_name=body.brand_name,
        brand_label=brand_label,
        keywords=body.keywords,
        tld_scope=body.tld_scope,
        is_active=body.is_active,
    )
    db.commit()
    return brand


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


def _run_scan_in_background(brand_id: UUID, tld: str | None) -> None:
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

        if tld:
            run_similarity_scan(db, brand, tld)
        else:
            run_similarity_scan_all(db, brand)
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
    db: Session = Depends(get_db),
):
    repo = MonitoredBrandRepository(db)
    brand = repo.get(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    # Dispatch to background thread
    thread = threading.Thread(
        target=_run_scan_in_background,
        args=(brand_id, tld),
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
            status="queued",
        )
        for t in tlds
    ]
    return ScanSummaryResponse(results=results)
