# Specs de Adequação do Sistema de Risco — Visão Geral

> Especificações técnicas para fechar os 7 gaps entre `docs/estudo-monitoramento.md` e o sistema atual.
> Cada spec é **auto-contida** — pode ser implementada por um agent sem ler as outras.

---

## Contexto

O estudo de monitoramento define 5 camadas: descoberta → enriquecimento → confirmação de clonagem → scoring → resposta.

O pipeline atual cobre: WHOIS, DNS, HTTP, SSL, Blacklist (DNSBL), Email Security (SPF/DMARC/DKIM), Geo, Page Analysis, Clone Detection. Faltam os 7 gaps abaixo.

---

## Mapa de Cobertura por Prioridade

| # | Gap | Spec | Peso | Fase | Tipo |
|---|-----|------|------|------|------|
| 1 | Google Safe Browsing API | `01-safe-browsing.md` | 80 | 1 — Alta | Nova tool + pipeline |
| 2 | URLhaus + PhishTank | `02-urlhaus-phishtank.md` | 80 | 1 — Alta | 2 novas tools + pipeline |
| 3 | Dangling DNS / Subdomain Takeover | `03-subdomain-takeover.md` | 75 | 1 — Alta | Nova tool manual + migration |
| 4 | CAA Record Analysis | `04-caa-records.md` | 70 | 2 — Média | Extensão de 2 linhas |
| 5 | OCSP / Certificate Revocation | `05-ocsp-revocation.md` | 70 | 2 — Média | Extensão + nova dep |
| 6 | Padrões de Phishing Kit / PhaaS | `06-phaas-patterns.md` | 60 | 3 — Baixa | Extensão |
| 7 | MTA-STS | `07-mta-sts.md` | 55 | 3 — Baixa | Extensão |

---

## Dependências Python (verificadas em `backend/pyproject.toml`)

| Pacote | Status | Quem precisa |
|---|---|---|
| `httpx` `^0.27.0` | Já instalado | GAP 1, 2, 3, 5 (todos os novos clients HTTP) |
| `dnspython` `^2.7.0` | Já instalado | GAP 3 (CNAME resolver), GAP 4 (CAA), GAP 7 (MTA-STS TXT) |
| `cryptography` | **NÃO explícita** — puxada via `python-jose[cryptography]` como transitiva. **Adicionar como dependência explícita `cryptography>=42.0.0`** para GAP 5 (OCSP). |

---

## Dois Caminhos de Integração

### Caminho A — Tool manual via API `/v1/tools/*`

```
registry.py → register_tool(ServiceInstance())
  → API route auto-registra endpoint GET/POST /v1/tools/{tool_type}
  → BaseToolService.run() gerencia cache, rate limit, execução
  → _execute(target) → infra/external/client.py
```

- **Contrato:** `_execute(target: str) -> dict` — retorna dict serializável para JSONB
- **Base class:** `backend/app/services/use_cases/tools/base.py` (L26-148)
- **Registro:** `backend/app/services/use_cases/tools/registry.py` (L20-35)

### Caminho B — Pipeline automático (similarity enrichment)

```
enrich_similarity_match.py:
  _run_enrichment_tools() (L146-181) → instancia tools diretamente
  _apply_*_adjustments()            → ajusta score + append signals
  _compact_summary() (L609-663)     → resume resultado para enrichment_summary
  enrich_similarity_match() (L46-143) → orquestra tudo
```

- **IMPORTANTE:** Tools no pipeline são instanciadas **diretamente** em `_run_enrichment_tools()`, NÃO via registry. Precisa adicionar em **ambos** os locais.
- **Padrão de guard:** `if not tool_data or tool_data.get("status") != "completed": return score, signals`
- **Helper de sinal:** `_signal(code, severity, description)` (L690-691)

### Qual caminho para cada gap

| Gap | Caminho A (tool manual) | Caminho B (pipeline) | Motivo |
|---|---|---|---|
| 1 — Safe Browsing | Sim | Sim | Sinal de reputação para suspeitos |
| 2 — URLhaus/PhishTank | Sim | Sim | Sinal de reputação para suspeitos |
| 3 — Subdomain Takeover | Sim | **NÃO** | Opera sobre ativos da marca, não suspeitos |
| 4 — CAA | Extensão (já existe) | Extensão do `_compact_summary` | Apenas novo campo no summary |
| 5 — OCSP | Extensão (já existe) | Sim (nova `_apply_ssl_adjustments`) | Sinal de certificado para suspeitos |
| 6 — PhaaS Patterns | Extensão (já existe) | Extensão do `_apply_page_adjustments` | Nova categoria de sinal |
| 7 — MTA-STS | Extensão (já existe) | Extensão do `_compact_summary` | Apenas contexto (sem score delta) |

---

## Padrão de Implementação (referência para todas as specs)

### 1. Infra client (`backend/app/infra/external/<name>_client.py`)

Função pura que faz a chamada externa e retorna dict. Sem DB, sem cache, sem estado.
Referência: `backend/app/infra/external/dnsbl_client.py` — `check_blacklists(domain: str) -> dict`

### 2. Service (`backend/app/services/use_cases/tools/<name>.py`)

```python
"""<Name> Check tool service."""
from __future__ import annotations
from app.core.config import settings
from app.infra.external.<name>_client import check_<name>
from app.services.use_cases.tools.base import BaseToolService

class <Name>CheckService(BaseToolService):
    tool_type = "<name>_check"
    cache_ttl_seconds = settings.TOOLS_CACHE_<NAME>_CHECK
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return check_<name>(target)
```

Referência real: `backend/app/services/use_cases/tools/blacklist_check.py` (17 linhas, exatamente esse padrão)

### 3. Config (`backend/app/core/config.py`)

