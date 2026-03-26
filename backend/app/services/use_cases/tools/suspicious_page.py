"""Suspicious Page Detector — rule-based analysis of page content."""

from __future__ import annotations

import logging
import re

import httpx
try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover - exercised in lean test envs
    BeautifulSoup = None

from app.core.config import settings
from app.services.registrable_domain import parse_registrable_domain
from app.services.use_cases.tools.base import BaseToolService

logger = logging.getLogger(__name__)

# Credential-related terms
CREDENTIAL_TERMS = {
    "password", "senha", "login", "sign in", "sign-in", "signin",
    "log in", "log-in", "entrar", "acessar", "authenticate",
    "username", "usuário", "email", "cpf", "cnpj", "cartão",
    "credit card", "card number", "cvv", "ssn", "social security",
    "bank account", "conta bancária",
}

# Brand impersonation patterns
BRAND_PATTERNS = [
    r"banco\s*(do\s*brasil|itau|bradesco|santander|caixa|nubank)",
    r"correios",
    r"receita\s*federal",
    r"gov\.br",
]

# Urgency / social engineering phrases
URGENCY_TERMS = {
    "your account has been", "sua conta foi", "verify your",
    "verifique sua", "suspended", "suspens", "unauthorized",
    "não autorizado", "immediately", "imediatamente",
    "expires today", "expira hoje", "act now", "aja agora",
    "limited time", "tempo limitado", "click here", "clique aqui",
}

PARKED_PATTERNS = (
    "this domain is for sale",
    "buy this domain",
    "domain for sale",
    "parked free",
    "parked domain",
    "afternic",
    "sedo",
    "dan.com",
    "undeveloped",
)

CHALLENGE_PATTERNS = (
    "access denied",
    "attention required",
    "checking your browser",
    "ddos-guard",
    "cloudflare",
    "temporarily unavailable",
    "service unavailable",
)


