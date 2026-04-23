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
from app.repositories.czds_policy_repository import CzdsPolicyRepository
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.schemas.czds_ingestion import (
    CzdsPolicyItemResponse,
    CzdsPolicyPatchRequest,
    CzdsPolicyReorderRequest,
    CzdsPolicyResponse,
    CzdsPolicyUpdateRequest,
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


def _env_fallback_tlds() -> list[str]:
    raw = settings.CZDS_ENABLED_TLDS
    if not raw:
        return []
    return [t.strip().lower() for t in raw.split(",") if t.strip()]


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
    summary="[DEPRECATED] Trigger a CZDS zone sync for a TLD",
    deprecated=True,
)
def trigger_sync(
    body: TriggerSyncRequest,
    db: Session = Depends(get_db),
):
    """
    **DEPRECATED**: Use the ingestion package orchestrator instead.
    This endpoint uses the legacy sync pipeline and will be removed in a future release.

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
    "/policy",
    response_model=CzdsPolicyResponse,
    summary="Get the active CZDS TLD policy",
)
def get_policy(
    db: Session = Depends(get_db),
):
    repo = CzdsPolicyRepository(db)
    active_items = repo.list_enabled()
    all_items = repo.list_all()

    if all_items:
        return CzdsPolicyResponse(
            source="database",
            tlds=[item.tld for item in active_items],
            items=all_items,
        )

    fallback_tlds = _env_fallback_tlds()
    return CzdsPolicyResponse(
        source="env",
        tlds=fallback_tlds,
        items=[],
    )


@router.put(
    "/policy",
    response_model=CzdsPolicyResponse,
    summary="Replace the active CZDS TLD policy",
)
def replace_policy(
    body: CzdsPolicyUpdateRequest,
    db: Session = Depends(get_db),
):
    repo = CzdsPolicyRepository(db)
    items = repo.replace_enabled_tlds(body.tlds)
    db.commit()

    return CzdsPolicyResponse(
        source="database",
        tlds=[item.tld for item in items],
        items=items,
    )


@router.patch(
    "/policy/{tld}",
    response_model=CzdsPolicyItemResponse,
    summary="Toggle or edit a single TLD policy",
)
def patch_policy(
    tld: str,
    body: CzdsPolicyPatchRequest,
    db: Session = Depends(get_db),
):
    """Apply partial updates to a single TLD policy."""
    fields = body.model_dump(exclude_none=True)
    if not fields:
        raise HTTPException(status_code=422, detail="No fields to update")

    repo = CzdsPolicyRepository(db)
    policy = repo.patch(tld, **fields)
    db.commit()
    return policy


@router.post(
    "/policy/reorder",
    status_code=204,
    summary="Reorder TLD priorities in batch",
)
def reorder_policy(
    body: CzdsPolicyReorderRequest,
    db: Session = Depends(get_db),
):
    """Set priority = index+1 for each TLD in the provided order."""
    repo = CzdsPolicyRepository(db)
    repo.update_priorities(body.tlds)
    db.commit()


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
