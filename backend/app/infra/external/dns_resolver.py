"""DNS resolution client using dnspython."""

from __future__ import annotations

import logging
import time

import dns.resolver
import dns.rdatatype

logger = logging.getLogger(__name__)

# Record types to query by default
DEFAULT_RECORD_TYPES = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "CAA"]


def resolve_domain(domain: str, record_types: list[str] | None = None) -> dict:
    """Resolve DNS records for a domain.

    Returns a dict with 'records', 'nameservers', 'resolution_time_ms'.
    """
    types = record_types or DEFAULT_RECORD_TYPES
    records: list[dict] = []
    nameservers: list[str] = []

    start = time.monotonic()

    for rtype in types:
        try:
            answers = dns.resolver.resolve(domain, rtype)
            for rdata in answers:
                records.append({
                    "type": rtype,
                    "name": domain,
                    "value": rdata.to_text(),
                    "ttl": answers.rrset.ttl if answers.rrset else None,
                })
        except (
            dns.resolver.NoAnswer,
            dns.resolver.NXDOMAIN,
            dns.resolver.NoNameservers,
            dns.resolver.Timeout,
        ):
            continue
        except Exception as exc:
            logger.debug("DNS query %s/%s failed: %s", domain, rtype, exc)
            continue

    # Fetch nameservers separately
    try:
        ns_answers = dns.resolver.resolve(domain, "NS")
        nameservers = [rdata.to_text().rstrip(".") for rdata in ns_answers]
    except Exception:
        pass

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return {
        "records": records,
        "nameservers": nameservers,
        "resolution_time_ms": elapsed_ms,
    }
