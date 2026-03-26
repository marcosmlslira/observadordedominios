"""Resolve effective ingestion coverage per TLD."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import settings
from app.infra.external.czds_client import CZDSClient
from app.repositories.czds_policy_repository import CzdsPolicyRepository


def _parse_tld_csv(raw: str) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        tld = item.strip().lower().lstrip(".")
        if not tld or tld in seen:
            continue
        seen.add(tld)
        items.append(tld)
    return items


@dataclass(slots=True)
class TldCoverage:
    tld: str
    effective_source: str
    czds_available: bool
    ct_enabled: bool
    bulk_status: str
    fallback_reason: str | None
    priority_group: str


def get_target_tlds() -> list[str]:
    raw = settings.TARGET_TLDS or settings.CZDS_ENABLED_TLDS
    return _parse_tld_csv(raw)


def get_ct_priority_tlds() -> list[str]:
    explicit = _parse_tld_csv(settings.CT_FALLBACK_PRIORITY_TLDS)
    if explicit:
        return explicit
    return ["br", "com.br", "net.br", "org.br", "uk", "de", "fr", "au", "ca", "us", "io", "ai", "co", "tv", "me"]


def get_br_ct_subtlds() -> list[str]:
    return _parse_tld_csv(settings.CT_BR_SUBTLDS)


def expand_ct_query_tlds(tlds: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for tld in tlds:
        if tld == "br":
            for subtld in get_br_ct_subtlds():
                if subtld == "br":
                    continue
                if subtld not in seen:
                    seen.add(subtld)
                    expanded.append(subtld)
            continue
        if tld not in seen:
            seen.add(tld)
            expanded.append(tld)
    return expanded


def get_authorized_czds_tlds(czds_client: CZDSClient | None = None) -> set[str]:
    if not settings.CZDS_USERNAME or not settings.CZDS_PASSWORD:
        return set()
    client = czds_client or CZDSClient()
    try:
        return client.list_authorized_tlds()
    except Exception:
        return set()


def resolve_tld_coverages(
    db: Session,
    *,
    czds_client: CZDSClient | None = None,
) -> list[TldCoverage]:
    target_tlds = get_target_tlds()
    priority_tlds = set(get_ct_priority_tlds())
    authorized_czds_tlds = get_authorized_czds_tlds(czds_client)
    policies = {item.tld: item for item in CzdsPolicyRepository(db).list_all()}
    coverages: list[TldCoverage] = []

    for tld in target_tlds:
        policy = policies.get(tld)
        is_quarantined = bool(
            policy
            and policy.last_error_code in {403, 404}
            and policy.suspended_until is not None
        )
        czds_available = tld in authorized_czds_tlds and not is_quarantined
        if settings.CT_FALLBACK_INCLUDE_NON_CZDS and not czds_available:
            effective_source = "ct_fallback"
            fallback_reason = "czds_unavailable"
            ct_enabled = True
            bulk_status = "manual"
        else:
            effective_source = "czds_primary"
            fallback_reason = None
            ct_enabled = False
            bulk_status = "n/a"

        coverages.append(
            TldCoverage(
                tld=tld,
                effective_source=effective_source,
                czds_available=czds_available,
                ct_enabled=ct_enabled,
                bulk_status=bulk_status,
                fallback_reason=fallback_reason,
                priority_group="priority" if tld in priority_tlds else "standard",
            )
        )

    return coverages


def resolve_ct_fallback_tlds(
    db: Session,
    *,
    czds_client: CZDSClient | None = None,
) -> list[str]:
    fallbacks = [
        item.tld
        for item in resolve_tld_coverages(db, czds_client=czds_client)
        if item.effective_source == "ct_fallback"
    ]
    return expand_ct_query_tlds(fallbacks)


def resolve_certstream_suffixes(
    db: Session,
    *,
    czds_client: CZDSClient | None = None,
) -> list[str]:
    explicit = _parse_tld_csv(settings.CT_STREAM_ENABLED_TLDS)
    if explicit:
        return sorted({f".{item}" for item in explicit})

    fallbacks = [
        item.tld
        for item in resolve_tld_coverages(db, czds_client=czds_client)
        if item.effective_source == "ct_fallback"
    ]

    suffixes: set[str] = set()
    for tld in fallbacks:
        if tld == "br":
            suffixes.add(".br")
        else:
            suffixes.add(f".{tld}")
    return sorted(suffixes, key=len, reverse=True)
