"""IP Geolocation using geoip2 + MaxMind GeoLite2 database.

Falls back to ip-api.com (free, no key required) when GeoLite2 DB is not available.
"""

from __future__ import annotations

import logging
import os

import dns.resolver
import httpx

logger = logging.getLogger(__name__)

GEOIP_DB_PATH = os.environ.get("GEOIP_DB_PATH", "/data/GeoLite2-City.mmdb")
IPAPI_URL = "http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,region,regionName,city,lat,lon,isp,org,as,query"


def _resolve_ip(domain: str) -> str | None:
    """Resolve domain to its first IPv4 address."""
    # If already an IP, return as-is
    import re
    if re.match(r"^\d+\.\d+\.\d+\.\d+$", domain):
        return domain
    try:
        answers = dns.resolver.resolve(domain, "A", lifetime=5)
        for rdata in answers:
            return rdata.to_text()
    except Exception:
        return None


def _lookup_via_geoip2(ip: str) -> dict | None:
    """Try to look up IP via local GeoLite2 database."""
    try:
        import geoip2.database
        import geoip2.errors

        with geoip2.database.Reader(GEOIP_DB_PATH) as reader:
            response = reader.city(ip)
            return {
                "ip": ip,
                "country": response.country.name,
                "country_code": response.country.iso_code,
                "region": response.subdivisions.most_specific.name if response.subdivisions else None,
                "city": response.city.name,
                "latitude": response.location.latitude,
                "longitude": response.location.longitude,
                "isp": None,
                "org": response.traits.organization if hasattr(response.traits, "organization") else None,
                "asn": None,
                "source": "geoip2",
            }
    except ImportError:
        return None
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.debug("GeoIP2 lookup failed: %s", exc)
        return None


def _lookup_via_ipapi(ip: str) -> dict:
    """Look up IP via ip-api.com (free, ~45 req/min, no key)."""
    try:
        url = IPAPI_URL.format(ip=ip)
        r = httpx.get(url, timeout=10, follow_redirects=True)
        r.raise_for_status()
        data = r.json()

        if data.get("status") != "success":
            return {
                "ip": ip,
                "error": data.get("message", "Lookup failed"),
                "source": "ip-api",
            }

        return {
            "ip": data.get("query", ip),
            "country": data.get("country"),
            "country_code": data.get("countryCode"),
            "region": data.get("regionName"),
            "city": data.get("city"),
            "latitude": data.get("lat"),
            "longitude": data.get("lon"),
            "isp": data.get("isp"),
            "org": data.get("org"),
            "asn": data.get("as"),
            "source": "ip-api",
        }
    except Exception as exc:
        logger.warning("ip-api.com lookup failed: %s", exc)
        return {"ip": ip, "error": str(exc), "source": "ip-api"}


def geolocate(domain: str) -> dict:
    """Geolocate the IP of a domain.

    Tries GeoLite2 DB first, falls back to ip-api.com.
    """
    ip = _resolve_ip(domain)
    if not ip:
        return {
            "domain": domain,
            "ip": None,
            "error": "Could not resolve domain to IP",
        }

    # Try local DB first, fallback to API
    result = _lookup_via_geoip2(ip) or _lookup_via_ipapi(ip)
    result["domain"] = domain
    return result
