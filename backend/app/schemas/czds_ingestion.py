"""Pydantic schemas for ingestion endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Request ─────────────────────────────────────────────────
class TriggerSyncRequest(BaseModel):
    tld: str = Field(..., min_length=2, max_length=24, pattern=r"^[a-z0-9-]+$")
    force: bool = False


# ── Responses ───────────────────────────────────────────────
class TriggerSyncResponse(BaseModel):
    run_id: UUID
    status: str


class RunStatusResponse(BaseModel):
    run_id: UUID
    source: str = "czds"
    tld: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    domains_seen: int = 0
    domains_inserted: int = 0
    domains_reactivated: int = 0
    domains_deleted: int = 0
    artifact_key: str | None = None
    error_message: str | None = None

    model_config = {"from_attributes": True}


class SourceSummaryResponse(BaseModel):
    source: str
    total_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    running_now: int = 0
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_status: str | None = None
    total_domains_seen: int = 0
    total_domains_inserted: int = 0


class CheckpointResponse(BaseModel):
    source: str
    tld: str
    last_successful_run_id: UUID | None = None
    last_successful_run_at: datetime | None = None

    model_config = {"from_attributes": True}


class ErrorResponse(BaseModel):
    error: str
