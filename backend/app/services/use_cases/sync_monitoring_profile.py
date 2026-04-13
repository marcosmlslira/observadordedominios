"""Create/update monitoring profile structure on top of MonitoredBrand."""

from __future__ import annotations

from collections import defaultdict

from app.models.monitored_brand import MonitoredBrand
from app.repositories.monitored_brand_repository import MonitoredBrandRepository
from app.schemas.monitored_brand import BrandAliasRequest
from app.services.monitoring_profile import (
    build_alias_inputs,
    build_domain_inputs,
    build_seed_rows,
    derive_brand_label,
    enrich_tld_scope_for_brazil,
    looks_like_domain,
    normalize_noise_mode,
    resolve_display_name,
    resolve_official_domains,
    resolve_primary_brand_name,
)


def create_monitoring_profile(
    repo: MonitoredBrandRepository,
    *,
    organization_id,
    display_name: str,
    primary_brand_name: str | None,
    official_domains: list[str],
    aliases: list[BrandAliasRequest],
    keywords: list[str],
    tld_scope: list[str],
    noise_mode: str,
    notes: str | None,
) -> MonitoredBrand:
    prepared = _prepare_profile_components(
        display_name=display_name,
        primary_brand_name=primary_brand_name,
        official_domains=official_domains,
        aliases=aliases,
        keywords=keywords,
        noise_mode=noise_mode,
    )

    enriched_tld_scope = enrich_tld_scope_for_brazil(tld_scope, official_domains)

    brand = repo.create(
        organization_id=organization_id,
        brand_name=prepared["display_name"],
        primary_brand_name=prepared["primary_brand_name"],
        brand_label=prepared["brand_label"],
        keywords=prepared["keywords"],
        tld_scope=enriched_tld_scope,
        noise_mode=prepared["noise_mode"],
        notes=notes,
    )
    _apply_profile_components(repo, brand, prepared)
    return brand


def update_monitoring_profile(
    repo: MonitoredBrandRepository,
    brand: MonitoredBrand,
    *,
    display_name: str | None = None,
    primary_brand_name: str | None = None,
    official_domains: list[str] | None = None,
    aliases: list[BrandAliasRequest] | None = None,
    keywords: list[str] | None = None,
    tld_scope: list[str] | None = None,
    noise_mode: str | None = None,
    notes: str | None = None,
    is_active: bool | None = None,
    trusted_registrants: dict | None = None,
) -> MonitoredBrand:
    effective_display_name = display_name if display_name is not None else brand.brand_name
    effective_domains = official_domains if official_domains is not None else [item.domain_name for item in brand.domains]
    effective_aliases = aliases if aliases is not None else [
        BrandAliasRequest(value=item.alias_value, type=item.alias_type)
        for item in brand.aliases
        if item.alias_type != "brand_primary"
    ]
    effective_keywords = keywords if keywords is not None else list(brand.keywords or [])
    effective_primary = primary_brand_name if primary_brand_name is not None else brand.primary_brand_name
    effective_noise_mode = noise_mode if noise_mode is not None else brand.noise_mode

    prepared = _prepare_profile_components(
        display_name=effective_display_name,
        primary_brand_name=effective_primary,
        official_domains=effective_domains,
        aliases=effective_aliases,
        keywords=effective_keywords,
        noise_mode=effective_noise_mode,
    )

    enriched_tld_scope = (
        enrich_tld_scope_for_brazil(tld_scope, effective_domains)
        if tld_scope is not None
        else None
    )

    repo.update(
        brand,
        brand_name=prepared["display_name"],
        primary_brand_name=prepared["primary_brand_name"],
        brand_label=prepared["brand_label"],
        keywords=prepared["keywords"],
        tld_scope=enriched_tld_scope,
        noise_mode=prepared["noise_mode"],
        notes=notes,
        is_active=is_active,
        trusted_registrants=trusted_registrants,
    )
    _apply_profile_components(repo, brand, prepared)
    return brand


def ensure_monitoring_profile_integrity(
    repo: MonitoredBrandRepository,
    brand: MonitoredBrand,
) -> MonitoredBrand:
    if brand.aliases and brand.seeds:
        return brand

    display_name = brand.brand_name
    official_domains = [item.domain_name for item in brand.domains]
    if not official_domains and looks_like_domain(display_name):
        official_domains = [display_name]

    aliases = [
        BrandAliasRequest(value=item.alias_value, type=item.alias_type)
        for item in brand.aliases
        if item.alias_type != "brand_primary"
    ]

    prepared = _prepare_profile_components(
        display_name=display_name,
        primary_brand_name=brand.primary_brand_name,
        official_domains=official_domains,
        aliases=aliases,
        keywords=list(brand.keywords or []),
        noise_mode=brand.noise_mode,
    )
    repo.update(
        brand,
        primary_brand_name=prepared["primary_brand_name"],
        brand_label=prepared["brand_label"],
        keywords=prepared["keywords"],
        noise_mode=prepared["noise_mode"],
    )
    _apply_profile_components(repo, brand, prepared)
    return brand


def _prepare_profile_components(
    *,
    display_name: str,
    primary_brand_name: str | None,
    official_domains: list[str],
    aliases: list[BrandAliasRequest],
    keywords: list[str],
    noise_mode: str,
) -> dict:
    resolved_display_name = resolve_display_name(display_name, primary_brand_name)
    resolved_domains = resolve_official_domains(resolved_display_name, official_domains)
    resolved_primary_brand_name = resolve_primary_brand_name(
        resolved_display_name,
        primary_brand_name,
        resolved_domains,
    )
    domain_inputs = build_domain_inputs(resolved_domains)

    alias_values_by_type: dict[str, list[str]] = defaultdict(list)
    for alias in aliases:
        alias_values_by_type[alias.type].append(alias.value)

    alias_inputs = build_alias_inputs(
        primary_brand_name=resolved_primary_brand_name,
        aliases=alias_values_by_type["brand_alias"],
        phrases=alias_values_by_type["brand_phrase"],
        support_keywords=keywords,
    )

    return {
        "display_name": resolved_display_name,
        "primary_brand_name": resolved_primary_brand_name,
        "brand_label": derive_brand_label(resolved_primary_brand_name, domain_inputs),
        "keywords": [item.alias_value for item in alias_inputs if item.alias_type == "support_keyword"],
        "noise_mode": normalize_noise_mode(noise_mode),
        "domains": [
            {
                "domain_name": item.domain_name,
                "registrable_domain": item.registrable_domain,
                "registrable_label": item.registrable_label,
                "public_suffix": item.public_suffix,
                "hostname_stem": item.hostname_stem,
                "is_primary": item.is_primary,
                "is_active": True,
            }
            for item in domain_inputs
        ],
        "aliases": [
            {
                "alias_value": item.alias_value,
                "alias_normalized": item.alias_normalized,
                "alias_type": item.alias_type,
                "weight_override": item.weight_override,
                "is_active": True,
            }
            for item in alias_inputs
        ],
    }


def _apply_profile_components(
    repo: MonitoredBrandRepository,
    brand: MonitoredBrand,
    prepared: dict,
) -> None:
    domains = repo.replace_domains(brand, prepared["domains"])
    aliases = repo.replace_aliases(brand, prepared["aliases"])
    repo.replace_seeds(brand, build_seed_rows(domains, aliases))
