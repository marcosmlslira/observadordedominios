"""Google Safe Browsing Lookup API v4 client."""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

SAFE_BROWSING_URL = "https://safebrowsing.googleapis.com/v4/threatMatches:find"

THREAT_TYPES = [
    "MALWARE",
    "SOCIAL_ENGINEERING",
    "UNWANTED_SOFTWARE",
    "POTENTIALLY_HARMFUL_APPLICATION",
]
PLATFORM_TYPES = ["ANY_PLATFORM"]
THREAT_ENTRY_TYPES = ["URL"]


def check_safe_browsing(target: str) -> dict:
    """Check a URL/domain against Google Safe Browsing lists.

    Args:
        target: Domain name or full URL to check.

    Returns:
        {
            "is_listed": bool,
            "threat_types": list[str],   # ex: ["MALWARE", "SOCIAL_ENGINEERING"]
            "skipped": bool,             # True quando API key não configurada
        }
    """
    api_key = settings.GOOGLE_SAFE_BROWSING_API_KEY
    if not api_key:
        logger.debug("GOOGLE_SAFE_BROWSING_API_KEY not set — skipping")
        return {"is_listed": False, "threat_types": [], "skipped": True}

    # Safe Browsing espera URL completa
    url_to_check = target if target.startswith("http") else f"http://{target}"

    payload = {
        "client": {"clientId": "observadordedominios", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": THREAT_TYPES,
            "platformTypes": PLATFORM_TYPES,
            "threatEntryTypes": THREAT_ENTRY_TYPES,
            "threatEntries": [{"url": url_to_check}],
        },
    }

    try:
        resp = httpx.post(
            SAFE_BROWSING_URL,
            params={"key": api_key},
            json=payload,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as exc:
        logger.warning("Safe Browsing API HTTP error: %s", exc)
        return {"is_listed": False, "threat_types": [], "skipped": False, "error": str(exc)}
    except Exception as exc:
        logger.warning("Safe Browsing API error: %s", exc)
        return {"is_listed": False, "threat_types": [], "skipped": False, "error": str(exc)}

    # API retorna {} (vazio) quando NÃO listado. Presença de "matches" = listagem.
    matches = data.get("matches") or []
    threat_types = sorted({m.get("threatType") for m in matches if m.get("threatType")})

    return {
        "is_listed": bool(matches),
        "threat_types": threat_types,
        "skipped": False,
    }
