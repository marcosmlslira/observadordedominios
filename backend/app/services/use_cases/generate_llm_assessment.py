"""LLM-powered domain assessment via OpenRouter.

Called at the end of enrich_similarity_match() for medium/high/critical risk
matches when OPENROUTER_API_KEY is configured. Returns a structured parecer
(expert opinion) in Portuguese.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_GATE_RISK_LEVELS = {"medium", "high", "critical"}
_GATE_ATTENTION_BUCKETS = {"immediate_attention", "defensive_gap"}

_PROMPT_TEMPLATE = """\
Você é um especialista em segurança cibernética analisando um domínio suspeito.

DADOS DO DOMÍNIO:
{summary_json}

Raciocine passo a passo:
1. O domínio é visualmente similar à marca? Como?
2. Os dados técnicos (DNS, WHOIS, HTTP, email) confirmam atividade maliciosa?
3. Qual o nível de risco real considerando todos os sinais?

Responda APENAS com JSON válido neste formato exato:
{{
  "risco_score": <0-100>,
  "categoria": "<Phishing Provável|Tiposquatting|Homograph|Legítimo|Alto Risco Corporativo>",
  "parecer_resumido": "<6-8 linhas em português claro e profissional>",
  "principais_motivos": ["<motivo1>", "<motivo2>", "<motivo3>"],
  "recomendacao_acao": "<Bloquear imediatamente|Monitorar|Ignorar>",
  "confianca": <0-100>
}}"""


def should_generate_assessment(match: dict, api_key: str) -> bool:
    """Gate: only runs for medium+ risk matches with a configured API key."""
    if not api_key or not api_key.strip():
        return False

    risk_level = (match.get("risk_level") or "").lower()
    attention_bucket = (match.get("attention_bucket") or "").lower()

    return risk_level in _GATE_RISK_LEVELS or attention_bucket in _GATE_ATTENTION_BUCKETS


def build_domain_summary(
    match: dict,
    brand_name: str,
    tool_results: dict[str, dict],
    signals: list[dict],
) -> dict:
    """Compile all collected intel into a structured JSON for the LLM."""
    whois_result = (tool_results.get("whois") or {}).get("result") or {}
    dns_result = (tool_results.get("dns_lookup") or {}).get("result") or {}
    http_result = (tool_results.get("http_headers") or {}).get("result") or {}
    page_result = (tool_results.get("suspicious_page") or {}).get("result") or {}
    email_result = (tool_results.get("email_security") or {}).get("result") or {}
    geo_result = (tool_results.get("ip_geolocation") or {}).get("result") or {}

    # Compute age_days from WHOIS creation_date
    age_days: int | None = None
    creation_raw = str(whois_result.get("creation_date") or "").strip()
    if creation_raw:
        parsed = _parse_date(creation_raw)
        if parsed:
            age_days = max(0, int((datetime.now(timezone.utc) - parsed).total_seconds() // 86400))

    # DNS record types
    records = dns_result.get("records") or []
    dns_types = sorted({str(r.get("type", "")).upper() for r in records if r.get("type")})

    # Email spoofing risk
    spoofing_risk = email_result.get("spoofing_risk")
    if isinstance(spoofing_risk, dict):
        spoofing_risk = spoofing_risk.get("level", "unknown")

    domain = str(match.get("domain_name") or "")
    tld = str(match.get("tld") or "")
    full_domain = domain if domain.endswith(f".{tld}") else f"{domain}.{tld}"

    return {
        "marca_monitorada": brand_name,
        "dominio_suspeito": full_domain,
        "score_similaridade": round(float(match.get("score_final") or 0), 4),
        "score_acionabilidade": round(float(match.get("actionability_score") or 0), 4),
        "nivel_risco": match.get("risk_level"),
        "bucket_atencao": match.get("attention_bucket"),
        "regra_deteccao": match.get("matched_rule"),
        "motivos_deteccao": list(match.get("reasons") or []),
        "whois": {
            "idade_dias": age_days,
            "registrar": whois_result.get("registrar"),
            "pais_registrante": whois_result.get("registrant_country"),
        },
        "dns": {
            "tipos_registros": dns_types,
            "tem_mx": "MX" in dns_types,
            "tem_web": bool({"A", "AAAA"} & set(dns_types)),
        },
        "http": {
            "status_code": http_result.get("status_code"),
            "url_final": http_result.get("final_url"),
        },
        "pagina": {
            "disposicao": page_result.get("page_disposition"),
            "nivel_risco": page_result.get("risk_level"),
            "tem_formulario_login": page_result.get("has_login_form"),
            "tem_captura_credenciais": page_result.get("has_credential_inputs"),
        },
        "email_seguranca": {
            "risco_spoofing": spoofing_risk,
        },
        "geolocalizacao": {
            "pais": geo_result.get("country_code"),
            "org": geo_result.get("org"),
        },
        "sinais_enriquecimento": [
            {"codigo": s.get("code"), "severidade": s.get("severity")}
            for s in signals
        ],
    }


def generate_llm_assessment(
    match: dict,
    brand_name: str,
    tool_results: dict[str, dict],
    signals: list[dict],
) -> dict | None:
    """Generate LLM-powered assessment. Returns dict or None if not applicable/failed."""
    from app.core.config import settings
    from app.infra.external.openrouter_client import OpenRouterClient

    if not should_generate_assessment(match, settings.OPENROUTER_API_KEY):
        return None

    try:
        summary = build_domain_summary(match, brand_name, tool_results, signals)
        summary_json = json.dumps(summary, ensure_ascii=False, indent=2)
        prompt = _PROMPT_TEMPLATE.format(summary_json=summary_json)

        client = OpenRouterClient(
            api_key=settings.OPENROUTER_API_KEY,
            base_url=settings.OPENROUTER_BASE_URL,
            timeout=settings.OPENROUTER_TIMEOUT_SECONDS,
        )
        raw = client.complete(
            messages=[{"role": "user", "content": prompt}],
        )

        parsed = _parse_llm_response(raw)
        if parsed:
            logger.info(
                "LLM assessment generated for %s: risco=%s categoria=%s",
                summary["dominio_suspeito"],
                parsed.get("risco_score"),
                parsed.get("categoria"),
            )
        return parsed

    except Exception as exc:
        logger.warning("LLM assessment failed for match %s: %s", match.get("domain_name"), exc)
        return None


def _parse_llm_response(raw: str) -> dict | None:
    """Extract and validate the JSON payload from the LLM response."""
    raw = raw.strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(
            line for line in lines
            if not line.startswith("```")
        ).strip()

    # Find JSON boundaries (LLM sometimes adds reasoning text before the JSON)
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        logger.warning("LLM response has no JSON object: %r", raw[:200])
        return None

    try:
        data = json.loads(raw[start:end])
    except json.JSONDecodeError as exc:
        logger.warning("LLM JSON parse error: %s — raw: %r", exc, raw[:300])
        return None

    required = {"risco_score", "categoria", "parecer_resumido", "principais_motivos", "recomendacao_acao", "confianca"}
    if not required.issubset(data.keys()):
        missing = required - data.keys()
        logger.warning("LLM response missing keys: %s", missing)
        return None

    # Coerce numeric fields to int (LLM may return strings)
    try:
        data["risco_score"] = int(data["risco_score"])
        data["confianca"] = int(data["confianca"])
    except (TypeError, ValueError):
        pass

    return data


def _parse_date(value: str):
    """Parse ISO-like datetime string, return UTC datetime or None."""
    for candidate in (value.strip(), value.strip().replace("Z", "+00:00")):
        try:
            from datetime import timezone as tz
            from datetime import datetime as dt
            parsed = dt.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=tz.utc)
            return parsed.astimezone(tz.utc)
        except ValueError:
            continue
    return None
