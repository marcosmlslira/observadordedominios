"""Pydantic schemas for ingestion endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


# ── Request ─────────────────────────────────────────────────
class TriggerSyncRequest(BaseModel):
    tld: str = Field(..., min_length=2, max_length=24, pattern=r"^[a-z0-9-]+$")
    force: bool = False


class CzdsPolicyUpdateRequest(BaseModel):
    tlds: list[str] = Field(default_factory=list)

    @field_validator("tlds")
    @classmethod
    def normalize_tlds(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for raw_tld in value:
            tld = raw_tld.strip().lower().lstrip(".")
            if not tld:
                continue
            if len(tld) < 2 or len(tld) > 24:
                raise ValueError(f"Invalid TLD length: {raw_tld}")
            if not all(char.isalnum() or char == "-" for char in tld):
                raise ValueError(f"Invalid TLD format: {raw_tld}")
            if tld in seen:
                continue
            seen.add(tld)
            normalized.append(tld)

        if not normalized:
            raise ValueError("At least one TLD must be provided")

        return normalized


# ── Responses ───────────────────────────────────────────────
class TriggerSyncResponse(BaseModel):
    run_id: UUID
    status: str


class CzdsPolicyItemResponse(BaseModel):
    tld: str
    is_enabled: bool
    priority: int
    cooldown_hours: int
    failure_count: int = 0
    last_error_code: int | None = None
    last_error_at: datetime | None = None
    suspended_until: datetime | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


class CzdsPolicyResponse(BaseModel):
    source: str
    tlds: list[str]
    items: list[CzdsPolicyItemResponse]


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
    mode: str | None = None
    status_hint: str | None = None
    next_expected_run_hint: str | None = None


class TldCoverageResponse(BaseModel):
    tld: str
    effective_source: str
    czds_available: bool
    ct_enabled: bool
    bulk_status: str
    fallback_reason: str | None = None
    priority_group: str
    last_ct_stream_seen_at: datetime | None = None
    last_crtsh_success_at: datetime | None = None



class CheckpointResponse(BaseModel):
    source: str
    tld: str
    last_successful_run_id: UUID | None = None
    last_successful_run_at: datetime | None = None

    model_config = {"from_attributes": True}


class ErrorResponse(BaseModel):
    error: str


# ── CZDS Policy Patch/Reorder ─────────────────────────────
class CzdsPolicyPatchRequest(BaseModel):
    is_enabled: bool | None = None
    priority: int | None = None
    cooldown_hours: int | None = None


class CzdsPolicyReorderRequest(BaseModel):
    tlds: list[str]  # desired order → priority = index + 1


# ── Cycle Status ──────────────────────────────────────────
class CycleStatusResponse(BaseModel):
    is_active: bool
    total_tlds: int
    completed_tlds: int
    failed_tlds: int
    skipped_tlds: int
    current_tld: str | None
    cycle_started_at: datetime | None
    estimated_completion_at: datetime | None
    avg_tld_duration_seconds: float | None


class ScheduleEntry(BaseModel):
    source: str
    cron_expression: str
    next_run_at: str | None
    mode: str  # "cron" | "realtime" | "manual"


class HealthSummary(BaseModel):
    total_tlds_enabled: int
    tlds_ok: int
    tlds_suspended: int
    tlds_failing: int


class IngestionCycleStatusResponse(BaseModel):
    czds_cycle: CycleStatusResponse
    schedules: list[ScheduleEntry]
    health: HealthSummary
