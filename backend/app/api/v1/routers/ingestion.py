"""Generic ingestion API — runs, health summary, and checkpoints for ALL sources."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin
from app.infra.db.session import get_db
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.schemas.czds_ingestion import (
    CheckpointResponse,
    ErrorResponse,
    RunStatusResponse,
    SourceSummaryResponse,
)

router = APIRouter(
    prefix="/v1/ingestion",
    tags=["Ingestion"],
    dependencies=[Depends(get_current_admin)],
)


@router.get(
    "/runs",
    response_model=list[RunStatusResponse],
    summary="List ingestion runs from all sources",
)
def list_runs(
    limit: int = 50,
    offset: int = 0,
    source: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """Return ingestion runs, optionally filtered by source and/or status."""
    run_repo = IngestionRunRepository(db)
    runs = run_repo.list_runs(limit=limit, offset=offset, source=source, status=status)

    return [
        RunStatusResponse(
            run_id=run.id,
            source=run.source,
            tld=run.tld,
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            domains_seen=run.domains_seen or 0,
            domains_inserted=run.domains_inserted or 0,
            domains_reactivated=run.domains_reactivated or 0,
            domains_deleted=run.domains_deleted or 0,
            artifact_key=None,
            error_message=run.error_message,
        )
        for run in runs
    ]


@router.get(
    "/runs/{run_id}",
    response_model=RunStatusResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get a specific ingestion run",
)
def get_run(
    run_id: UUID,
    db: Session = Depends(get_db),
):
    run_repo = IngestionRunRepository(db)
    run = run_repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return RunStatusResponse(
        run_id=run.id,
        source=run.source,
        tld=run.tld,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        domains_seen=run.domains_seen or 0,
        domains_inserted=run.domains_inserted or 0,
        domains_reactivated=run.domains_reactivated or 0,
        domains_deleted=run.domains_deleted or 0,
        artifact_key=None,
        error_message=run.error_message,
    )


@router.get(
    "/summary",
    response_model=list[SourceSummaryResponse],
    summary="Aggregated health stats per ingestion source",
)
def get_summary(
    db: Session = Depends(get_db),
):
    """Per-source aggregation: total runs, success/fail counts, last run, totals."""
    run_repo = IngestionRunRepository(db)
    return [SourceSummaryResponse(**row) for row in run_repo.get_source_summary()]


@router.get(
    "/checkpoints",
    response_model=list[CheckpointResponse],
    summary="Last successful run per source/TLD pair",
)
def list_checkpoints(
    source: str | None = None,
    db: Session = Depends(get_db),
):
    run_repo = IngestionRunRepository(db)
    return [
        CheckpointResponse(
            source=cp.source,
            tld=cp.tld,
            last_successful_run_id=cp.last_successful_run_id,
            last_successful_run_at=cp.last_successful_run_at,
        )
        for cp in run_repo.list_checkpoints(source=source)
    ]
