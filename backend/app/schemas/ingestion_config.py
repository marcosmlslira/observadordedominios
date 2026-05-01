"""Pydantic schemas for ingestion config and TLD policy endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.services.ingestion_config_service import InvalidCronError, validate_cron_expression

OrderingMode = Literal["corpus_first", "priority_first", "alphabetical"]

# Sources that support ordering_mode configuration
ORDERING_MODE_SOURCES = {"czds"}


# ── Requests ─────────────────────────────────────────────────

class CronUpdateRequest(BaseModel):
    cron_expression: str

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        try:
            return validate_cron_expression(v)
        except InvalidCronError as exc:
            raise ValueError(str(exc)) from exc


class IngestionConfigPatchRequest(BaseModel):
    ordering_mode: OrderingMode | None = None


class TldPolicyPatchRequest(BaseModel):
    is_enabled: bool | None = None
    priority: int | None = None


class TldPolicyBulkItem(BaseModel):
    tld: str
    is_enabled: bool


class TldPolicyBulkRequest(BaseModel):
    tlds: list[TldPolicyBulkItem]


# ── Responses ─────────────────────────────────────────────────

class SourceConfigResponse(BaseModel):
    source: str
    cron_expression: str
    ordering_mode: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class TldPolicyResponse(BaseModel):
    source: str
    tld: str
    is_enabled: bool
    priority: int | None = None
    domains_inserted: int = 0
    last_seen_at: datetime | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}
