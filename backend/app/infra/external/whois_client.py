"""WHOIS lookup client using python-whois."""

from __future__ import annotations

import logging

import whois

logger = logging.getLogger(__name__)


def _to_str(value) -> str | None:
    """Convert whois field (may be list or datetime) to string."""
    if value is None:
        return None
    if isinstance(value, list):
        return str(value[0]) if value else None
    return str(value)


def _to_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def lookup_whois(domain: str) -> dict:
    """Query WHOIS for a domain. Returns a normalized dict."""
    w = whois.whois(domain)

    return {
        "domain_name": _to_str(w.domain_name),
        "registrar": _to_str(w.registrar),
        "creation_date": _to_str(w.creation_date),
        "expiration_date": _to_str(w.expiration_date),
        "updated_date": _to_str(w.updated_date),
        "name_servers": _to_str_list(w.name_servers),
        "status": _to_str_list(w.status),
        "registrant_name": _to_str(getattr(w, "name", None)),
        "registrant_organization": _to_str(getattr(w, "org", None)),
        "registrant_country": _to_str(getattr(w, "country", None)),
        "dnssec": _to_str(getattr(w, "dnssec", None)),
        "raw_text": w.text if hasattr(w, "text") else None,
    }
