"""Similarity matches API — query matches and review workflow."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin

from app.infra.db.session import get_db
from app.models.match_state_snapshot import MatchStateSnapshot
from app.models.monitoring_event import MonitoringEvent
from app.models.similarity_match import SimilarityMatch as SimilarityMatchModel
from app.repositories.match_state_snapshot_repository import MatchStateSnapshotRepository
from app.repositories.monitoring_event_repository import MonitoringEventRepository
from app.repositories.similarity_repository import SimilarityRepository
from app.schemas.monitoring import (
    EventListResponse,
    EventResponse,
    MatchSnapshotListResponse,
    MatchSnapshotResponse,
    SignalSchema,
)
from app.schemas.similarity import (
    MarkOwnedRequest,
    MatchListResponse,
    MatchResponse,
    SimilarityHealthResponse,
    SimilaritySearchRequest,
    SimilaritySearchResponse,
    UpdateMatchStatusRequest,
)
from app.services.similarity_scan_jobs import serialize_scan_job
from app.services.use_cases.search_similarity import (
    InvalidSimilarityQuery,
    build_similarity_error_detail,
    get_similarity_search_health,
    search_similarity_domains,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1",
    tags=["Similarity"],
    dependencies=[Depends(get_current_admin)],
)


@router.post(
    "/similarity/search",
    response_model=SimilaritySearchResponse,
    summary="Search similar domains synchronously",
)
def search_similarity(
    body: SimilaritySearchRequest,
    db: Session = Depends(get_db),
):
    try:
        return search_similarity_domains(db, body)
    except InvalidSimilarityQuery as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Similarity search failed")
        raise HTTPException(
            status_code=503,
            detail=build_similarity_error_detail(str(exc) or "similarity_search_failed"),
        ) from exc


@router.get(
    "/similarity/health",
    response_model=SimilarityHealthResponse,
    summary="Health and lightweight telemetry for similarity search",
)
def similarity_health():
    return get_similarity_search_health()


@router.get(
    "/brands/{brand_id}/matches",
    summary="List similarity matches for a brand",
)
def list_matches(
    brand_id: UUID,
    status: str | None = Query(None, description="Filter by status: new, reviewing, dismissed, confirmed_threat"),
    risk_level: str | None = Query(None, description="Filter by risk: low, medium, high, critical"),
    attention_bucket: str | None = Query(
        None,
        description="Filter by actionability bucket: immediate_attention, defensive_gap, watchlist",
    ),
    bucket: str | None = Query(None, description="Filter by derived_bucket from snapshot"),
    exclude_auto_dismissed: bool = Query(True, description="Exclude auto-dismissed matches"),
    include_llm: bool = Query(False, description="Include derived snapshot fields and LLM assessment"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    if include_llm:
        snapshot_repo = MatchStateSnapshotRepository(db)
        effective_bucket = bucket or attention_bucket
        snapshots = snapshot_repo.list_for_brand(
            brand_id,
            bucket=effective_bucket,
            exclude_auto_dismissed=exclude_auto_dismissed,
            limit=limit,
            offset=offset,
        )
        match_ids = [s.match_id for s in snapshots]
        matches_by_id: dict = {}
        if match_ids:
            rows = db.query(SimilarityMatchModel).filter(
                SimilarityMatchModel.id.in_(match_ids)
            ).all()
            matches_by_id = {m.id: m for m in rows}

        items = []
        for snap in snapshots:
            m = matches_by_id.get(snap.match_id)
            if m is None:
                continue
            items.append(MatchSnapshotResponse(
                id=m.id,
                brand_id=m.brand_id,
                domain_name=m.domain_name,
                tld=m.tld,
                label=m.label,
                score_final=m.score_final,
                attention_bucket=m.attention_bucket,
                matched_rule=m.matched_rule,
                auto_disposition=m.auto_disposition,
                auto_disposition_reason=m.auto_disposition_reason,
                first_detected_at=m.first_detected_at,
                domain_first_seen=m.domain_first_seen,
                derived_score=snap.derived_score,
                derived_bucket=snap.derived_bucket,
                derived_risk=snap.derived_risk,
                derived_disposition=snap.derived_disposition,
                active_signals=[SignalSchema(**s) for s in (snap.active_signals or [])],
                signal_codes=list(snap.signal_codes or []),
                llm_assessment=snap.llm_assessment,
                state_fingerprint=snap.state_fingerprint,
                last_derived_at=snap.last_derived_at,
            ))

        # Count mirrors same filters as list_for_brand to avoid mismatch
        count_q = db.query(MatchStateSnapshot).filter(
            MatchStateSnapshot.brand_id == brand_id
        )
        if effective_bucket:
            count_q = count_q.filter(MatchStateSnapshot.derived_bucket == effective_bucket)
        if exclude_auto_dismissed:
            count_q = count_q.join(
                SimilarityMatchModel,
                MatchStateSnapshot.match_id == SimilarityMatchModel.id,
            ).filter(SimilarityMatchModel.auto_disposition.is_(None))
        total = count_q.count()

        repo_legacy = SimilarityRepository(db)
        active_job = repo_legacy.get_active_scan_job_for_brand(brand_id)
        latest_job = repo_legacy.get_latest_scan_job_for_brand(brand_id)
        return MatchSnapshotListResponse(
            items=items,
            total=total,
            active_scan=serialize_scan_job(active_job) if active_job else None,
            last_scan=serialize_scan_job(latest_job) if latest_job else None,
        )

    # Legacy path: no snapshot data requested
    repo = SimilarityRepository(db)
    matches = repo.list_matches(
        brand_id,
        status=status,
        risk_level=risk_level,
        attention_bucket=attention_bucket,
        limit=limit,
        offset=offset,
    )
    total = repo.count_matches(
        brand_id,
        status=status,
        risk_level=risk_level,
        attention_bucket=attention_bucket,
    )
    active_job = repo.get_active_scan_job_for_brand(brand_id)
    latest_job = repo.get_latest_scan_job_for_brand(brand_id)
    return MatchListResponse(
        items=matches,
        total=total,
        active_scan=serialize_scan_job(active_job) if active_job else None,
        last_scan=serialize_scan_job(latest_job) if latest_job else None,
    )


@router.get(
    "/brands/{brand_id}/self-owned-matches",
    response_model=MatchSnapshotListResponse,
    summary="List company-owned matches detected for a brand",
)
def list_self_owned_matches(
    brand_id: UUID,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    snapshot_repo = MatchStateSnapshotRepository(db)
    snapshots = snapshot_repo.list_self_owned_for_brand(brand_id, limit=limit, offset=offset)
    match_ids = [s.match_id for s in snapshots]
    matches_by_id: dict = {}
    if match_ids:
        rows = db.query(SimilarityMatchModel).filter(SimilarityMatchModel.id.in_(match_ids)).all()
        matches_by_id = {m.id: m for m in rows}

    items = []
    for snap in snapshots:
        m = matches_by_id.get(snap.match_id)
        if m is None:
            continue
        items.append(MatchSnapshotResponse(
            id=m.id,
            brand_id=m.brand_id,
            domain_name=m.domain_name,
            tld=m.tld,
            label=m.label,
            score_final=m.score_final,
            attention_bucket=m.attention_bucket,
            matched_rule=m.matched_rule,
            auto_disposition=m.auto_disposition,
            auto_disposition_reason=m.auto_disposition_reason,
            first_detected_at=m.first_detected_at,
            domain_first_seen=m.domain_first_seen,
            derived_score=snap.derived_score,
            derived_bucket=snap.derived_bucket,
            derived_risk=snap.derived_risk,
            derived_disposition=snap.derived_disposition,
            active_signals=[SignalSchema(**s) for s in (snap.active_signals or [])],
            signal_codes=list(snap.signal_codes or []),
            llm_assessment=snap.llm_assessment,
            state_fingerprint=snap.state_fingerprint,
            last_derived_at=snap.last_derived_at,
        ))

    total = snapshot_repo.count_self_owned_for_brand(brand_id)
    return MatchSnapshotListResponse(items=items, total=total)


@router.get(
    "/matches/{match_id}/events",
    response_model=EventListResponse,
    summary="Get monitoring event timeline for a match",
)
def get_match_events(
    match_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    repo = SimilarityRepository(db)
    match = repo.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    event_repo = MonitoringEventRepository(db)
    events = event_repo.list_for_match(match_id=match_id, limit=limit, offset=offset)
    total = db.query(MonitoringEvent).filter(
        MonitoringEvent.match_id == match_id
    ).count()

    return EventListResponse(
        items=[EventResponse.model_validate(e) for e in events],
        total=total,
    )


@router.get(
    "/matches",
    response_model=MatchSnapshotListResponse,
    summary="List all match snapshots across brands (global threat view)",
)
def list_all_matches(
    bucket: str | None = Query(None, description="Filter by derived_bucket"),
    brand_id: UUID | None = Query(None, description="Filter by brand"),
    exclude_auto_dismissed: bool = Query(True, description="Exclude auto-dismissed matches"),
    verified_only: bool = Query(False, description="Return only verified/self-owned matches"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    snapshot_repo = MatchStateSnapshotRepository(db)
    snapshots = snapshot_repo.list_global(
        bucket=bucket,
        brand_id=brand_id,
        exclude_auto_dismissed=exclude_auto_dismissed,
        verified_only=verified_only,
        limit=limit,
        offset=offset,
    )
    total = snapshot_repo.count_global(
        bucket=bucket,
        brand_id=brand_id,
        exclude_auto_dismissed=exclude_auto_dismissed,
        verified_only=verified_only,
    )
    match_ids = [s.match_id for s in snapshots]
    matches_by_id: dict = {}
    if match_ids:
        rows = db.query(SimilarityMatchModel).filter(
            SimilarityMatchModel.id.in_(match_ids)
        ).all()
        matches_by_id = {m.id: m for m in rows}

    items = []
    for snap in snapshots:
        m = matches_by_id.get(snap.match_id)
        if m is None:
            continue
        items.append(MatchSnapshotResponse(
            id=m.id,
            brand_id=m.brand_id,
            domain_name=m.domain_name,
            tld=m.tld,
            label=m.label,
            score_final=m.score_final,
            attention_bucket=m.attention_bucket,
            matched_rule=m.matched_rule,
            auto_disposition=m.auto_disposition,
            auto_disposition_reason=m.auto_disposition_reason,
            first_detected_at=m.first_detected_at,
            domain_first_seen=m.domain_first_seen,
            status=m.status,
            self_owned=m.self_owned,
            ownership_classification=m.ownership_classification,
            derived_score=snap.derived_score,
            derived_bucket=snap.derived_bucket,
            derived_risk=snap.derived_risk,
            derived_disposition=snap.derived_disposition,
            active_signals=[SignalSchema(**s) for s in (snap.active_signals or [])],
            signal_codes=list(snap.signal_codes or []),
            llm_assessment=snap.llm_assessment,
            state_fingerprint=snap.state_fingerprint,
            last_derived_at=snap.last_derived_at,
        ))

    return MatchSnapshotListResponse(items=items, total=total)


@router.get(
    "/matches/{match_id}",
    response_model=MatchResponse,
    summary="Get a specific similarity match",
)
def get_match(
    match_id: UUID,
    db: Session = Depends(get_db),
):
    repo = SimilarityRepository(db)
    match = repo.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")
    return match


@router.patch(
    "/matches/{match_id}",
    response_model=MatchResponse,
    summary="Update match status (review workflow)",
)
def update_match_status(
    match_id: UUID,
    body: UpdateMatchStatusRequest,
    db: Session = Depends(get_db),
):
    repo = SimilarityRepository(db)
    match = repo.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # TODO: Get reviewed_by from auth context
    repo.update_match_status(
        match,
        status=body.status,
        notes=body.notes,
    )
    db.commit()
    return match


@router.post(
    "/matches/{match_id}/mark-owned",
    response_model=MatchResponse,
    summary="Mark a match as a company-owned domain (confirms as self_owned, dismisses it)",
)
def mark_match_owned(
    match_id: UUID,
    body: MarkOwnedRequest,
    db: Session = Depends(get_db),
):
    repo = SimilarityRepository(db)
    match = repo.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    repo.mark_match_owned(match, add_to_profile=body.add_to_profile)
    db.commit()
    return match


@router.get(
    "/similarity/metrics",
    summary="Operational metrics: match counts by bucket, disposition, brand, and last scan job",
)
def get_similarity_metrics(
    db: Session = Depends(get_db),
):
    repo = SimilarityRepository(db)
    return repo.get_operational_metrics()


@router.get(
    "/similarity/trends",
    summary="Match discovery trends — daily counts for the last N days",
)
def get_similarity_trends(
    days: int = Query(30, ge=7, le=90, description="Look-back window in days"),
    db: Session = Depends(get_db),
):
    repo = SimilarityRepository(db)
    return repo.get_discovery_trends(days=days)
