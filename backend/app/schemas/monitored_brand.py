"""Pydantic schemas for monitored brand endpoints."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Request ──────────────────────────────────────────────────

class CreateBrandRequest(BaseModel):
    brand_name: str = Field(..., min_length=1, max_length=253)
    keywords: list[str] = Field(default_factory=list)
    tld_scope: list[str] = Field(default_factory=list)


class UpdateBrandRequest(BaseModel):
    brand_name: str | None = Field(None, min_length=1, max_length=253)
    keywords: list[str] | None = None
    tld_scope: list[str] | None = None
    is_active: bool | None = None


# ── Response ─────────────────────────────────────────────────

class BrandResponse(BaseModel):
    id: UUID
    organization_id: UUID
    brand_name: str
    brand_label: str
    keywords: list[str]
    tld_scope: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BrandListResponse(BaseModel):
    items: list[BrandResponse]
    total: int
