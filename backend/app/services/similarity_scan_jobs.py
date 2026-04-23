"""Helpers for manual similarity scan jobs."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.monitored_brand import MonitoredBrand
from app.models.similarity_scan_job import SimilarityScanJob
from app.repositories.domain_repository import list_partition_tlds
from app.schemas.similarity import ScanJobResponse, ScanResultResponse


def resolve_effective_scan_tlds(db: Session, brand: MonitoredBrand, requested_tld: str | None) -> list[str]:
    if requested_tld:
        return [requested_tld]
    if brand.tld_scope:
        return sorted(dict.fromkeys(brand.tld_scope))
    return list_partition_tlds(db)


def serialize_scan_job(job: SimilarityScanJob) -> ScanJobResponse:
    return ScanJobResponse(
        job_id=job.id,
        brand_id=job.brand_id,
        requested_tld=job.requested_tld,
        status=job.status,
        queued_at=job.queued_at,
        started_at=job.started_at,
        finished_at=job.finished_at,
        force_full=bool(job.force_full),
        tlds_effective=list(job.effective_tlds or []),
        last_error=job.last_error,
        results=[
            ScanResultResponse(
                brand_id=job.brand_id,
                tld=tld,
                candidates=int((job.tld_results or {}).get(tld, {}).get("candidates") or 0),
                matched=int((job.tld_results or {}).get(tld, {}).get("matched") or 0),
                removed=int((job.tld_results or {}).get(tld, {}).get("removed") or 0),
                ring_c_candidates=int((job.tld_results or {}).get(tld, {}).get("ring_c_candidates") or 0),
                ring_c_matches=int((job.tld_results or {}).get(tld, {}).get("ring_c_matches") or 0),
                ring_c_limit=int((job.tld_results or {}).get(tld, {}).get("ring_c_limit") or 0),
                status=str((job.tld_results or {}).get(tld, {}).get("status") or "queued"),
                error_message=(job.tld_results or {}).get(tld, {}).get("error_message"),
                started_at=_parse_optional_datetime((job.tld_results or {}).get(tld, {}).get("started_at")),
                finished_at=_parse_optional_datetime((job.tld_results or {}).get(tld, {}).get("finished_at")),
            )
            for tld in list(job.effective_tlds or [])
        ],
    )


def _parse_optional_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
