"""Pydantic schemas for CZDS ingestion endpoints."""

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


class ErrorResponse(BaseModel):
    error: str
