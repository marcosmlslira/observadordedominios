# GAP 2 — URLhaus + PhishTank

**Prioridade:** Alta | **Peso:** 80 | **Fase:** 1

---

## Contexto

**URLhaus** (abuse.ch) — feed colaborativo de URLs de distribuição de malware. Sem autenticação. Cobertura ampla de campanhas ativas.

**PhishTank** (OpenDNS/Cisco) — base verificada por comunidade de URLs de phishing. "Verificado" = múltiplos usuários confirmaram phishing ativo.

O sistema atual usa DNSBL (`blacklist_check`) mas **não consulta** feeds de URL em tempo real. Este gap adiciona:
- 2 tools manuais: `/v1/tools/urlhaus_check` e `/v1/tools/phishtank_check`
- Ambas integradas no pipeline com uma função `_apply_threat_feed_adjustments()` combinada

---

## 1. Criar `backend/app/infra/external/urlhaus_client.py`

```python
"""URLhaus (abuse.ch) host lookup client."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

URLHAUS_API_URL = "https://urlhaus-api.abuse.ch/v1/host/"


def check_urlhaus(target: str) -> dict:
    """Query URLhaus for a host (domain or IP).

    A API aceita domínio sem esquema, via POST com Content-Type x-www-form-urlencoded.
    Sem autenticação.

    Returns:
        {
            "query_status": str,      # "is_host" | "no_results" | "invalid_host"
            "is_listed": bool,
            "urls_count": int,
            "urls": list[dict],       # amostra (max 10)
        }
    """
    host = target.replace("http://", "").replace("https://", "").split("/")[0]

    try:
        resp = httpx.post(URLHAUS_API_URL, data={"host": host}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("URLhaus API error for %s: %s", target, exc)
        return {"query_status": "error", "is_listed": False, "urls_count": 0, "urls": [], "error": str(exc)}

    query_status = data.get("query_status", "")
    urls = (data.get("urls") or [])[:10]

    return {
        "query_status": query_status,
        "is_listed": query_status == "is_host",
        "urls_count": data.get("urls_count") or 0,
        "urls": urls,
    }
```

---

## 2. Criar `backend/app/services/use_cases/tools/urlhaus_check.py`

```python
"""URLhaus Check tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.urlhaus_client import check_urlhaus
from app.services.use_cases.tools.base import BaseToolService


class UrlhausCheckService(BaseToolService):
    tool_type = "urlhaus_check"
    cache_ttl_seconds = settings.TOOLS_CACHE_URLHAUS_CHECK
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return check_urlhaus(target)
```

---

## 3. Criar `backend/app/infra/external/phishtank_client.py`

```python
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
```

---

## 4. Criar `backend/app/services/use_cases/tools/phishtank_check.py`

```python
"""PhishTank Check tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.phishtank_client import check_phishtank
from app.services.use_cases.tools.base import BaseToolService


class PhishTankCheckService(BaseToolService):
    tool_type = "phishtank_check"
    cache_ttl_seconds = settings.TOOLS_CACHE_PHISHTANK_CHECK
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return check_phishtank(target)
```

---

## 5. Modificar `backend/app/core/config.py`

**Diff 1 — API key.** Inserir após L96 (`TOOLS_PLACEHOLDER_ORG_ID`), junto com a do GAP 1:

```python
    PHISHTANK_APP_KEY: str = ""
```

**Diff 2 — Cache TTLs.** Inserir após L110 (`TOOLS_CACHE_WEBSITE_CLONE`):

```python
    TOOLS_CACHE_URLHAUS_CHECK: int = 3600
    TOOLS_CACHE_PHISHTANK_CHECK: int = 3600
```

---

## 6. Modificar `backend/app/services/use_cases/tools/registry.py`

**Imports** — adicionar no bloco de imports (L1-17):

```python
from app.services.use_cases.tools.urlhaus_check import UrlhausCheckService
from app.services.use_cases.tools.phishtank_check import PhishTankCheckService
```

**Registro** — em `register_all_tools()`, Wave 2 (após L35, `register_tool(WebsiteCloneService())`):

```python
    register_tool(UrlhausCheckService())
    register_tool(PhishTankCheckService())
```

---

## 7. Modificar `backend/app/services/use_cases/enrich_similarity_match.py`

### 7a. Em `_run_enrichment_tools()` (L146-181)

**Imports lazy** — adicionar após L154 (`WhoisLookupService`):

