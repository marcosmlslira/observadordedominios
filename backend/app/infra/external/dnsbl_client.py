"""DNSBL (blacklist) query client using dnspython."""

from __future__ import annotations

import logging
import socket

import dns.resolver

logger = logging.getLogger(__name__)

# Well-known DNSBL zones with display names and categories
DNSBL_ZONES: list[dict] = [
    {"zone": "zen.spamhaus.org",        "name": "Spamhaus ZEN",        "category": "spam"},
    {"zone": "bl.spamcop.net",          "name": "SpamCop",             "category": "spam"},
    {"zone": "dnsbl.sorbs.net",         "name": "SORBS",               "category": "spam"},
    {"zone": "b.barracudacentral.org",  "name": "Barracuda",           "category": "spam"},
    {"zone": "multi.surbl.org",         "name": "SURBL Multi",         "category": "malware"},
    {"zone": "dbl.spamhaus.org",        "name": "Spamhaus DBL",        "category": "domain"},
    {"zone": "uribl.com",               "name": "URIBL",               "category": "spam"},
    {"zone": "0spam.fusioned.net",      "name": "0spam",               "category": "spam"},
    {"zone": "psbl.surriel.com",        "name": "PSBL",                "category": "spam"},
    {"zone": "noptr.spamrats.com",      "name": "SpamRats NoPtr",      "category": "spam"},
]


def _reverse_ip(ip: str) -> str:
    """Reverse an IPv4 address for DNSBL lookup."""
    parts = ip.split(".")
    return ".".join(reversed(parts))


def _resolve_ip(domain: str) -> str | None:
    """Resolve domain to its first IPv4 address."""
    try:
        answers = dns.resolver.resolve(domain, "A", lifetime=5)
        for rdata in answers:
            return rdata.to_text()
    except Exception:
        return None


# IPs returned by blacklist services to indicate quota exceeded or access denied
# These must NOT be treated as actual listings (false positives)
_QUOTA_EXCEEDED_IPS = {
    "127.255.255.252",  # Spamhaus: query refused (need license)
    "127.255.255.253",  # Spamhaus: internal error
    "127.255.255.254",  # Spamhaus: query volume limit exceeded
    "127.255.255.255",  # Spamhaus: general error
}


def _check_dnsbl(query: str, zone: str) -> bool:
    """Return True if query.zone resolves with a real listing code.

    Filters out quota/error response codes (127.255.255.x) that services
    return when unauthenticated or when query limits are exceeded — these
    must not be treated as actual blacklist hits.
    """
    lookup = f"{query}.{zone}"
    try:
        answers = dns.resolver.resolve(lookup, "A", lifetime=3)
        ips = {rdata.to_text() for rdata in answers}
        # If every returned IP is a quota/error code, this is not a real listing
        if ips and ips.issubset(_QUOTA_EXCEEDED_IPS):
            logger.debug("DNSBL quota/error response from %s for %s: %s", zone, query, ips)
            return False
        return bool(ips)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.Timeout,
            dns.resolver.NoNameservers):
        return False
    except Exception:
        return False


def check_blacklists(domain: str) -> dict:
    """Check a domain against known DNSBL/SURBL lists.

    Returns listings per blacklist, summary counts, and risk level.
    """
    # Resolve IP for IP-based blacklists
    ip = _resolve_ip(domain)
    reversed_ip = _reverse_ip(ip) if ip else None

    listings: list[dict] = []
    listed_count = 0

    for bl in DNSBL_ZONES:
        zone = bl["zone"]
        category = bl["category"]

        # Domain-based BLs use the domain directly; IP-based use reversed IP
        if category == "domain":
            query = domain
        else:
            query = reversed_ip if reversed_ip else domain

        listed = _check_dnsbl(query, zone)
        if listed:
            listed_count += 1

        listings.append({
            "name": bl["name"],
            "zone": zone,
            "category": category,
            "listed": listed,
        })

    total = len(listings)
    if listed_count == 0:
        risk_level = "clean"
    elif listed_count <= 1:
        risk_level = "low"
    elif listed_count <= 3:
        risk_level = "medium"
    else:
        risk_level = "high"

    return {
        "domain": domain,
        "ip": ip,
        "listed_count": listed_count,
        "total_checked": total,
        "risk_level": risk_level,
        "listings": listings,
    }
