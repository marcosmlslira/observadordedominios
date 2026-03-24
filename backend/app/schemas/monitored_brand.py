"""Pydantic schemas for monitoring profile endpoints (legacy /brands compatibility)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

AliasType = Literal["brand_alias", "brand_phrase", "support_keyword"]
NoiseMode = Literal["conservative", "standard", "broad"]


class BrandAliasRequest(BaseModel):
    value: str = Field(..., min_length=1, max_length=253)
    type: AliasType


class BrandDomainResponse(BaseModel):
    id: UUID
    domain_name: str
    registrable_domain: str
    registrable_label: str
    public_suffix: str
    hostname_stem: str | None = None
    is_primary: bool
    is_active: bool

    model_config = {"from_attributes": True}


class BrandAliasResponse(BaseModel):
    id: UUID
    alias_value: str
    alias_normalized: str
    alias_type: str
    weight_override: float | None = None
    is_active: bool

    model_config = {"from_attributes": True}


class BrandSeedResponse(BaseModel):
    id: UUID
    source_ref_type: str
    source_ref_id: UUID | None = None
    seed_value: str
    seed_type: str
    channel_scope: str
    base_weight: float
    is_manual: bool
    is_active: bool

    model_config = {"from_attributes": True}


class BrandSeedListResponse(BaseModel):
    items: list[BrandSeedResponse]
    total: int


class CreateBrandRequest(BaseModel):
    brand_name: str = Field(..., min_length=1, max_length=253)
    primary_brand_name: str | None = Field(None, min_length=1, max_length=253)
    official_domains: list[str] = Field(default_factory=list)
    aliases: list[BrandAliasRequest] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    tld_scope: list[str] = Field(default_factory=list)
    noise_mode: NoiseMode = "standard"
    notes: str | None = None


class UpdateBrandRequest(BaseModel):
    brand_name: str | None = Field(None, min_length=1, max_length=253)
    primary_brand_name: str | None = Field(None, min_length=1, max_length=253)
    official_domains: list[str] | None = None
    aliases: list[BrandAliasRequest] | None = None
    keywords: list[str] | None = None
    tld_scope: list[str] | None = None
    noise_mode: NoiseMode | None = None
    notes: str | None = None
    is_active: bool | None = None


class BrandResponse(BaseModel):
    id: UUID
    organization_id: UUID
    brand_name: str
    primary_brand_name: str
    brand_label: str
    keywords: list[str]
    tld_scope: list[str]
    noise_mode: str
    notes: str | None = None
    official_domains: list[BrandDomainResponse] = Field(default_factory=list)
    aliases: list[BrandAliasResponse] = Field(default_factory=list)
    seeds: list[BrandSeedResponse] = Field(default_factory=list)
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BrandListResponse(BaseModel):
    items: list[BrandResponse]
    total: int
