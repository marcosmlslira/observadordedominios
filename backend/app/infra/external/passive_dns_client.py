"""Reverse IP lookup via HackerTarget free API."""

from __future__ import annotations

import logging

import dns.resolver
import httpx

logger = logging.getLogger(__name__)

HACKERTARGET_URL = "https://api.hackertarget.com/reverseiplookup/"
MAX_DOMAINS = 100


def _resolve_ip(domain: str) -> str | None:
    """Resolve a domain to its first IPv4 address."""
    try:
        answers = dns.resolver.resolve(domain, "A", lifetime=5)
        for rdata in answers:
            return rdata.to_text()
    except Exception:
        return None


def reverse_ip_lookup(domain: str) -> dict:
    """Find other domains hosted on the same IP as the given domain.

    Uses HackerTarget free API (1500 req/day without API key).
    """
    ip = _resolve_ip(domain)
    if not ip:
        return {
            "domain": domain,
            "ip": None,
            "domains": [],
            "total": 0,
            "error": "Could not resolve domain to IP",
        }

    try:
        response = httpx.get(
            HACKERTARGET_URL,
            params={"q": ip},
            timeout=15,
            follow_redirects=True,
        )
        response.raise_for_status()
        body = response.text.strip()

        # HackerTarget returns "error check your search parameter" or similar on bad input
        if body.startswith("error") or "API count exceeded" in body:
            return {
                "domain": domain,
                "ip": ip,
                "domains": [],
                "total": 0,
                "error": body,
            }

        # Response is newline-separated domain names
        domains = [line.strip() for line in body.splitlines() if line.strip()]
        # Exclude the original domain from the list
        other_domains = [d for d in domains if d.lower() != domain.lower()]

        return {
            "domain": domain,
            "ip": ip,
            "domains": other_domains[:MAX_DOMAINS],
            "total": len(other_domains),
            "truncated": len(other_domains) > MAX_DOMAINS,
        }

    except httpx.HTTPStatusError as exc:
        return {
            "domain": domain,
            "ip": ip,
            "domains": [],
            "total": 0,
            "error": f"HTTP {exc.response.status_code}",
        }
    except Exception as exc:
        logger.warning("Reverse IP lookup failed for %s: %s", domain, exc)
        return {
            "domain": domain,
            "ip": ip,
            "domains": [],
            "total": 0,
            "error": str(exc),
        }
