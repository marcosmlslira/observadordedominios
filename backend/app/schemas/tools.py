"""Pydantic schemas for free tools — requests, responses, and per-tool result shapes."""

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


# ── Per-tool result schemas (DNS Lookup — Wave 1) ────────

class DnsRecord(BaseModel):
    type: str
    name: str
    value: str
    ttl: int | None = None


class DnsLookupResult(BaseModel):
    records: list[DnsRecord]
    nameservers: list[str] = []
    resolution_time_ms: int | None = None


# ── WHOIS ─────────────────────────────────────────────────

class WhoisResult(BaseModel):
    domain_name: str | None = None
    registrar: str | None = None
    creation_date: str | None = None
    expiration_date: str | None = None
    updated_date: str | None = None
    name_servers: list[str] = []
    status: list[str] = []
    registrant_name: str | None = None
    registrant_organization: str | None = None
    registrant_country: str | None = None
    dnssec: str | None = None
    raw_text: str | None = None
    lookup_status: Literal["ok", "not_found", "rate_limited", "redacted", "technical_error"] = "ok"
    availability_reason: str | None = None
    confidence: float = 0.0
    data_quality: Literal["complete", "degraded", "inconclusive"] = "complete"


# ── SSL Check ─────────────────────────────────────────────

class SslCertificate(BaseModel):
    subject: str | None = None
    issuer: str | None = None
    serial_number: str | None = None
    not_before: str | None = None
    not_after: str | None = None
    days_remaining: int | None = None
    san: list[str] = []
    signature_algorithm: str | None = None
    version: int | None = None


class SslCheckResult(BaseModel):
    is_valid: bool
    certificate: SslCertificate | None = None
    chain_length: int | None = None
    protocol_version: str | None = None
    cipher_suite: str | None = None
    issues: list[str] = []


# ── HTTP Headers ──────────────────────────────────────────

class SecurityHeader(BaseModel):
    name: str
    value: str | None = None
    present: bool
    severity: Literal["good", "warning", "critical"] = "warning"
    description: str | None = None


class RedirectHop(BaseModel):
    url: str
    status_code: int


class HttpHeadersResult(BaseModel):
    final_url: str
    status_code: int
    headers: dict[str, str] = {}
    security_headers: list[SecurityHeader] = []
    redirect_chain: list[RedirectHop] = []
    server: str | None = None
    content_type: str | None = None


# ── Screenshot ────────────────────────────────────────────

class ScreenshotResult(BaseModel):
    screenshot_url: str | None = None
    s3_key: str | None = None
    page_title: str | None = None
    final_url: str | None = None
    viewport_width: int = 1280
    viewport_height: int = 720


# ── Suspicious Page ───────────────────────────────────────

class SuspiciousSignal(BaseModel):
    category: str
    description: str
    severity: Literal["low", "medium", "high", "critical"]


class SuspiciousPageResult(BaseModel):
    risk_score: float = 0.0
    risk_level: Literal["safe", "inconclusive", "protected", "low", "medium", "high", "critical"] = "safe"
    signals: list[SuspiciousSignal] = []
    page_title: str | None = None
    final_url: str | None = None
    http_status: int | None = None
    page_disposition: Literal["live", "parked", "challenge", "unreachable"] | None = None
    has_login_form: bool = False
    has_credential_inputs: bool = False
    external_resource_count: int = 0
    confidence: float = 0.0
    data_quality: Literal["complete", "degraded", "inconclusive"] = "complete"


# ── Blacklist Check ───────────────────────────────────────

class BlacklistEntry(BaseModel):
    source: str
    listed: bool
    detail: str | None = None


class BlacklistCheckResult(BaseModel):
    is_listed: bool = False
    total_sources: int = 0
    listed_count: int = 0
    entries: list[BlacklistEntry] = []


# ── Email Security ────────────────────────────────────────

class EmailProtocol(BaseModel):
    protocol: Literal["spf", "dmarc", "dkim"]
    status: Literal["pass", "fail", "partial", "not_found"]
    record: str | None = None
    details: str | None = None


class SpoofingRiskResult(BaseModel):
    score: int = 0
    level: Literal["low", "medium", "high", "critical"] = "high"


class EmailSecurityResult(BaseModel):
    spoofing_risk: SpoofingRiskResult = Field(default_factory=SpoofingRiskResult)
    protocols: list[EmailProtocol] = []
    has_spf: bool = False
    has_dmarc: bool = False
    has_dkim: bool = False


# ── Reverse IP ────────────────────────────────────────────

class ReverseIpResult(BaseModel):
    ip_address: str
    total_domains: int = 0
    domains: list[str] = []


# ── IP Geolocation ────────────────────────────────────────

class IpGeolocationResult(BaseModel):
    ip_address: str
    country: str | None = None
    country_code: str | None = None
    region: str | None = None
    city: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    asn: int | None = None
    as_name: str | None = None
    isp: str | None = None


# ── Domain Similarity ─────────────────────────────────────

class SimilarDomain(BaseModel):
    domain: str
    type: str
    is_registered: bool | None = None
    ip_address: str | None = None


class DomainSimilarityResult(BaseModel):
    total_generated: int = 0
    registered_count: int | None = None
    variations: list[SimilarDomain] = []


# ── Website Clone ─────────────────────────────────────────

class CloneComparisonScore(BaseModel):
    visual: float | None = None
    textual: float | None = None
    structural: float | None = None
    overall: float = 0.0


class WebsiteCloneResult(BaseModel):
    reference_domain: str
    target_domain: str
    scores: CloneComparisonScore
    is_clone: bool = False
    confidence: Literal["low", "medium", "high"] = "low"
    comparison_state: Literal["complete", "partial_comparison", "failed"] = "complete"
    target_access_state: Literal["ok", "challenge", "not_found", "error"] = "ok"
    reference_access_state: Literal["ok", "challenge", "not_found", "error"] = "ok"
    errors: list[str] = []
