"""CZDS ingestion API router — trigger sync and check run status."""

from __future__ import annotations

import logging
import threading
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin

from app.infra.db.session import SessionLocal, get_db
from app.core.config import settings
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.schemas.czds_ingestion import (
    ErrorResponse,
    RunStatusResponse,
    TriggerSyncRequest,
    TriggerSyncResponse,
)
from app.services.use_cases.sync_czds_tld import (
    CooldownActiveError,
    SyncAlreadyRunningError,
    sync_czds_tld,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/czds",
    tags=["CZDS Ingestion"],
    dependencies=[Depends(get_current_admin)],
)


def _run_sync_in_background(tld: str, force: bool, run_id: UUID) -> None:
    """Execute the sync in a background thread with its own DB session."""
    db = SessionLocal()
    try:
        sync_czds_tld(db, tld, force=force, run_id=run_id)
    except Exception:
        logger.exception("Background sync failed for TLD=%s", tld)
    finally:
        db.close()


@router.post(
    "/trigger-sync",
    response_model=TriggerSyncResponse,
    status_code=202,
    responses={409: {"model": ErrorResponse}},
    summary="Trigger a CZDS zone sync for a TLD",
)
def trigger_sync(
    body: TriggerSyncRequest,
    db: Session = Depends(get_db),
):
    """
    Queue a zone file sync for the given TLD.

    Returns 202 with the run_id if accepted.
    Returns 409 if a sync is already running for this TLD.
    """
    run_repo = IngestionRunRepository(db)

    stale_runs = run_repo.recover_stale_runs(
        "czds",
        body.tld,
        stale_after_minutes=settings.CZDS_RUNNING_STALE_MINUTES,
    )
    if stale_runs:
        db.commit()
        logger.warning(
            "Recovered %d stale runs before triggering sync for TLD=%s",
            len(stale_runs),
            body.tld,
        )

    # Pre-flight check
    if run_repo.has_running_run("czds", body.tld):
        raise HTTPException(
            status_code=409,
            detail=f"Sync already running for TLD={body.tld}",
        )

    # Create the run record first so we can return the ID
    run = run_repo.create_run("czds", body.tld)
    db.commit()

    # Dispatch the actual work to a background thread
    thread = threading.Thread(
        target=_run_sync_in_background,
        args=(body.tld, body.force, run.id),
        daemon=True,
    )
    thread.start()

    return TriggerSyncResponse(run_id=run.id, status="queued")


@router.get(
    "/runs",
    response_model=list[RunStatusResponse],
    summary="List all recent ingestion runs",
)
def list_runs(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Return a list of ingestion runs, ordered by newest first."""
    run_repo = IngestionRunRepository(db)
    runs = run_repo.list_runs(limit=limit, offset=offset)

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
    summary="Get the status of an ingestion run",
)
def get_run_status(
    run_id: UUID,
    db: Session = Depends(get_db),
):
    """Return current status and metrics for a specific ingestion run."""
    run_repo = IngestionRunRepository(db)
    run = run_repo.get_run(run_id)

    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    # Build artifact key if available
    artifact_key = None
    if run.artifact_id:
        from app.models.zone_file_artifact import ZoneFileArtifact
        artifact = db.get(ZoneFileArtifact, run.artifact_id)
        if artifact:
            artifact_key = artifact.object_key

    return RunStatusResponse(
        run_id=run.id,
        tld=run.tld,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        domains_seen=run.domains_seen or 0,
        domains_inserted=run.domains_inserted or 0,
        domains_reactivated=run.domains_reactivated or 0,
        domains_deleted=run.domains_deleted or 0,
        artifact_key=artifact_key,
        error_message=run.error_message,
    )