class SuspiciousPageService(BaseToolService):
    tool_type = "suspicious_page"
    cache_ttl_seconds = settings.TOOLS_CACHE_SUSPICIOUS_PAGE
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        if BeautifulSoup is None:
            raise RuntimeError("BeautifulSoup is not installed")
        page = self._fetch_page(target)
        if not page:
            return {
                "risk_score": 0.0,
                "risk_level": "inconclusive",
                "signals": [],
                "page_title": None,
                "final_url": None,
                "http_status": None,
                "page_disposition": "unreachable",
                "has_login_form": False,
                "has_credential_inputs": False,
                "external_resource_count": 0,
                "confidence": 0.0,
                "data_quality": "inconclusive",
            }

        html = page["html"]
        soup = BeautifulSoup(html, "html.parser")
        text_content = soup.get_text(separator=" ", strip=True).lower()
        page_title = soup.title.string.strip() if soup.title and soup.title.string else None
        final_url = page["final_url"]
        http_status = page["status_code"]
        server_header = page["server"]

        signals: list[dict] = []
        page_disposition = "live"

        parked_hit = self._find_first_match(
            [page_title or "", final_url, text_content],
            PARKED_PATTERNS,
        )
        if parked_hit:
            page_disposition = "parked"
            signals.append({
                "category": "parked_domain",
                "description": f"Parked or for-sale page detected via '{parked_hit}'",
                "severity": "low",
            })

        challenge_hit = self._find_first_match(
            [page_title or "", final_url, text_content, server_header or ""],
            CHALLENGE_PATTERNS,
        )
        if challenge_hit or http_status in {401, 403, 429, 503}:
            if page_disposition != "parked":
                page_disposition = "challenge"
            signals.append({
                "category": "protected_page",
                "description": (
                    f"Protected or blocked page detected"
                    + (f" via '{challenge_hit}'" if challenge_hit else f" (HTTP {http_status})")
                ),
                "severity": "medium",
            })
        if server_header and "ddos-guard" in server_header.lower():
            signals.append({
                "category": "infrastructure_masking",
                "description": "Hosted behind DDoS-Guard shielding",
                "severity": "medium",
            })

        # Check login forms
        has_login_form = False
        has_credential_inputs = False
        password_inputs = soup.find_all("input", attrs={"type": "password"})
        if password_inputs:
            has_credential_inputs = True
            signals.append({
                "category": "credential_harvesting",
                "description": f"Found {len(password_inputs)} password input field(s)",
                "severity": "high",
            })

        forms = soup.find_all("form")
        for form in forms:
            inputs = form.find_all("input")
            input_types = [i.get("type", "text").lower() for i in inputs]
            if "password" in input_types:
                has_login_form = True
                action = form.get("action", "")
                if action and not action.startswith("/"):
                    signals.append({
                        "category": "credential_harvesting",
                        "description": f"Login form posts to external URL: {action[:100]}",
                        "severity": "critical",
                    })

        # Check credential terms in text
        found_terms = [t for t in CREDENTIAL_TERMS if t in text_content]
        if len(found_terms) >= 3:
            signals.append({
                "category": "credential_harvesting",
                "description": f"Multiple credential-related terms found: {', '.join(found_terms[:5])}",
                "severity": "medium",
            })

        # Check urgency language before brand checks so we can require both cues together.
        found_urgency = [t for t in URGENCY_TERMS if t in text_content]
        if found_urgency:
            signals.append({
                "category": "social_engineering",
                "description": f"Urgency language detected: {', '.join(found_urgency[:3])}",
                "severity": "medium",
            })

        target_label = parse_registrable_domain(target).registrable_label

        # Check brand impersonation conservatively to avoid false positives from assets or boilerplate.
        for pattern in BRAND_PATTERNS:
            match = re.search(pattern, f"{page_title or ''} {text_content}", re.IGNORECASE)
            if match:
                brand = match.group().lower()
                if brand not in target_label and (has_login_form or has_credential_inputs or found_urgency):
                    signals.append({
                        "category": "brand_impersonation",
                        "description": f"References brand '{brand}' not in domain name",
                        "severity": "high",
                    })
                    break

        # Check external resources
        external_count = 0
        for tag in soup.find_all(["script", "link", "img"]):
            src = tag.get("src") or tag.get("href") or ""
            if src.startswith("http") and target not in src:
                external_count += 1
        if external_count > 20:
            signals.append({
                "category": "resource_loading",
                "description": f"{external_count} external resources loaded from other domains",
                "severity": "low",
            })

        # Calculate risk score
        severity_weights = {"critical": 0.4, "high": 0.25, "medium": 0.15, "low": 0.05}
        risk_score = min(1.0, sum(severity_weights.get(s["severity"], 0) for s in signals))

        data_quality = "complete"
        if page_disposition == "challenge":
            data_quality = "degraded"
        if risk_score >= 0.7:
            risk_level = "critical"
        elif risk_score >= 0.5:
            risk_level = "high"
        elif risk_score >= 0.3:
            risk_level = "medium"
        elif risk_score > 0:
            risk_level = "low"
        elif page_disposition == "challenge":
            risk_level = "protected"
        else:
            risk_level = "safe"

        return {
            "risk_score": round(risk_score, 2),
            "risk_level": risk_level,
            "signals": signals,
            "page_title": page_title,
            "final_url": final_url,
            "http_status": http_status,
            "page_disposition": page_disposition,
            "has_login_form": has_login_form,
            "has_credential_inputs": has_credential_inputs,
            "external_resource_count": external_count,
            "confidence": 0.45 if page_disposition == "challenge" else 0.85,
            "data_quality": data_quality,
        }

    def _fetch_page(self, domain: str) -> dict | None:
        for scheme in ("https", "http"):
            try:
                with httpx.Client(
                    follow_redirects=True,
                    timeout=httpx.Timeout(10, read=15),
                    verify=False,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; ObsBot/1.0)"},
                ) as client:
                    resp = client.get(f"{scheme}://{domain}")
                    return {
                        "html": resp.text,
                        "final_url": str(resp.url),
                        "status_code": resp.status_code,
                        "server": resp.headers.get("server"),
                    }
            except Exception:
                continue
        return None

    @staticmethod
    def _find_first_match(values: list[str], patterns: tuple[str, ...]) -> str | None:
        for value in values:
            haystack = value.lower()
            for pattern in patterns:
                if pattern in haystack:
                    return pattern
        return None
