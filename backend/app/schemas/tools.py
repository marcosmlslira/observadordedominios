"""Pydantic schemas for free tools — requests, responses, history, and quick analysis."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, Field, field_validator

# ── Tool type enum ────────────────────────────────────────

ToolType = Literal[
    "dns_lookup",
    "whois",
    "ssl_check",
    "screenshot",
    "suspicious_page",
    "http_headers",
    "blacklist_check",
    "email_security",
    "reverse_ip",
    "ip_geolocation",
    "domain_similarity",
    "website_clone",
    "subdomain_takeover_check",
    "safe_browsing_check",
    "urlhaus_check",
    "phishtank_check",
]

ToolStatus = Literal["running", "completed", "failed", "timeout"]
TriggeredBy = Literal["manual", "quick_analysis"]


# ── Shared request / response ─────────────────────────────

def _normalize_domain(value: str) -> str:
    import re
    v = value.strip().lower().rstrip(".")
    v = re.sub(r"^https?://", "", v)
    v = re.sub(r"^www\.", "", v)
    v = v.split("/")[0].split("?")[0].split("#")[0]
    return v


def _normalize_domain_pair(value: str) -> str:
    if "|" not in value:
        return _normalize_domain(value)

    target, reference = value.split("|", 1)
    return f"{_normalize_domain(target)}|{_normalize_domain(reference)}"


class ToolRequest(BaseModel):
    target: str = Field(..., min_length=1, max_length=253)

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        return _normalize_domain(value)


class WebsiteCloneRequest(BaseModel):
    target: str = Field(..., min_length=1, max_length=253)
    reference_target: str | None = Field(
        default=None,
        min_length=1,
        max_length=253,
        validation_alias=AliasChoices("reference_target", "reference_url"),
    )

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        return _normalize_domain_pair(value)

    @field_validator("reference_target")
    @classmethod
    def normalize_reference_target(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _normalize_domain(value)

    def build_execution_target(self) -> str:
        if self.reference_target:
            return f"{_normalize_domain(self.target)}|{self.reference_target}"
        if "|" in self.target:
            return self.target
        raise ValueError("Website Clone requires target and reference_target")


class ToolResponse(BaseModel):
    execution_id: UUID
    tool_type: ToolType
    target: str
    status: ToolStatus
    duration_ms: int | None = None
    cached: bool = False
    result: dict[str, Any] | None = None
    error: str | None = None
    executed_at: datetime

    model_config = {"from_attributes": True}


# ── Quick Analysis ────────────────────────────────────────

class QuickAnalysisRequest(BaseModel):
    target: str = Field(..., min_length=1, max_length=253)
    tools: list[ToolType] = Field(
        default_factory=lambda: [
            "dns_lookup", "whois", "ssl_check",
            "http_headers", "screenshot", "suspicious_page",
        ]
    )

    @field_validator("target")
    @classmethod
    def normalize_target(cls, value: str) -> str:
        return _normalize_domain(value)


class QuickAnalysisToolResult(BaseModel):
    status: ToolStatus
    result: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int | None = None


class QuickAnalysisResponse(BaseModel):
    quick_analysis_id: UUID
    target: str
    status: Literal["completed", "partial"]
    total_duration_ms: int
    results: dict[str, QuickAnalysisToolResult]


# ── History ───────────────────────────────────────────────

class HistoryItem(BaseModel):
    execution_id: UUID
    tool_type: ToolType
    target: str
    status: ToolStatus
    duration_ms: int | None = None
    triggered_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class HistoryListResponse(BaseModel):
    items: list[HistoryItem]
    total: int


# Per-tool result payloads are returned as untyped `dict` inside
# `ToolResponse.result` — see `ToolResponse` above. The granular Pydantic
# schemas that previously documented each tool's shape were never bound to
# any endpoint or runtime check (tools return raw dicts), so they were
# removed to keep this module lean. Refer to each tool's implementation
# under `app.services.use_cases.tools.*` for the actual payload shape.