```python
    from app.services.use_cases.tools.urlhaus_check import UrlhausCheckService
    from app.services.use_cases.tools.phishtank_check import PhishTankCheckService
```

**Dict services** — adicionar após L165 (`"screenshot": ScreenshotCaptureService()`):

```python
        "urlhaus": UrlhausCheckService(),
        "phishtank": PhishTankCheckService(),
```

### 7b. Nova função `_apply_threat_feed_adjustments()`

Inserir após `_apply_safe_browsing_adjustments()` (ou após `_apply_geo_adjustments()` se GAP 1 ainda não implementado):

```python
def _apply_threat_feed_adjustments(
    urlhaus_data: dict | None,
    phishtank_data: dict | None,
    score: float,
    signals: list[dict[str, object]],
) -> tuple[float, list[dict[str, object]]]:
    # URLhaus
    if urlhaus_data and urlhaus_data.get("status") == "completed":
        result = urlhaus_data.get("result") or {}
        if result.get("is_listed"):
            count = result.get("urls_count") or 0
            score += 0.20
            signals.append(_signal(
                "urlhaus_malware_listed",
                "high",
                f"Domain is listed in URLhaus with {count} associated malware URL(s).",
            ))

    # PhishTank
    if phishtank_data and phishtank_data.get("status") == "completed":
        result = phishtank_data.get("result") or {}
        if result.get("verified") and result.get("valid"):
            score += 0.28
            signals.append(_signal(
                "phishtank_verified_phish",
                "critical",
                "Domain has a verified and active phishing URL in PhishTank.",
            ))
        elif result.get("in_database"):
            score += 0.12
            signals.append(_signal(
                "phishtank_in_database",
                "high",
                "Domain appears in PhishTank database (not yet community-verified).",
            ))

    return score, signals
```

### 7c. Chamada na orquestração

Em `enrich_similarity_match()`, inserir após a chamada de `_apply_safe_browsing_adjustments` (ou após L74 `_apply_geo_adjustments`):

```python
    score, signals = _apply_threat_feed_adjustments(
        tool_results.get("urlhaus"),
        tool_results.get("phishtank"),
        score,
        signals,
    )
```

### 7d. Em `_compact_summary()` (L609-663)

Adicionar antes do `return result` final:

```python
    if tool_type == "urlhaus":
        return {
            "is_listed": result.get("is_listed"),
            "urls_count": result.get("urls_count"),
            "query_status": result.get("query_status"),
        }
    if tool_type == "phishtank":
        return {
            "in_database": result.get("in_database"),
            "verified": result.get("verified"),
            "valid": result.get("valid"),
        }
```

---

## Ajuste de Score

| Condição | Delta | Sinal | Severidade |
|---|---|---|---|
| URLhaus listado (`is_listed`) | `+0.20` | `urlhaus_malware_listed` | `high` |
| PhishTank verificado + válido | `+0.28` | `phishtank_verified_phish` | `critical` |
| PhishTank na base, não verificado | `+0.12` | `phishtank_in_database` | `high` |

**Nota:** PhishTank verificado + válido é quase equivalente a Safe Browsing hit. Ambos podem coexistir (score cumulativo).

---

## Exemplos de Retorno

```json
// URLhaus — listado:
{"query_status": "is_host", "is_listed": true, "urls_count": 3, "urls": [{"url": "http://evil.com/payload.exe", "url_status": "online"}]}

// URLhaus — limpo:
{"query_status": "no_results", "is_listed": false, "urls_count": 0, "urls": []}

// PhishTank — verificado:
{"in_database": true, "verified": true, "valid": true, "phish_id": "7654321"}

// PhishTank — limpo:
{"in_database": false, "verified": false, "valid": false, "phish_id": null}
```

---

## Configuração de Ambiente

```env
# Opcional — sem key funciona mas com rate limit agressivo
PHISHTANK_APP_KEY=sua-key-aqui
```

Registrar app key gratuita em phishtank.org. URLhaus não precisa de autenticação.

---

## Casos de Teste

1. **URLhaus listado:** Usar domínio da [URLhaus Recent Submissions](https://urlhaus.abuse.ch/browse/) marcado "online". Esperado: `urlhaus_malware_listed` nos sinais.
2. **PhishTank verificado:** URL da [PhishTank Stats](https://www.phishtank.com/stats.php). Esperado: `phishtank_verified_phish`, score `+0.28`.
3. **Domínio limpo:** `google.com`. Esperado: ambos retornam negativo, sem sinais.
4. **Regressão:** Pipeline em matches existentes → scores inalterados.
