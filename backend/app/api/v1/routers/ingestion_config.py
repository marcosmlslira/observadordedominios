"""Ingestion config API — cron management, generic TLD policy, and manual triggers."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin
from app.infra.db.session import get_db
from app.repositories.ingestion_config_repository import IngestionConfigRepository
from app.schemas.ingestion_config import (
    CronUpdateRequest,
    IngestionConfigPatchRequest,
    ORDERING_MODE_SOURCES,
    SourceConfigResponse,
    TldPolicyBulkRequest,
    TldPolicyPatchRequest,
    TldPolicyResponse,
)
from app.services.ingestion_config_service import InvalidSourceError, validate_source

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


def _validate_source_or_404(source: str) -> None:
    try:
        validate_source(source)
    except InvalidSourceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
