"""Label extraction — strip the TLD suffix from a normalised domain name."""

from __future__ import annotations


def extract_label(domain_norm: str, tld: str) -> str:
    """Return the SLD label for a fully-qualified domain name.

    Examples
    --------
    >>> extract_label("google.com", "com")
    'google'
    >>> extract_label("example.co.uk", "co.uk")
    'example'
    """
    suffix = f".{tld}"
    if domain_norm.endswith(suffix):
        return domain_norm[: -len(suffix)]
    # Fallback: strip last component
    parts = domain_norm.rsplit(".", 1)
    return parts[0] if len(parts) == 2 else domain_norm
