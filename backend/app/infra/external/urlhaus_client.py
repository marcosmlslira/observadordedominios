"""URLhaus (abuse.ch) host lookup client."""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

URLHAUS_API_URL = "https://urlhaus-api.abuse.ch/v1/host/"


def check_urlhaus(target: str) -> dict:
    """Query URLhaus for a host (domain or IP).

    Requer Auth-Token (gratuito em abuse.ch/api). Sem token, retorna skipped=True.

    Returns:
        {
            "query_status": str,      # "is_host" | "no_results" | "invalid_host"
            "is_listed": bool,
            "urls_count": int,
            "urls": list[dict],       # amostra (max 10)
            "skipped": bool,
        }
    """
    auth_token = settings.URLHAUS_AUTH_TOKEN
    if not auth_token:
        return {"query_status": "skipped", "is_listed": False, "urls_count": 0, "urls": [], "skipped": True}

    host = target.replace("http://", "").replace("https://", "").split("/")[0]

    try:
        resp = httpx.post(
            URLHAUS_API_URL,
            data={"host": host},
            headers={"Auth-Token": auth_token},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("URLhaus API error for %s: %s", target, exc)
        return {"query_status": "error", "is_listed": False, "urls_count": 0, "urls": [], "error": str(exc), "skipped": False}

    query_status = data.get("query_status", "")
    urls = (data.get("urls") or [])[:10]

    return {
        "query_status": query_status,
        "is_listed": query_status == "is_host",
        "urls_count": data.get("urls_count") or 0,
        "urls": urls,
        "skipped": False,
    }
