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
    bulk_job_status: str | None = None
    bulk_chunks_total: int = 0
    bulk_chunks_done: int = 0
    bulk_chunks_error: int = 0
    bulk_chunks_pending: int = 0


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


class CtBulkJobResponse(BaseModel):
    job_id: UUID
    status: str
    requested_tlds: list[str]
    resolved_tlds: list[str]
    priority_tlds: list[str]
    dry_run: bool
    initiated_by: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str | None = None
    total_chunks: int = 0
    pending_chunks: int = 0
    running_chunks: int = 0
    done_chunks: int = 0
    error_chunks: int = 0
    total_raw_domains: int = 0
    total_inserted_domains: int = 0


class CtBulkChunkResponse(BaseModel):
    chunk_id: UUID
    job_id: UUID
    target_tld: str
    chunk_key: str
    query_pattern: str
    prefix: str
    depth: int
    status: str
    attempt_count: int
    last_error_type: str | None = None
    last_error_excerpt: str | None = None
    next_retry_at: datetime | None = None
    raw_domains: int = 0
    inserted_domains: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


class CtBulkJobCreateRequest(BaseModel):
    tlds: list[str] = Field(default_factory=list)
    dry_run: bool = False

    @field_validator("tlds")
    @classmethod
    def normalize_bulk_tlds(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_tld in value:
            tld = raw_tld.strip().lower().lstrip(".")
            if not tld:
                continue
            if tld in seen:
                continue
            seen.add(tld)
            normalized.append(tld)
        return normalized


class CheckpointResponse(BaseModel):
    source: str
    tld: str
    last_successful_run_id: UUID | None = None
    last_successful_run_at: datetime | None = None

    model_config = {"from_attributes": True}


class ErrorResponse(BaseModel):
    error: str
