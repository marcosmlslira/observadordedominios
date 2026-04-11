"""PhishTank URL lookup client."""

from __future__ import annotations

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

PHISHTANK_CHECK_URL = "https://checkurl.phishtank.com/checkurl/"


def check_phishtank(target: str) -> dict:
    """Check a URL against PhishTank database.

    POST com Content-Type x-www-form-urlencoded. app_key opcional mas recomendada
    (sem ela, rate limit agressivo). Com cache de 1h no BaseToolService, impacto mínimo.

    Returns:
        {
            "in_database": bool,
            "verified": bool,       # comunidade verificou como phishing
            "valid": bool,          # ainda ativa
            "phish_id": str | None,
        }
    """
    url_to_check = target if target.startswith("http") else f"http://{target}"

    form_data: dict[str, str] = {"url": url_to_check, "format": "json"}
    app_key = settings.PHISHTANK_APP_KEY
    if app_key:
        form_data["app_key"] = app_key

    try:
        resp = httpx.post(
            PHISHTANK_CHECK_URL,
            data=form_data,
            headers={"User-Agent": "phishtank/observadordedominios"},
            timeout=10,
        )
        resp.raise_for_status()
        data_resp = resp.json()
    except Exception as exc:
        logger.warning("PhishTank API error for %s: %s", target, exc)
        return {"in_database": False, "verified": False, "valid": False, "phish_id": None, "error": str(exc)}

    results = data_resp.get("results") or {}
    return {
        "in_database": bool(results.get("in_database")),
        "verified": bool(results.get("verified")),
        "valid": bool(results.get("valid")),
        "phish_id": results.get("phish_id"),
    }
