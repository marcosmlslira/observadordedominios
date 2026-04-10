"""Pydantic schemas for ingestion config and TLD policy endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from app.services.ingestion_config_service import InvalidCronError, validate_cron_expression


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


class TldPolicyPatchRequest(BaseModel):
    is_enabled: bool


class TldPolicyBulkItem(BaseModel):
    tld: str
    is_enabled: bool


class TldPolicyBulkRequest(BaseModel):
    tlds: list[TldPolicyBulkItem]


class TriggerTldRequest(BaseModel):
    force: bool = False


# ── Responses ─────────────────────────────────────────────────

class SourceConfigResponse(BaseModel):
    source: str
    cron_expression: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class TldPolicyResponse(BaseModel):
    source: str
    tld: str
    is_enabled: bool
    updated_at: datetime

    model_config = {"from_attributes": True}


class TriggerTldResponse(BaseModel):
    run_id: str
    source: str
    tld: str
    status: str  # "queued"
