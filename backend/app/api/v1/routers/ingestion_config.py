"""Ingestion config API — cron management, generic TLD policy, and manual triggers."""

from __future__ import annotations

import logging
import threading

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin
from app.infra.db.session import SessionLocal, get_db
from app.repositories.ingestion_config_repository import IngestionConfigRepository
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.schemas.ingestion_config import (
    CronUpdateRequest,
    IngestionConfigPatchRequest,
    ORDERING_MODE_SOURCES,
    SourceConfigResponse,
    TldPolicyBulkRequest,
    TldPolicyPatchRequest,
    TldPolicyResponse,
    TriggerTldRequest,
    TriggerTldResponse,
)
from app.services.ingestion_config_service import InvalidSourceError, validate_source
from app.services.use_cases.sync_czds_tld import (
    CooldownActiveError as CzdsCooldownError,
    SyncAlreadyRunningError as CzdsSyncRunningError,
    sync_czds_tld,
)
from app.services.use_cases.sync_openintel_tld import (
    CooldownActiveError as OpenintelCooldownError,
    CzdsRunningError,
    SnapshotAlreadyIngestedError,
    SnapshotNotFoundError,
    SyncAlreadyRunningError as OpenintelSyncRunningError,
    sync_openintel_tld,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/v1/ingestion",
    tags=["Ingestion Config"],
    dependencies=[Depends(get_current_admin)],
)


@router.get("/config", response_model=list[SourceConfigResponse])
def list_configs(db: Session = Depends(get_db)):
    """List cron config for all sources."""
    repo = IngestionConfigRepository(db)
    return repo.list_configs()


@router.get("/config/{source}", response_model=SourceConfigResponse)
def get_config(source: str, db: Session = Depends(get_db)):
    """Get cron config for a single source."""
    _validate_source_or_404(source)
    repo = IngestionConfigRepository(db)
    cfg = repo.get_config(source)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"No config found for source '{source}'")
    return cfg


@router.patch("/config/{source}", response_model=SourceConfigResponse)
def patch_config(source: str, body: IngestionConfigPatchRequest, db: Session = Depends(get_db)):
    """Patch ordering_mode for a source. Only supported for CZDS."""
    _validate_source_or_404(source)
    if body.ordering_mode is not None and source not in ORDERING_MODE_SOURCES:
        raise HTTPException(
            status_code=422,
            detail=f"ordering_mode is not supported for source '{source}'",
        )
    repo = IngestionConfigRepository(db)
    cfg = repo.patch_config(source, ordering_mode=body.ordering_mode)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"No config found for source '{source}'")
    db.commit()
    return cfg


@router.put("/config/{source}", response_model=SourceConfigResponse)
def update_config(source: str, body: CronUpdateRequest, db: Session = Depends(get_db)):
    """Update (upsert) cron expression for a source."""
    _validate_source_or_404(source)
    repo = IngestionConfigRepository(db)
    cfg = repo.upsert_cron(source, body.cron_expression)
    db.commit()
    return cfg


@router.get("/tld-policy/{source}", response_model=list[TldPolicyResponse])
def list_tld_policies(source: str, db: Session = Depends(get_db)):
    """List all TLD policies for a source."""
    _validate_source_or_404(source)
    repo = IngestionConfigRepository(db)
    return repo.list_tld_policies(source)


@router.patch(
    "/tld-policy/{source}/{tld}",
    response_model=TldPolicyResponse,
)
def patch_tld_policy(
    source: str,
    tld: str,
    body: TldPolicyPatchRequest,
    db: Session = Depends(get_db),
):
    """Enable or disable a single TLD for a source."""
    _validate_source_or_404(source)
    repo = IngestionConfigRepository(db)
    policy = repo.patch_tld(source, tld.lower(), is_enabled=body.is_enabled, priority=body.priority)
    db.commit()
    return policy


