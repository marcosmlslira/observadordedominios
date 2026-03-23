"""Pydantic schemas for similarity match and similarity search endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

SimilarityAlgorithm = Literal["fuzzy", "typo", "vector", "hybrid"]
SimilaritySource = Literal["czds"]


# ── Request ──────────────────────────────────────────────────

class TriggerScanRequest(BaseModel):
    tld: str | None = Field(None, description="Specific TLD to scan. Empty = all.")


class UpdateMatchStatusRequest(BaseModel):
    status: str = Field(..., pattern=r"^(new|reviewing|dismissed|confirmed_threat)$")
    notes: str | None = None


class SimilaritySearchRequest(BaseModel):
    query_domain: str = Field(..., min_length=3, max_length=253)
    algorithms: list[SimilarityAlgorithm] = Field(default_factory=lambda: ["hybrid"])
    min_score: float = Field(0.45, ge=0.0, le=1.0)
    max_results: int = Field(50, ge=1, le=200)
    include_subdomains: bool = False
    tld_allowlist: list[str] | None = None
    sources: list[SimilaritySource] = Field(default_factory=lambda: ["czds"])
    offset: int = Field(0, ge=0)

    @field_validator("query_domain")
    @classmethod
    def normalize_query_domain(cls, value: str) -> str:
        return value.strip().lower().rstrip(".")

    @field_validator("algorithms")
    @classmethod
    def ensure_algorithms(cls, value: list[SimilarityAlgorithm]) -> list[SimilarityAlgorithm]:
        if not value:
            raise ValueError("algorithms must contain at least one value")
        return list(dict.fromkeys(value))

    @field_validator("tld_allowlist")
    @classmethod
    def normalize_tlds(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [item.strip().lower() for item in value if item.strip()]
        return normalized or None


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
    removed: int = 0
    status: str


class ScanSummaryResponse(BaseModel):
    results: list[ScanResultResponse]


class SimilaritySearchScoreResponse(BaseModel):
    fuzzy: float
    typo: float
    vector: float


class SimilaritySearchResultResponse(BaseModel):
    domain: str
    tld: str
    source: str
    status: str
    score: float
    scores: SimilaritySearchScoreResponse
    reasons: list[str]
    observed_at: datetime


class SimilaritySearchQueryResponse(BaseModel):
    domain: str
    normalized: str
    algorithms: list[SimilarityAlgorithm]
    min_score: float


class SimilaritySearchPaginationResponse(BaseModel):
    offset: int
    limit: int
    returned: int
    has_more: bool


class SimilaritySearchResponse(BaseModel):
    query: SimilaritySearchQueryResponse
    pagination: SimilaritySearchPaginationResponse
    results: list[SimilaritySearchResultResponse]


class SimilarityHealthResponse(BaseModel):
    status: str
    version: str
    average_search_latency_ms: float
    samples: int
    vector_enabled: bool
