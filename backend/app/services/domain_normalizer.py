"""Domain normalization for CT Log sources (CertStream, crt.sh).

Pure functions — no side effects, no DB access.
Uses tldextract with Mozilla Public Suffix List for correct multi-level TLD parsing.
"""

from __future__ import annotations

import logging
import re

import tldextract

logger = logging.getLogger(__name__)

# Pre-compiled regex for basic domain validation
_DOMAIN_RE = re.compile(
    r"^[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?"  # label
    r"(\.[a-z0-9]([a-z0-9\-]{0,61}[a-z0-9])?)*$"  # more labels
)

# Configure tldextract to use local cache (avoids network calls on startup)
_extractor = tldextract.TLDExtract(cache_dir="/tmp/tldextract_cache")


def normalize_ct_domains(
    raw_names: list[str],
    *,
    filter_suffix: str = "br",
) -> list[tuple[str, str, str]]:
    """Normalize raw domain names from CT sources.

    Pipeline: lowercase -> strip wildcard -> strip trailing dot ->
              tldextract -> filter by suffix -> validate -> dedup.

    Args:
        raw_names: Raw domain names (may include wildcards, subdomains).
        filter_suffix: Only keep domains whose TLD ends with this suffix.

    Returns:
        List of (name, tld, label) tuples ready for DB insert.
        - name: registered domain, e.g. "banco.com.br"
        - tld: effective TLD, e.g. "com.br"
        - label: domain without TLD, e.g. "banco"
    """
    seen: set[tuple[str, str]] = set()
    results: list[tuple[str, str, str]] = []

    for raw in raw_names:
        normalized = _normalize_single(raw, filter_suffix)
        if normalized is None:
            continue

        name, tld, label = normalized
        key = (name, tld)
        if key in seen:
            continue
        seen.add(key)
        results.append((name, tld, label))

    return results


def _normalize_single(
    raw: str,
    filter_suffix: str,
) -> tuple[str, str, str] | None:
    """Normalize a single raw domain name. Returns None if invalid."""
    # Lowercase and strip whitespace
    cleaned = raw.strip().lower()

    # Strip leading wildcard prefix
    if cleaned.startswith("*."):
        cleaned = cleaned[2:]

    # Strip trailing dot
    cleaned = cleaned.rstrip(".")

    # Skip empty or too long
    if not cleaned or len(cleaned) > 253:
        return None

    # Quick check: must end with filter suffix
    if not cleaned.endswith(f".{filter_suffix}") and cleaned != filter_suffix:
        return None

    # Parse with tldextract
    ext = _extractor(cleaned)

    # ext.domain = "banco", ext.suffix = "com.br", ext.registered_domain = "banco.com.br"
    tld = ext.suffix
    label = ext.domain
    registered_domain = ext.registered_domain

    # Reject if no label (bare TLD like "com.br")
    if not label:
        return None

    # Reject if no TLD parsed
    if not tld:
        return None

    # Reject if TLD doesn't match filter
    if not tld.endswith(filter_suffix):
        return None

    # Reject if registered_domain is empty
    if not registered_domain:
        return None

    # Use registered_domain as name (strips subdomains)
    # "login.banco.com.br" -> name="banco.com.br", not "login.banco.com.br"
    name = registered_domain

    # Validate the label format
    if not _DOMAIN_RE.match(label):
        return None

    return (name, tld, label)
