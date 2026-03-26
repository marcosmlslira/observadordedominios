"""Helpers for parsing registrable domains using the public suffix list."""

from __future__ import annotations

import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

try:
    import tldextract  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - exercised in tests via fallback
    tldextract = None

_DOMAIN_RE = re.compile(
    r"^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?"
    r"(\.[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?)*$"
)
_SECOND_LEVEL_CCTLD_PREFIXES = {"ac", "co", "com", "edu", "gov", "net", "org"}

if tldextract is not None:
    _extractor = tldextract.TLDExtract(
        cache_dir=str(Path(tempfile.gettempdir()) / "tldextract_cache"),
    )
else:  # pragma: no cover - exercised only when dependency is unavailable
    _extractor = None


@dataclass(frozen=True)
class RegistrableDomainParts:
    normalized: str
    registrable_domain: str
    registrable_label: str
    public_suffix: str


class InvalidDomainError(ValueError):
    """Raised when a domain cannot be normalized into a registrable domain."""


def normalize_domain(raw_value: str) -> str:
    cleaned = raw_value.strip().lower().rstrip(".")
    if not cleaned or " " in cleaned:
        raise InvalidDomainError("domain must not be empty")

    try:
        normalized = cleaned.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise InvalidDomainError("domain could not be normalized") from exc

    if len(normalized) > 253 or not _DOMAIN_RE.match(normalized):
        raise InvalidDomainError("domain has invalid syntax")
    return normalized


def parse_registrable_domain(raw_value: str) -> RegistrableDomainParts:
    normalized = normalize_domain(raw_value)
    parts = _extract_domain_parts(normalized)
    if not parts:
        raise InvalidDomainError("domain must contain a registrable label and public suffix")
    return RegistrableDomainParts(
        normalized=normalized,
        registrable_domain=parts["registered_domain"],
        registrable_label=parts["domain"],
        public_suffix=parts["suffix"],
    )


def _extract_domain_parts(candidate: str) -> dict[str, str] | None:
    if _extractor is not None:
        ext = _extractor(candidate)
        if ext.domain and ext.suffix and ext.registered_domain:
            return {
                "domain": ext.domain,
                "suffix": ext.suffix,
                "registered_domain": ext.registered_domain,
            }

    labels = [label for label in candidate.split(".") if label]
    if len(labels) < 2:
        return None

    if (
        len(labels) >= 3
        and len(labels[-1]) == 2
        and labels[-2] in _SECOND_LEVEL_CCTLD_PREFIXES
    ):
        suffix_labels = labels[-2:]
        domain_index = -3
    else:
        suffix_labels = labels[-1:]
        domain_index = -2

    domain = labels[domain_index]
    suffix = ".".join(suffix_labels)
    registered_domain = ".".join([domain, *suffix_labels])
    return {
        "domain": domain,
        "suffix": suffix,
        "registered_domain": registered_domain,
    }