@router.put(
    "/tld-policy/{source}",
    response_model=list[TldPolicyResponse],
)
def bulk_upsert_tld_policy(
    source: str,
    body: TldPolicyBulkRequest,
    db: Session = Depends(get_db),
):
    """Bulk upsert TLD policies. Rows not in the payload are unchanged."""
    _validate_source_or_404(source)
    repo = IngestionConfigRepository(db)
    policies = repo.bulk_upsert_tlds(
        source,
        [{"tld": item.tld.lower(), "is_enabled": item.is_enabled} for item in body.tlds],
    )
    db.commit()
    return policies


@router.post(
    "/trigger/{source}/{tld}",
    response_model=TriggerTldResponse,
    status_code=202,
    summary="Trigger manual ingestion for a specific TLD",
)
def trigger_tld(
    source: str,
    tld: str,
    body: TriggerTldRequest,
    db: Session = Depends(get_db),
):
    """Queue an immediate ingestion run for a single TLD.

    Supported sources: czds, openintel.
    Returns 202 with run_id when accepted.
    Returns 409 if a run is already in progress for this TLD.
    Returns 429 if the cooldown window has not elapsed (use force=true to override).
    """
    _validate_source_or_404(source)
    tld = tld.lower()

    if source not in ("czds", "openintel"):
        raise HTTPException(
            status_code=422,
            detail=f"Manual trigger is not supported for source '{source}'",
        )

    run_repo = IngestionRunRepository(db)

    # Recover any stale runs before checking for in-progress
    stale = run_repo.recover_stale_runs(source, tld, stale_after_minutes=120)
    if stale:
        db.commit()

    if run_repo.has_running_run(source, tld):
        raise HTTPException(status_code=409, detail=f"Run already in progress for {source}/{tld}")

    run = run_repo.create_run(source, tld)
    db.commit()
    run_id = run.id

    def _background() -> None:
        bg_db = SessionLocal()
        failure_reason: str | None = None
        skip_reason: str | None = None
        try:
            if source == "czds":
                sync_czds_tld(bg_db, tld, force=body.force, run_id=run_id)
            else:
                sync_openintel_tld(bg_db, tld, force=body.force, run_id=run_id)
        except (SnapshotAlreadyIngestedError, SnapshotNotFoundError) as exc:
            logger.info(
                "OpenINTEL manual trigger skipped for %s/%s: %s",
                source,
                tld,
                exc,
            )
            skip_reason = str(exc)
        except (CzdsCooldownError, OpenintelCooldownError) as exc:
            logger.warning("Cooldown active for %s/%s: %s", source, tld, exc)
            failure_reason = str(exc)
        except (CzdsSyncRunningError, OpenintelSyncRunningError) as exc:
            logger.warning("Sync already running for %s/%s: %s", source, tld, exc)
            failure_reason = str(exc)
        except CzdsRunningError as exc:
            logger.warning("CZDS is running, aborting OpenINTEL trigger for %s: %s", tld, exc)
            failure_reason = str(exc)
        except Exception:
            logger.exception("Background trigger failed for %s/%s", source, tld)
            failure_reason = "Unexpected error during background trigger"
        finally:
            if failure_reason is not None or skip_reason is not None:
                # Finalize the pre-created run so it doesn't stay orphaned in "running".
                try:
                    run_repo = IngestionRunRepository(bg_db)
                    orphan = run_repo.get_run(run_id)
                    if orphan and orphan.status == "running":
                        if failure_reason is not None:
                            run_repo.finish_run(orphan, status="failed", error_message=failure_reason)
                        else:
                            run_repo.finish_run(orphan, status="success", error_message=skip_reason)
                        bg_db.commit()
                except Exception:
                    logger.exception("Failed to mark orphaned run %s as failed", run_id)
            bg_db.close()

    threading.Thread(target=_background, daemon=True).start()

    return TriggerTldResponse(
        run_id=str(run_id),
        source=source,
        tld=tld,
        status="queued",
    )


def _validate_source_or_404(source: str) -> None:
    try:
        validate_source(source)
    except InvalidSourceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
