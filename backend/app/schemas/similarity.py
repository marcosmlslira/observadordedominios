"""Pydantic schemas for similarity match endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Request ──────────────────────────────────────────────────

class TriggerScanRequest(BaseModel):
    tld: str | None = Field(None, description="Specific TLD to scan. Empty = all.")


class UpdateMatchStatusRequest(BaseModel):
    status: str = Field(..., pattern=r"^(reviewing|dismissed|confirmed_threat)$")
    notes: str | None = None


# ── Response ─────────────────────────────────────────────────

class MatchResponse(BaseModel):
    id: UUID
    brand_id: UUID
    domain_name: str
    tld: str
    label: str
    score_final: float
    score_trigram: float | None
    score_levenshtein: float | None
    score_brand_hit: float | None
    score_keyword: float | None
    score_homograph: float | None
    reasons: list[str]
    risk_level: str
    first_detected_at: datetime
    domain_first_seen: datetime
    status: str
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


class MatchListResponse(BaseModel):
    items: list[MatchResponse]
    total: int


class ScanResultResponse(BaseModel):
    brand_id: UUID
    tld: str | None
    candidates: int
    matched: int
    status: str


class ScanSummaryResponse(BaseModel):
    results: list[ScanResultResponse]
