"""Similarity matches API — query matches and review workflow."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin

from app.infra.db.session import get_db
from app.repositories.similarity_repository import SimilarityRepository
from app.schemas.similarity import (
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
    response_model=MatchListResponse,
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
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
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
