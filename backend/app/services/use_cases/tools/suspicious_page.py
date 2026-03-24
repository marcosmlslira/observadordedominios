"""Suspicious Page Detector — rule-based analysis of page content."""

from __future__ import annotations

import logging
import re

import httpx
from bs4 import BeautifulSoup

from app.core.config import settings
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
    r"paypal", r"apple", r"microsoft", r"google", r"amazon",
    r"netflix", r"facebook", r"instagram", r"whatsapp",
    r"banco\s*(do\s*brasil|itau|bradesco|santander|caixa|nubank)",
    r"correios", r"receita\s*federal", r"gov\.br",
]

# Urgency / social engineering phrases
URGENCY_TERMS = {
    "your account has been", "sua conta foi", "verify your",
    "verifique sua", "suspended", "suspens", "unauthorized",
    "não autorizado", "immediately", "imediatamente",
    "expires today", "expira hoje", "act now", "aja agora",
    "limited time", "tempo limitado", "click here", "clique aqui",
}


class SuspiciousPageService(BaseToolService):
    tool_type = "suspicious_page"
    cache_ttl_seconds = settings.TOOLS_CACHE_SUSPICIOUS_PAGE
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        html = self._fetch_html(target)
        if not html:
            return {
                "risk_score": 0.0,
                "risk_level": "safe",
                "signals": [],
                "page_title": None,
                "has_login_form": False,
                "has_credential_inputs": False,
                "external_resource_count": 0,
            }

        soup = BeautifulSoup(html, "html.parser")
        text_content = soup.get_text(separator=" ", strip=True).lower()
        page_title = soup.title.string.strip() if soup.title and soup.title.string else None

        signals: list[dict] = []

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

        # Check brand impersonation
        for pattern in BRAND_PATTERNS:
            if re.search(pattern, text_content, re.IGNORECASE):
                brand = re.search(pattern, text_content, re.IGNORECASE).group()
                if brand.lower() not in target.lower():
                    signals.append({
                        "category": "brand_impersonation",
                        "description": f"References brand '{brand}' not in domain name",
                        "severity": "high",
                    })
                    break

        # Check urgency language
        found_urgency = [t for t in URGENCY_TERMS if t in text_content]
        if found_urgency:
            signals.append({
                "category": "social_engineering",
                "description": f"Urgency language detected: {', '.join(found_urgency[:3])}",
                "severity": "medium",
            })

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

        if risk_score >= 0.7:
            risk_level = "critical"
        elif risk_score >= 0.5:
            risk_level = "high"
        elif risk_score >= 0.3:
            risk_level = "medium"
        elif risk_score > 0:
            risk_level = "low"
        else:
            risk_level = "safe"

        return {
            "risk_score": round(risk_score, 2),
            "risk_level": risk_level,
            "signals": signals,
            "page_title": page_title,
            "has_login_form": has_login_form,
            "has_credential_inputs": has_credential_inputs,
            "external_resource_count": external_count,
        }

    def _fetch_html(self, domain: str) -> str | None:
        for scheme in ("https", "http"):
            try:
                with httpx.Client(
                    follow_redirects=True,
                    timeout=httpx.Timeout(10, read=15),
                    verify=False,
                ) as client:
                    resp = client.get(f"{scheme}://{domain}")
                    return resp.text
            except Exception:
                continue
        return None
