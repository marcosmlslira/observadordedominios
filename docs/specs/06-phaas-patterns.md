# GAP 6 — Padrões de Phishing Kit / PhaaS

**Prioridade:** Baixa | **Peso:** 60 | **Fase:** 3

---

## Contexto

**PhaaS** kits (EvilProxy, Evilginx, Darcula) usam paths e strings JavaScript padronizados. O `suspicious_page.py` já detecta `has_login_form`, `has_credential_inputs` e categorias como `brand_impersonation`. Esta spec adiciona detecção de **infraestrutura PhaaS** — paths e scripts característicos, não o conteúdo.

Nenhum novo arquivo — extensão de `backend/app/services/use_cases/tools/suspicious_page.py` (274 linhas).

---

## 1. Modificar `backend/app/services/use_cases/tools/suspicious_page.py`

### 1a. Adicionar constantes (após L66, `CHALLENGE_PATTERNS = (...)`)

```python
# PhaaS / phishing kit infrastructure patterns
PHAAS_PATH_PATTERNS: tuple[str, ...] = (
    "/__utm.gif",
    "/__open.gif",
    "/track/open",
    "/track/click",
    "/panel/login",
    "/admin/login.php",
    "/admin/index.php",
    "/cp/login",
    "/api/collect",
    "/api/submit",
    "/api/capture",
    "/submit.php",
    "/gate.php",
)

PHAAS_BODY_PATTERNS: tuple[str, ...] = (
    "evilginx",
    "modlishka",
    "robin banks",
    "darcula",
    "collectdata(",
    "sendtogate(",
    "exfil(",
)
```

### 1b. Adicionar import (L7, após `import re`)

```python
from urllib.parse import urlparse
```

**Nota:** `urlparse` já pode estar no arquivo via outro import. Verificar antes de adicionar.

### 1c. Adicionar detecção no `_execute()` — após bloco de brand impersonation (L186-196), antes de external resources (L199)

Inserir o seguinte bloco:

```python
        # Check PhaaS / phishing kit patterns
        has_phishing_kit_indicators = False
        try:
            url_path = urlparse(final_url).path.lower()
        except Exception:
            url_path = ""

        for pattern in PHAAS_PATH_PATTERNS:
            if pattern in url_path:
                has_phishing_kit_indicators = True
                signals.append({
                    "category": "phishing_kit_infrastructure",
                    "description": f"URL path matches PhaaS pattern: {pattern}",
                    "severity": "high",
                })
                break

        if not has_phishing_kit_indicators:
            for pattern in PHAAS_BODY_PATTERNS:
                if pattern in text_content:
                    has_phishing_kit_indicators = True
                    signals.append({
                        "category": "phishing_kit_infrastructure",
                        "description": f"Page content matches PhaaS pattern: {pattern}",
                        "severity": "high",
                    })
                    break
```

### 1d. Adicionar campo ao return dict (L231-244)

O return dict atual (L231-244) contém `"has_credential_inputs": has_credential_inputs`. Adicionar após esse campo:

```python
            "has_phishing_kit_indicators": has_phishing_kit_indicators,
```

### 1e. Inicializar no early return (L79-92)

No return de `page is None` (L79-92), adicionar o campo:

```python
                "has_phishing_kit_indicators": False,
```

Inserir após L88 (`"has_credential_inputs": False,`).

---

## 2. Modificar `backend/app/services/use_cases/enrich_similarity_match.py`

### 2a. Em `_apply_page_adjustments()` (L260-302)

O bloco de categorias começa em L291. Após L300 (`"shielded_infrastructure"...`), adicionar:

```python
    if "phishing_kit_infrastructure" in categories:
        score += 0.15
        signals.append(_signal(
            "phishing_kit_indicator",
            "high",
            "Page exhibits patterns consistent with PhaaS/phishing kit infrastructure.",
        ))
```

### 2b. Em `_compact_summary()` — case `suspicious_page` (L633-640)

O case atual:
```python
    if tool_type == "suspicious_page":
        return {
            "risk_level": result.get("risk_level"),
            "page_disposition": result.get("page_disposition"),
            "has_login_form": result.get("has_login_form"),
            "has_credential_inputs": result.get("has_credential_inputs"),
            "data_quality": result.get("data_quality"),
        }
```

**Substituir por:**
```python
    if tool_type == "suspicious_page":
        return {
            "risk_level": result.get("risk_level"),
            "page_disposition": result.get("page_disposition"),
            "has_login_form": result.get("has_login_form"),
            "has_credential_inputs": result.get("has_credential_inputs"),
            "has_phishing_kit_indicators": result.get("has_phishing_kit_indicators", False),
            "data_quality": result.get("data_quality"),
        }
```

---

## Ajuste de Score

| Condição | Delta | Sinal | Severidade |
|---|---|---|---|
| Path ou body match PhaaS | `+0.15` | `phishing_kit_indicator` | `high` |

**Aditivo com outros sinais:** `credential_collection_surface` (+0.26) e `phishing_kit_indicator` (+0.15) podem disparar juntos no mesmo domínio. Score acumula.

---

## Decisões de Design

- **Só 1 match por tipo (path OU body):** Break após primeiro match para evitar inflar o score com múltiplos patterns do mesmo kit.
- **`text_content` já está lowercase** (L96) — patterns em `PHAAS_BODY_PATTERNS` devem estar lowercase.
- **False positives possíveis:** Sites legítimos com `/api/submit` existem. A combinação com outros sinais (login form, brand impersonation) reduz o impacto.

---

## Casos de Teste

1. **Path PhaaS:** Página com `final_url` contendo `/api/collect` → `has_phishing_kit_indicators: true`.
2. **Body PhaaS:** Página com `"collectdata("` no JS → sinal `phishing_kit_infrastructure`.
3. **Página limpa:** Homepage legítima → `has_phishing_kit_indicators: false`.
4. **Regressão:** Resultados existentes de `suspicious_page` em cache não afetados.
