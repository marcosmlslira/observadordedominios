"""Phase 2 — LLM-powered seed generation via Groq (primary) or OpenRouter (fallback).

Gated by SEED_LLM_GENERATION_ENABLED flag. When disabled, returns [].
Provider selection: GROQ_API_KEY takes priority; falls back to OPENROUTER_API_KEY.
"""

from __future__ import annotations

import json
import logging
import time

logger = logging.getLogger(__name__)

_SEED_PROMPT_TEMPLATE = """\
Você é um especialista em proteção de marca e segurança cibernética.

PERFIL DA MARCA:
- Nome: {brand_name}
- Domínio oficial: {official_domain}
- Segmento: {segment}
- Palavras-chave: {keywords}

Gere uma lista de variações de domínio que agentes maliciosos usariam para enganar usuários,
incluindo: combos com palavras de abuso, typosquatting, engenharia social, termos financeiros.

Responda APENAS com JSON válido:
{{
  "seeds": [
    {{"seed_value": "<label sem TLD>", "seed_type": "<llm_combo|llm_semantic|llm_social_engineering>", "rationale": "<motivo breve>"}},
    ...
  ]
}}

Máximo de {max_seeds} seeds. seed_value deve ser apenas o label (sem '.com', sem TLD).
Prefira seeds que não sejam variações óbvias — foque em engenharia social e combos criativos.
"""


def generate_llm_seeds(
    brand_name: str,
    official_domain: str,
    segment: str,
    keywords: list[str],
    *,
    language: str = "pt-BR",
    max_seeds: int = 100,
) -> list[dict]:
    """Generate LLM-based brand abuse seeds.

    Uses Groq (primary) if GROQ_API_KEY is set; falls back to OpenRouter.
    Returns [] when SEED_LLM_GENERATION_ENABLED is False or no API key is configured.
    """
    from app.core.config import settings
    if not settings.SEED_LLM_GENERATION_ENABLED:
        return []

    groq_key = getattr(settings, "GROQ_API_KEY", "") or ""
    openrouter_key = getattr(settings, "OPENROUTER_API_KEY", "") or ""

    if groq_key.strip():
        api_key = groq_key.strip()
        base_url = getattr(settings, "GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        model = getattr(settings, "GROQ_MODEL", "llama-3.3-70b-versatile")
        provider = "Groq"
    elif openrouter_key.strip():
        api_key = openrouter_key.strip()
        base_url = getattr(settings, "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
        model = "meta-llama/llama-3.3-70b-instruct:free"
        provider = "OpenRouter"
    else:
        logger.warning("SEED_LLM_GENERATION_ENABLED=true but no API key configured — skipping")
        return []

    try:
        return _call_llm_api(
            api_key=api_key,
            base_url=base_url,
            model=model,
            provider=provider,
            brand_name=brand_name,
            official_domain=official_domain,
            segment=segment or "geral",
            keywords=keywords,
            max_seeds=max_seeds,
        )
    except Exception:
        logger.exception("LLM seed generation failed for brand=%s — returning []", brand_name)
        return []


def _call_llm_api(
    api_key: str,
    base_url: str,
    model: str,
    provider: str,
    brand_name: str,
    official_domain: str,
    segment: str,
    keywords: list[str],
    max_seeds: int,
) -> list[dict]:
    import httpx

    prompt = _SEED_PROMPT_TEMPLATE.format(
        brand_name=brand_name,
        official_domain=official_domain,
        segment=segment,
        keywords=", ".join(keywords[:20]) if keywords else "nenhuma",
        max_seeds=max_seeds,
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
        "temperature": 0.7,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    # OpenRouter-specific headers (ignored by Groq)
    if "openrouter" in base_url:
        headers["HTTP-Referer"] = "https://observadordedominios.com.br"
        headers["X-Title"] = "Observador de Dominios - Seed Generator"

    with httpx.Client(timeout=60.0) as client:
        for attempt in range(3):
            resp = client.post(f"{base_url}/chat/completions", json=payload, headers=headers)
            if resp.status_code == 429:
                wait = 2 ** attempt * 10  # 10s, 20s, 40s
                logger.warning("%s 429 rate limit — retrying in %ds (attempt %d/3)", provider, wait, attempt + 1)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            break
        else:
            raise httpx.HTTPStatusError(
                f"{provider} rate limit after 3 attempts",
                request=resp.request,
                response=resp,
            )

    content = resp.json()["choices"][0]["message"]["content"]

    # Extract JSON from response
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Try to extract JSON block from markdown fence
        import re
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
        else:
            logger.warning("LLM seed response not valid JSON — skipping")
            return []

    raw_seeds = data.get("seeds", [])
    if not isinstance(raw_seeds, list):
        return []

    from app.services.monitoring_profile import SEED_BASE_WEIGHTS, normalize_brand_text

    result: list[dict] = []
    seen: set[str] = set()
    valid_types = {"llm_combo", "llm_semantic", "llm_social_engineering"}

    for item in raw_seeds:
        seed_value = normalize_brand_text(str(item.get("seed_value", "")))
        seed_type = str(item.get("seed_type", "llm_combo"))
        if seed_type not in valid_types:
            seed_type = "llm_combo"
        if not seed_value or len(seed_value) < 3:
            continue
        if seed_value in seen:
            continue
        seen.add(seed_value)
        result.append({
            "source_ref_type": "llm_seed",
            "source_ref_id": None,
            "seed_value": seed_value,
            "seed_type": seed_type,
            "channel_scope": "registrable_domain",
            "base_weight": SEED_BASE_WEIGHTS.get(seed_type, 0.45),
        })

    logger.info("LLM seed generation produced %d seeds for brand=%s", len(result), brand_name)
    return result[:max_seeds]