Adicionar na seção `# Cache TTLs (seconds)` — linhas 98-110:
```python
TOOLS_CACHE_<NAME>_CHECK: int = <TTL>
```
E chaves de API (se houver) na seção `# ── Free Tools`:
```python
<API_KEY_NAME>: str = ""
```

### 4. Registry (`backend/app/services/use_cases/tools/registry.py`)

Adicionar import no topo (L1-17) e chamada em `register_all_tools()` (L20-35).
Wave 1 = essenciais (L23-28), Wave 2 = enrichment (L29-35). Novas tools vão em Wave 2.

### 5. Pipeline — `_run_enrichment_tools()` (L146-181 de `enrich_similarity_match.py`)

Import lazy dentro da função (padrão existente, L147-154) e adicionar ao dict `services` (L156-165).

### 6. Pipeline — `_apply_*_adjustments()` (nova função)

Padrão guard:
```python
def _apply_<name>_adjustments(tool_data, score, signals):
    if not tool_data or tool_data.get("status") != "completed":
        return score, signals
    result = tool_data.get("result") or {}
    # lógica de score
    return score, signals
```

Chamar em `enrich_similarity_match()` — após L74 (`_apply_geo_adjustments`) e antes de L76 (`_derive_ownership`).

### 7. Pipeline — `_compact_summary()` (L609-663)

Adicionar `if tool_type == "<name>":` case com os campos relevantes.

---

## Diagrama de Dependências de Implementação

```
Fase 1 (alta prioridade)
├── GAP 1: safe_browsing_client.py ──→ safe_browsing_check.py ──→ registry.py
│                                                               └──→ _run_enrichment_tools()
│                                                                    _apply_safe_browsing_adjustments()
├── GAP 2: urlhaus_client.py ────────→ urlhaus_check.py ────────→ registry.py
│          phishtank_client.py ───────→ phishtank_check.py ─────→ _run_enrichment_tools()
│                                                                    _apply_threat_feed_adjustments()
└── GAP 3: subdomain_takeover_client.py → subdomain_takeover_check.py → registry.py
                                                              ├──→ monitored_brand_domain.py (campo)
                                                              └──→ 023_brand_domain_takeover_status.py

Fase 2 (média prioridade)
├── GAP 4: dns_resolver.py (+ "CAA") → sem novas tools
└── GAP 5: ssl_checker.py (+ OCSP) → _apply_ssl_adjustments() em enrich_similarity_match.py

Fase 3 (baixa prioridade)
├── GAP 6: suspicious_page.py (+ PhaaS patterns)
└── GAP 7: email_security_client.py (+ MTA-STS)
```

---

## Arquivos Críticos a Modificar

| Arquivo | Linhas-chave | Gaps | O que muda |
|---|---|---|---|
| `backend/pyproject.toml` | L31 | 5 | Adicionar `cryptography>=42.0.0` |
| `backend/app/core/config.py` | L96, L110 | 1,2,3 | API keys + cache TTLs |
| `backend/app/infra/external/dns_resolver.py` | L14 | 4 | `"CAA"` em `DEFAULT_RECORD_TYPES` |
| `backend/app/infra/external/ssl_checker.py` | L8, L33, L89, L112+ | 5 | Imports cryptography + OCSP |
| `backend/app/infra/external/email_security_client.py` | L6, L191, L200-206 | 7 | Import httpx + `_check_mta_sts()` + return |
| `backend/app/services/use_cases/tools/registry.py` | L1-17, L20-35 | 1,2,3 | 4 novos imports + 4 register_tool() |
| `backend/app/services/use_cases/tools/suspicious_page.py` | L66, L88, L196, L231 | 6 | PhaaS patterns + detecção + campo |
| `backend/app/services/use_cases/enrich_similarity_match.py` | L146-165, L260-302, L362, L609-663 | 1,2,4,5,6 | Services dict + 3 _apply_* + compact_summary |
| `backend/app/models/monitored_brand_domain.py` | L29 | 3 | Coluna `takeover_status` |

## Novos Arquivos a Criar (9)

| Arquivo | Gap | Linhas (~) |
|---|---|---|
| `backend/app/infra/external/safe_browsing_client.py` | 1 | ~65 |
| `backend/app/services/use_cases/tools/safe_browsing_check.py` | 1 | ~17 |
| `backend/app/infra/external/urlhaus_client.py` | 2 | ~40 |
| `backend/app/services/use_cases/tools/urlhaus_check.py` | 2 | ~17 |
| `backend/app/infra/external/phishtank_client.py` | 2 | ~50 |
| `backend/app/services/use_cases/tools/phishtank_check.py` | 2 | ~17 |
| `backend/app/infra/external/subdomain_takeover_client.py` | 3 | ~90 |
| `backend/app/services/use_cases/tools/subdomain_takeover_check.py` | 3 | ~17 |
| `backend/alembic/versions/023_brand_domain_takeover_status.py` | 3 | ~25 |

## Ordem Segura de Implementação

Cada GAP é independente dos demais, MAS todos os GAPs 1/2/5 tocam `enrich_similarity_match.py`. Ordem recomendada para evitar conflitos de merge:

```
1. GAP 4 (CAA)      — 2 linhas, sem conflito possível
2. GAP 7 (MTA-STS)  — isolado em email_security_client.py
3. GAP 6 (PhaaS)    — isolado em suspicious_page.py  
4. GAP 3 (Takeover) — novos arquivos + migration, sem tocar enrichment
5. GAP 1 (Safe Browsing) — toca enrichment, fazer primeiro dos "pipeline"
6. GAP 2 (URLhaus+PhishTank) — toca enrichment, fazer segundo
7. GAP 5 (OCSP)     — toca ssl_checker.py + enrichment, requer poetry install
```
