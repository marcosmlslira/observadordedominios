"""HTTP header analysis using httpx."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

FOLLOW_REDIRECTS_LIMIT = 10
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 15

# Security headers to check
SECURITY_HEADERS = [
    {
        "name": "Strict-Transport-Security",
        "severity_missing": "critical",
        "description": "Enforces HTTPS connections",
    },
    {
        "name": "Content-Security-Policy",
        "severity_missing": "critical",
        "description": "Prevents XSS and injection attacks",
    },
    {
        "name": "X-Frame-Options",
        "severity_missing": "warning",
        "description": "Prevents clickjacking attacks",
    },
    {
        "name": "X-Content-Type-Options",
        "severity_missing": "warning",
        "description": "Prevents MIME type sniffing",
    },
    {
        "name": "Referrer-Policy",
        "severity_missing": "warning",
        "description": "Controls referrer information",
    },
    {
        "name": "Permissions-Policy",
        "severity_missing": "warning",
        "description": "Controls browser feature access",
    },
    {
        "name": "X-XSS-Protection",
        "severity_missing": "warning",
        "description": "Legacy XSS protection header",
    },
]


def analyze_http_headers(domain: str) -> dict:
    """Fetch a domain over HTTPS (fallback HTTP) and analyze headers.

    Returns a dict with the headers payload (placed into ToolResponse.result).
    """
    redirect_chain: list[dict] = []
    url = f"https://{domain}"

    try:
        with httpx.Client(
            follow_redirects=True,
            max_redirects=FOLLOW_REDIRECTS_LIMIT,
            timeout=httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT),
            verify=False,
        ) as client:
            response = client.get(url)

            # Build redirect chain from history
            for r in response.history:
                redirect_chain.append({
                    "url": str(r.url),
                    "status_code": r.status_code,
                })

    except httpx.ConnectError:
        # Fallback to HTTP
        url = f"http://{domain}"
        try:
            with httpx.Client(
                follow_redirects=True,
                max_redirects=FOLLOW_REDIRECTS_LIMIT,
                timeout=httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT),
            ) as client:
                response = client.get(url)
                for r in response.history:
                    redirect_chain.append({
                        "url": str(r.url),
                        "status_code": r.status_code,
                    })
        except Exception as exc:
            raise RuntimeError(f"Failed to connect to {domain}: {exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Failed to connect to {domain}: {exc}") from exc

    headers = dict(response.headers)

    # Analyze security headers
    security_headers = []
    for sh in SECURITY_HEADERS:
        value = headers.get(sh["name"].lower())
        security_headers.append({
            "name": sh["name"],
            "value": value,
            "present": value is not None,
            "severity": "good" if value else sh["severity_missing"],
            "description": sh["description"],
        })

    return {
        "final_url": str(response.url),
        "status_code": response.status_code,
        "headers": headers,
        "security_headers": security_headers,
        "redirect_chain": redirect_chain,
        "server": headers.get("server"),
        "content_type": headers.get("content-type"),
    }
