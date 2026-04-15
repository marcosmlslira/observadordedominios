"""Monitored brands API — CRUD + trigger similarity scan."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin

from app.infra.db.session import get_db
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
from app.repositories.brand_domain_health_repository import BrandDomainHealthRepository
from app.repositories.monitoring_cycle_repository import MonitoringCycleRepository
from app.models.monitoring_cycle import MonitoringCycle
from app.schemas.monitoring import (
    BrandHealthResponse,
    CycleListResponse,
    CycleResponse,
    CycleSummarySchema,
    DomainCheckDetailSchema,
    DomainHealthCheckSchema,
    ThreatCountsSchema,
    MonitoringSummarySchema,
)
from app.schemas.similarity import ScanResultResponse, ScanSummaryResponse
from app.services.monitoring_query_service import MonitoringQueryService
from app.services.similarity_scan_jobs import resolve_effective_scan_tlds, serialize_scan_job
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


def _to_brand_response(brand, monitoring_summary: MonitoringSummarySchema | None = None) -> BrandResponse:
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
        monitoring_summary=monitoring_summary,
    )


def _build_monitoring_summary(raw: dict) -> MonitoringSummarySchema:
    latest_cycle = None
    if raw["latest_cycle"]:
        latest_cycle = CycleSummarySchema(**raw["latest_cycle"])
    return MonitoringSummarySchema(
        latest_cycle=latest_cycle,
        threat_counts=ThreatCountsSchema(**raw["threat_counts"]),
        overall_health=raw["overall_health"],
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

    # Auto-queue an initial full similarity scan so the worker picks it up
    # within 15 seconds instead of waiting for the 09:00 UTC daily cron.
    if brand.seeds:
        try:
            similarity_repo = SimilarityRepository(db)
            effective_tlds = resolve_effective_scan_tlds(db, brand, None)
            if effective_tlds:
                similarity_repo.create_scan_job(
                    brand_id=brand.id,
                    requested_tld=None,
                    effective_tlds=effective_tlds,
                    force_full=True,
                    initiated_by="auto:brand_creation",
                )
                db.commit()
                logger.info(
                    "Auto-queued initial scan for new brand=%s tlds=%d",
                    brand.brand_name,
                    len(effective_tlds),
                )
        except Exception:
            logger.exception(
                "Failed to auto-queue initial scan for new brand=%s", brand.brand_name
            )

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
    svc = MonitoringQueryService(db)
    hydrated = []
    for brand in brands:
        ensure_monitoring_profile_integrity(repo, brand)
        raw = svc.get_monitoring_summary(brand.id)
        summary = _build_monitoring_summary(raw)
        hydrated.append(_to_brand_response(brand, summary))
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
    svc = MonitoringQueryService(db)
    raw = svc.get_monitoring_summary(brand.id)
    summary = _build_monitoring_summary(raw)
    return _to_brand_response(brand, summary)


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
        trusted_registrants=body.trusted_registrants.model_dump() if body.trusted_registrants is not None else None,
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
    "/{brand_id}/health",
    response_model=BrandHealthResponse,
    summary="Get health check results for all official domains of a brand",
)
def get_brand_health(
    brand_id: UUID,
    db: Session = Depends(get_db),
):
    repo = MonitoredBrandRepository(db)
    brand = repo.get(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    health_repo = BrandDomainHealthRepository(db)
    domains_with_health = []
    for dom in brand.domains:
        if not dom.is_active:
            continue
        health = health_repo.get_by_domain(dom.id)
        domains_with_health.append(_build_domain_health_schema(dom, health))

    return BrandHealthResponse(domains=domains_with_health)


def _build_domain_health_schema(domain, health) -> DomainHealthCheckSchema:
    if health is None:
        return DomainHealthCheckSchema(
            domain_id=domain.id,
            domain_name=domain.domain_name,
            is_primary=domain.is_primary,
            overall_status="unknown",
        )
    return DomainHealthCheckSchema(
        domain_id=domain.id,
        domain_name=domain.domain_name,
        is_primary=domain.is_primary,
        overall_status=health.overall_status,
        dns=DomainCheckDetailSchema(ok=health.dns_ok) if health.dns_ok is not None else None,
        ssl=DomainCheckDetailSchema(
            ok=health.ssl_ok,
            details={"days_remaining": health.ssl_days_remaining} if health.ssl_days_remaining is not None else None,
        ) if health.ssl_ok is not None else None,
        email_security=DomainCheckDetailSchema(
            ok=health.email_security_ok,
            details={"spoofing_risk": health.spoofing_risk} if health.spoofing_risk else None,
        ) if health.email_security_ok is not None else None,
        headers=DomainCheckDetailSchema(
            ok=health.headers_score == "good",
            details={"score": health.headers_score} if health.headers_score else None,
        ) if health.headers_score is not None else None,
        takeover=DomainCheckDetailSchema(ok=not health.takeover_risk) if health.takeover_risk is not None else None,
        blacklist=DomainCheckDetailSchema(ok=not health.blacklisted) if health.blacklisted is not None else None,
        safe_browsing=DomainCheckDetailSchema(ok=not health.safe_browsing_hit) if health.safe_browsing_hit is not None else None,
        urlhaus=DomainCheckDetailSchema(ok=not health.urlhaus_hit) if health.urlhaus_hit is not None else None,
        phishtank=DomainCheckDetailSchema(ok=not health.phishtank_hit) if health.phishtank_hit is not None else None,
        suspicious_page=DomainCheckDetailSchema(ok=not health.suspicious_content) if health.suspicious_content is not None else None,
        last_check_at=health.last_check_at,
    )


@router.get(
    "/{brand_id}/cycles",
    response_model=CycleListResponse,
    summary="Get monitoring cycle history for a brand",
)
def get_brand_cycles(
    brand_id: UUID,
    limit: int = Query(30, ge=1, le=90),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    repo = MonitoredBrandRepository(db)
    brand = repo.get(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    cycle_repo = MonitoringCycleRepository(db)
    cycles = cycle_repo.list_for_brand(brand_id, limit=limit, offset=offset)
    total = db.query(MonitoringCycle).filter(
        MonitoringCycle.brand_id == brand_id
    ).count()
    return CycleListResponse(
        items=[CycleResponse.model_validate(c) for c in cycles],
        total=total,
    )


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
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    repo = MonitoredBrandRepository(db)
    brand = repo.get(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    similarity_repo = SimilarityRepository(db)
    active_job = similarity_repo.get_active_scan_job_for_brand(brand_id)
    if active_job:
        serialized = serialize_scan_job(active_job)
        return ScanSummaryResponse(
            job_id=serialized.job_id,
            brand_id=serialized.brand_id,
            requested_tld=serialized.requested_tld,
            status=serialized.status,
            queued_at=serialized.queued_at,
            tlds_effective=serialized.tlds_effective,
            results=serialized.results,
        )

    effective_tlds = resolve_effective_scan_tlds(db, brand, tld)
    if not effective_tlds:
        raise HTTPException(status_code=400, detail="No effective TLDs resolved for scan")

    job = similarity_repo.create_scan_job(
        brand_id=brand_id,
        requested_tld=tld,
        effective_tlds=effective_tlds,
        force_full=force_full,
        initiated_by=current_admin,
    )
    db.commit()

    serialized = serialize_scan_job(job)
    return ScanSummaryResponse(
        job_id=serialized.job_id,
        brand_id=serialized.brand_id,
        requested_tld=serialized.requested_tld,
        status=serialized.status,
        queued_at=serialized.queued_at,
        tlds_effective=serialized.tlds_effective,
        results=serialized.results,
    )
