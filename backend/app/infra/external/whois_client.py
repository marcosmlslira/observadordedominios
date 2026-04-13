"""WHOIS lookup client using python-whois."""

from __future__ import annotations

import logging
import re

try:
    import whois
except ModuleNotFoundError:  # pragma: no cover - exercised in lean test envs
    whois = None

logger = logging.getLogger(__name__)

_NOT_FOUND_PATTERNS = (
    "domain not found",
    "no match for",
    "not found",
    "no entries found",
    "no data found",
    "status: free",
    "is available",
)
_RATE_LIMIT_PATTERNS = (
    "limit exceeded",
    "quota exceeded",
    "too many requests",
    "try again later",
    "rate limit",
)


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


def _parse_cctld_whois_fields(raw_text: str, result: dict) -> dict:
    """Augment WHOIS result with fields from ccTLD proprietary formats.

    Handles registro.br (and similar) formats where python-whois cannot parse
    the proprietary field names (owner/ownerid/responsible/created/expires).
    Only fills fields that python-whois left empty.
    """
    if not raw_text:
        return result

    if not result.get("registrant_organization"):
        m = re.search(r"^owner:\s+(.+)$", raw_text, re.MULTILINE | re.IGNORECASE)
        if m:
            result["registrant_organization"] = m.group(1).strip()

    if not result.get("registrant_name"):
        m = re.search(r"^responsible:\s+(.+)$", raw_text, re.MULTILINE | re.IGNORECASE)
        if m:
            result["registrant_name"] = m.group(1).strip()

    # ownerid carries CNPJ/CPF (Brazilian registry IDs)
    if not result.get("registrant_id"):
        m = re.search(r"^ownerid:\s+(.+)$", raw_text, re.MULTILINE | re.IGNORECASE)
        if m:
            result["registrant_id"] = m.group(1).strip()

    # creation date in YYYYMMDD format used by registro.br
    if not result.get("creation_date"):
        m = re.search(r"^created:\s+(\d{8})\s*$", raw_text, re.MULTILINE | re.IGNORECASE)
        if m:
            result["creation_date"] = m.group(1).strip()

    if not result.get("expiration_date"):
        m = re.search(r"^expires:\s+(\d{8})\s*$", raw_text, re.MULTILINE | re.IGNORECASE)
        if m:
            result["expiration_date"] = m.group(1).strip()

    # first e-mail: field (may appear in nic-hdl blocks — use the first occurrence)
    if not result.get("registrant_email"):
        m = re.search(r"^e-mail:\s+(.+)$", raw_text, re.MULTILINE | re.IGNORECASE)
        if m:
            result["registrant_email"] = m.group(1).strip()

    return result


def lookup_whois(domain: str) -> dict:
    """Query WHOIS for a domain. Returns a normalized dict."""
    if whois is None:
        return {
            "domain_name": domain,
            "registrar": None,
            "creation_date": None,
            "expiration_date": None,
            "updated_date": None,
            "name_servers": [],
            "status": [],
            "registrant_name": None,
            "registrant_organization": None,
            "registrant_country": None,
            "registrant_id": None,
            "registrant_email": None,
            "dnssec": None,
            "raw_text": "python-whois is not installed",
            "lookup_status": "technical_error",
            "availability_reason": "whois_library_missing",
            "confidence": 0.0,
            "data_quality": "inconclusive",
        }
    try:
        w = whois.whois(domain)
    except Exception as exc:
        message = str(exc)
        lowered = message.lower()
        if any(pattern in lowered for pattern in _RATE_LIMIT_PATTERNS):
            lookup_status = "rate_limited"
            availability_reason = "whois_provider_rate_limited"
            confidence = 0.0
            data_quality = "inconclusive"
        else:
            lookup_status = "technical_error"
            availability_reason = "whois_lookup_failed"
            confidence = 0.0
            data_quality = "inconclusive"
        return {
            "domain_name": domain,
            "registrar": None,
            "creation_date": None,
            "expiration_date": None,
            "updated_date": None,
            "name_servers": [],
            "status": [],
            "registrant_name": None,
            "registrant_organization": None,
            "registrant_country": None,
            "registrant_id": None,
            "registrant_email": None,
            "dnssec": None,
            "raw_text": message,
            "lookup_status": lookup_status,
            "availability_reason": availability_reason,
            "confidence": confidence,
            "data_quality": data_quality,
        }

    raw_text = w.text if hasattr(w, "text") else None
    raw_lower = (raw_text or "").lower()
    has_core_fields = any(
        [
            _to_str(w.registrar),
            _to_str(w.creation_date),
            _to_str(w.expiration_date),
            _to_str(w.updated_date),
            _to_str(getattr(w, "org", None)),
        ]
    )
    if any(pattern in raw_lower for pattern in _NOT_FOUND_PATTERNS):
        lookup_status = "not_found"
        availability_reason = "domain_not_registered"
        confidence = 0.2
        data_quality = "inconclusive"
    elif any(pattern in raw_lower for pattern in _RATE_LIMIT_PATTERNS):
        lookup_status = "rate_limited"
        availability_reason = "whois_provider_rate_limited"
        confidence = 0.0
        data_quality = "inconclusive"
    elif raw_lower and re.search(r"\b(redacted|privacy|gdpr)\b", raw_lower) and not has_core_fields:
        lookup_status = "redacted"
        availability_reason = "whois_redacted"
        confidence = 0.45
        data_quality = "degraded"
    elif has_core_fields or raw_text:
        lookup_status = "ok"
        availability_reason = None
        confidence = 0.9 if has_core_fields else 0.6
        data_quality = "complete" if has_core_fields else "degraded"
    else:
        lookup_status = "technical_error"
        availability_reason = "whois_response_empty"
        confidence = 0.0
        data_quality = "inconclusive"

    result = {
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
        "registrant_id": None,
        "registrant_email": None,
        "dnssec": _to_str(getattr(w, "dnssec", None)),
        "raw_text": raw_text,
        "lookup_status": lookup_status,
        "availability_reason": availability_reason,
        "confidence": confidence,
        "data_quality": data_quality,
    }
    return _parse_cctld_whois_fields(raw_text or "", result)
