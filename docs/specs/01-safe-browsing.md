# GAP 1 — Google Safe Browsing API

**Prioridade:** Alta | **Peso:** 80 | **Fase:** 1

---

## Contexto

Google Safe Browsing mantém listas de URLs/domínios associados a malware, phishing, software indesejado. Domínios listados recebem avisos no Chrome/Firefox/Safari — sinal forte de atividade maliciosa confirmada por terceiro de alta reputação.

O sistema atual **não consulta** este serviço. Este gap adiciona:
- Tool manual via `/v1/tools/safe_browsing_check`
- Integração no pipeline de enriquecimento automático

---

## 1. Criar `backend/app/infra/external/safe_browsing_client.py`

```python
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
```

---

## 2. Criar `backend/app/services/use_cases/tools/safe_browsing_check.py`

```python
"""Safe Browsing Check tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.safe_browsing_client import check_safe_browsing
from app.services.use_cases.tools.base import BaseToolService


class SafeBrowsingCheckService(BaseToolService):
    tool_type = "safe_browsing_check"
    cache_ttl_seconds = settings.TOOLS_CACHE_SAFE_BROWSING_CHECK
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return check_safe_browsing(target)
```

---

## 3. Modificar `backend/app/core/config.py`

**Diff 1 — Adicionar API key.** Inserir após L96 (`TOOLS_PLACEHOLDER_ORG_ID`):

```python
    GOOGLE_SAFE_BROWSING_API_KEY: str = ""
```

**Diff 2 — Adicionar cache TTL.** Inserir após L110 (`TOOLS_CACHE_WEBSITE_CLONE`):

```python
    TOOLS_CACHE_SAFE_BROWSING_CHECK: int = 3600
```

---

## 4. Modificar `backend/app/services/use_cases/tools/registry.py`

**Diff 1 — Import.** Adicionar após L16 (`from ...website_clone import WebsiteCloneService`):

```python
from app.services.use_cases.tools.safe_browsing_check import SafeBrowsingCheckService
```

**Diff 2 — Registro.** Adicionar após L28 (`register_tool(SuspiciousPageService())`), em Wave 1:

```python
    register_tool(SafeBrowsingCheckService())
```

---

## 5. Modificar `backend/app/services/use_cases/enrich_similarity_match.py`

### 5a. Em `_run_enrichment_tools()` (L146-181)

**Diff — Import + dict entry.** Adicionar import no bloco de imports lazy (após L154, `from ...whois_lookup import WhoisLookupService`):

```python
    from app.services.use_cases.tools.safe_browsing_check import SafeBrowsingCheckService
```

Adicionar ao dict `services` (após L165, `"screenshot": ScreenshotCaptureService()`):

```python
        "safe_browsing": SafeBrowsingCheckService(),
```

### 5b. Nova função `_apply_safe_browsing_adjustments()`

Inserir após `_apply_geo_adjustments()` (após L362):

```python
def _apply_safe_browsing_adjustments(
    tool_data: dict | None,
    score: float,
    signals: list[dict[str, object]],
) -> tuple[float, list[dict[str, object]]]:
    if not tool_data or tool_data.get("status") != "completed":
        return score, signals
    result = tool_data.get("result") or {}
    if result.get("skipped"):
        return score, signals
    if result.get("is_listed"):
        score += 0.30
        threat_types = result.get("threat_types") or []
        description = (
            f"Domain is listed in Google Safe Browsing ({', '.join(threat_types)})."
            if threat_types
            else "Domain is listed in Google Safe Browsing."
        )
        signals.append(_signal("safe_browsing_hit", "critical", description))
    return score, signals
```

### 5c. Chamada na orquestração

Em `enrich_similarity_match()`, inserir **após L74** (`_apply_geo_adjustments`), **antes de L76** (`_derive_ownership`):

```python
    score, signals = _apply_safe_browsing_adjustments(tool_results.get("safe_browsing"), score, signals)
```

### 5d. Em `_compact_summary()` (L609-663)

Adicionar **antes do `return result` final** (L663):

```python
    if tool_type == "safe_browsing":
        return {
            "is_listed": result.get("is_listed"),
            "threat_types": result.get("threat_types") or [],
            "skipped": result.get("skipped", False),
        }
```

---

## Ajuste de Score

| Condição | Delta | Sinal | Severidade |
|---|---|---|---|
| `is_listed == true` | `+0.30` | `safe_browsing_hit` | `critical` |
| `skipped` ou erro | `0` | nenhum | — |

---

## Exemplos de Retorno

```json
// Listado:
{"is_listed": true, "threat_types": ["MALWARE", "SOCIAL_ENGINEERING"], "skipped": false}

// Limpo:
{"is_listed": false, "threat_types": [], "skipped": false}

// Sem API key:
{"is_listed": false, "threat_types": [], "skipped": true}
```

---

## Configuração de Ambiente

```env
# .env ou Docker secret
GOOGLE_SAFE_BROWSING_API_KEY=sua-chave-aqui
```

Obter em: Google Cloud Console → APIs & Services → Credentials → API Key, com "Safe Browsing API" habilitada.

**Sem chave:** Funciona sem erro — retorna `skipped: true`, score inalterado.

---

## Casos de Teste

1. **Domínio listado:** `testsafebrowsing.appspot.com/s/phishing.html` (URL oficial de teste Google). Esperado: `safe_browsing_hit` nos sinais.
2. **Sem chave:** Remover env var. Esperado: `skipped: true`, sem erro, sem sinal.
3. **Domínio limpo:** `google.com`. Esperado: `is_listed: false`.
4. **Regressão:** Pipeline em matches existentes → scores sem listagem inalterados.

---

## Referências

- [Safe Browsing Lookup API v4](https://developers.google.com/safe-browsing/v4/lookup-api)
- URL de teste oficial: `https://testsafebrowsing.appspot.com/`
