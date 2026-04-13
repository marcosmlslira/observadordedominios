"""Pydantic schemas for monitoring pipeline API endpoints."""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Cycle ─────────────────────────────────────────────────────

class CycleSummarySchema(BaseModel):
    cycle_date: date
    health_status: str
    scan_status: str
    enrichment_status: str
    new_matches_count: int = 0
    threats_detected: int = 0
    dismissed_count: int = 0

    model_config = {"from_attributes": True}


class ThreatCountsSchema(BaseModel):
    immediate_attention: int = 0
    defensive_gap: int = 0
    watchlist: int = 0


class MonitoringSummarySchema(BaseModel):
    latest_cycle: CycleSummarySchema | None = None
    threat_counts: ThreatCountsSchema
    overall_health: str = "unknown"


class CycleResponse(BaseModel):
    id: UUID
    brand_id: UUID
    organization_id: UUID
    cycle_date: date
    cycle_type: str
    health_status: str
    health_started_at: datetime | None = None
    health_finished_at: datetime | None = None
    scan_status: str
    scan_started_at: datetime | None = None
    scan_finished_at: datetime | None = None
    scan_job_id: UUID | None = None
    enrichment_status: str
    enrichment_started_at: datetime | None = None
    enrichment_finished_at: datetime | None = None
    enrichment_budget: int = 0
    enrichment_total: int = 0
    new_matches_count: int = 0
    escalated_count: int = 0
    dismissed_count: int = 0
    threats_detected: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CycleListResponse(BaseModel):
    items: list[CycleResponse]
    total: int


# ── Health ────────────────────────────────────────────────────

class DomainCheckDetailSchema(BaseModel):
    ok: bool | None = None
    details: dict | None = None


class DomainHealthCheckSchema(BaseModel):
    domain_id: UUID
    domain_name: str
    is_primary: bool
    overall_status: str
    dns: DomainCheckDetailSchema | None = None
    ssl: DomainCheckDetailSchema | None = None
    email_security: DomainCheckDetailSchema | None = None
    headers: DomainCheckDetailSchema | None = None
    takeover: DomainCheckDetailSchema | None = None
    blacklist: DomainCheckDetailSchema | None = None
    safe_browsing: DomainCheckDetailSchema | None = None
    urlhaus: DomainCheckDetailSchema | None = None
    phishtank: DomainCheckDetailSchema | None = None
    suspicious_page: DomainCheckDetailSchema | None = None
    last_check_at: datetime | None = None

    model_config = {"from_attributes": True}


class BrandHealthResponse(BaseModel):
    domains: list[DomainHealthCheckSchema]


# ── Match snapshot ────────────────────────────────────────────

class SignalSchema(BaseModel):
    code: str
    severity: str | None = None
    score_adjustment: float | None = None
    description: str | None = None
    source_tool: str | None = None


class MatchSnapshotResponse(BaseModel):
    id: UUID
    brand_id: UUID
    domain_name: str
    tld: str
    label: str
    score_final: float
    attention_bucket: str | None = None
    matched_rule: str | None = None
    auto_disposition: str | None = None
    auto_disposition_reason: str | None = None
    first_detected_at: datetime
    domain_first_seen: datetime

    derived_score: float | None = None
    derived_bucket: str | None = None
    derived_risk: str | None = None
    derived_disposition: str | None = None
    active_signals: list[SignalSchema] = Field(default_factory=list)
    signal_codes: list[str] = Field(default_factory=list)
    llm_assessment: dict | None = None
    state_fingerprint: str | None = None
    last_derived_at: datetime | None = None

    model_config = {"from_attributes": True}


class MatchSnapshotListResponse(BaseModel):
    items: list[MatchSnapshotResponse]
    total: int


# ── Events ────────────────────────────────────────────────────

class EventResponse(BaseModel):
    id: UUID
    event_type: str
    event_source: str
    tool_name: str | None = None
    tool_version: str | None = None
    result_data: dict
    signals: list[dict] | None = None
    score_snapshot: dict | None = None
    cycle_id: UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    items: list[EventResponse]
    total: int
