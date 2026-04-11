"""Dangling DNS / subdomain takeover detector."""

from __future__ import annotations

import logging

import dns.resolver
import httpx

logger = logging.getLogger(__name__)

# Fingerprints: (service_name, substring no body HTTP)
# Fonte: https://github.com/EdOverflow/can-i-take-over-xyz
TAKEOVER_FINGERPRINTS: list[tuple[str, str]] = [
    ("GitHub Pages", "There isn't a GitHub Pages site here"),
    ("GitHub Pages", "For root URLs (like http://example.com/) you must provide an index.html file"),
    ("Amazon S3", "NoSuchBucket"),
    ("Amazon S3", "The specified bucket does not exist"),
    ("Heroku", "No such app"),
    ("Heroku", "herokucdn.com/error-pages/no-such-app"),
    ("Fastly", "Fastly error: unknown domain"),
    ("Shopify", "Sorry, this shop is currently unavailable"),
    ("Shopify", "Only one step away from your own online store"),
    ("Zendesk", "Help Center Closed"),
    ("Surge.sh", "project not found"),
    ("Tumblr", "Whatever you were looking for doesn't currently exist at this address"),
    ("Ghost", "The thing you were looking for is no longer here"),
    ("Bitbucket", "Repository not found"),
]

CONNECT_TIMEOUT = 8
READ_TIMEOUT = 8


def check_takeover(domain: str) -> dict:
    """Check if a domain/subdomain is vulnerable to takeover via dangling CNAME.

    Resolve CNAME chain e verifica HTTP response contra fingerprints de serviços desprovisionados.

    Returns:
        {
            "is_vulnerable": bool,
            "cname_chain": list[str],
            "vulnerable_cname": str | None,
            "fingerprint_matched": str | None,
            "service": str | None,
            "checked_url": str | None,
        }
    """
    cname_chain = _resolve_cname_chain(domain)

    if not cname_chain:
        return {
            "is_vulnerable": False,
            "cname_chain": [],
            "vulnerable_cname": None,
            "fingerprint_matched": None,
            "service": None,
            "checked_url": None,
        }

    final_cname = cname_chain[-1]
    checked_url = f"http://{domain}"

    try:
        resp = httpx.get(
            checked_url,
            follow_redirects=True,
            timeout=httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT),
            headers={"User-Agent": "ObservadorDominios/1.0 security-scanner"},
        )
        body = resp.text
    except (httpx.ConnectError, httpx.TimeoutException):
        body = ""
    except Exception as exc:
        logger.debug("HTTP check failed for %s: %s", domain, exc)
        return {
            "is_vulnerable": False,
            "cname_chain": cname_chain,
            "vulnerable_cname": final_cname,
            "fingerprint_matched": None,
            "service": None,
            "checked_url": checked_url,
            "error": str(exc),
        }

    for service_name, fingerprint in TAKEOVER_FINGERPRINTS:
        if fingerprint.lower() in body.lower():
            logger.info("Subdomain takeover detected: %s -> %s (%s)", domain, final_cname, service_name)
            return {
                "is_vulnerable": True,
                "cname_chain": cname_chain,
                "vulnerable_cname": final_cname,
                "fingerprint_matched": fingerprint,
                "service": service_name,
                "checked_url": checked_url,
            }

    return {
        "is_vulnerable": False,
        "cname_chain": cname_chain,
        "vulnerable_cname": final_cname,
        "fingerprint_matched": None,
        "service": None,
        "checked_url": checked_url,
    }


def _resolve_cname_chain(domain: str, max_depth: int = 10) -> list[str]:
    """Follow CNAME chain. Returns list of CNAME targets (empty if no CNAMEs)."""
    chain: list[str] = []
    current = domain

    for _ in range(max_depth):
        try:
            answers = dns.resolver.resolve(current, "CNAME")
            target = answers[0].to_text().rstrip(".")
            chain.append(target)
            current = target
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            break
        except Exception as exc:
            logger.debug("CNAME resolution error for %s: %s", current, exc)
            break

    return chain
