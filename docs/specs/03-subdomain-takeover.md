# GAP 3 — Dangling DNS / Subdomain Takeover

**Prioridade:** Alta | **Peso:** 75 | **Fase:** 1

---

## Contexto

Subdomain takeover: subdomínio da marca (ex: `blog.acme.com`) tem CNAME para serviço externo desprovisionado (ex: `old-blog.herokuapp.com`). Atacante registra o serviço e serve conteúdo sob o subdomínio legítimo.

**Diferente dos GAPs 1-2:** Esta tool opera sobre **ativos oficiais da marca** (`MonitoredBrandDomain`), não sobre domínios suspeitos. Por isso **NÃO entra no pipeline de enriquecimento** — é tool de uso manual ou scan periódico.

---

## 1. Criar `backend/app/infra/external/subdomain_takeover_client.py`

```python
"""Dangling DNS / subdomain takeover detector."""

from __future__ import annotations

import logging

import dns.resolver
import httpx

logger = logging.getLogger(__name__)

# Fingerprints: (service_name, substring no body HTTP)
# Fonte: https://github.com/EdOverflow/can-i-take-over-xyz
TAKEOVER_FINGERPRINTS: list[tuple[str, str]] = [
    ("GitHub Pages", "There isn't a GitHub Pages site here"),
    ("GitHub Pages", "For root URLs (like http://example.com/) you must provide an index.html file"),
    ("Amazon S3", "NoSuchBucket"),
    ("Amazon S3", "The specified bucket does not exist"),
    ("Heroku", "No such app"),
    ("Heroku", "herokucdn.com/error-pages/no-such-app"),
    ("Fastly", "Fastly error: unknown domain"),
    ("Shopify", "Sorry, this shop is currently unavailable"),
    ("Shopify", "Only one step away from your own online store"),
    ("Zendesk", "Help Center Closed"),
    ("Surge.sh", "project not found"),
    ("Tumblr", "Whatever you were looking for doesn't currently exist at this address"),
    ("Ghost", "The thing you were looking for is no longer here"),
    ("Bitbucket", "Repository not found"),
]

CONNECT_TIMEOUT = 8
READ_TIMEOUT = 8


def check_takeover(domain: str) -> dict:
    """Check if a domain/subdomain is vulnerable to takeover via dangling CNAME.

    Resolve CNAME chain e verifica HTTP response contra fingerprints de serviços desprovisionados.

    Returns:
        {
            "is_vulnerable": bool,
            "cname_chain": list[str],
            "vulnerable_cname": str | None,
            "fingerprint_matched": str | None,
            "service": str | None,
            "checked_url": str | None,
        }
    """
    cname_chain = _resolve_cname_chain(domain)

    if not cname_chain:
        return {
            "is_vulnerable": False,
            "cname_chain": [],
            "vulnerable_cname": None,
            "fingerprint_matched": None,
            "service": None,
            "checked_url": None,
        }

    final_cname = cname_chain[-1]
    checked_url = f"http://{domain}"

    try:
        resp = httpx.get(
            checked_url,
            follow_redirects=True,
            timeout=httpx.Timeout(CONNECT_TIMEOUT, read=READ_TIMEOUT),
            headers={"User-Agent": "ObservadorDominios/1.0 security-scanner"},
        )
        body = resp.text
    except (httpx.ConnectError, httpx.TimeoutException):
        body = ""
    except Exception as exc:
        logger.debug("HTTP check failed for %s: %s", domain, exc)
        return {
            "is_vulnerable": False,
            "cname_chain": cname_chain,
            "vulnerable_cname": final_cname,
            "fingerprint_matched": None,
            "service": None,
            "checked_url": checked_url,
            "error": str(exc),
        }

    for service_name, fingerprint in TAKEOVER_FINGERPRINTS:
        if fingerprint.lower() in body.lower():
            logger.info("Subdomain takeover detected: %s -> %s (%s)", domain, final_cname, service_name)
            return {
                "is_vulnerable": True,
                "cname_chain": cname_chain,
                "vulnerable_cname": final_cname,
                "fingerprint_matched": fingerprint,
                "service": service_name,
                "checked_url": checked_url,
            }

    return {
        "is_vulnerable": False,
        "cname_chain": cname_chain,
        "vulnerable_cname": final_cname,
        "fingerprint_matched": None,
        "service": None,
        "checked_url": checked_url,
    }


def _resolve_cname_chain(domain: str, max_depth: int = 10) -> list[str]:
    """Follow CNAME chain. Returns list of CNAME targets (empty if no CNAMEs)."""
    chain: list[str] = []
    current = domain

    for _ in range(max_depth):
        try:
            answers = dns.resolver.resolve(current, "CNAME")
            target = answers[0].to_text().rstrip(".")
            chain.append(target)
            current = target
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN, dns.resolver.NoNameservers):
            break
        except Exception as exc:
            logger.debug("CNAME resolution error for %s: %s", current, exc)
            break

    return chain
```

---

## 2. Criar `backend/app/services/use_cases/tools/subdomain_takeover_check.py`

```python
"""Subdomain Takeover Check tool service."""

from __future__ import annotations

from app.core.config import settings
from app.infra.external.subdomain_takeover_client import check_takeover
from app.services.use_cases.tools.base import BaseToolService


class SubdomainTakeoverCheckService(BaseToolService):
    tool_type = "subdomain_takeover_check"
    cache_ttl_seconds = settings.TOOLS_CACHE_SUBDOMAIN_TAKEOVER
    timeout_seconds = settings.TOOLS_DEFAULT_TIMEOUT_SECONDS

    def _execute(self, target: str) -> dict:
        return check_takeover(target)
```

---

## 3. Criar migration `backend/alembic/versions/023_brand_domain_takeover_status.py`

```python
"""Add takeover_status to monitored_brand_domain.

Revision ID: 023_brand_domain_takeover_status
Revises: 022_complete_tld_lists
Create Date: 2026-04-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "023_brand_domain_takeover_status"
down_revision = "022_complete_tld_lists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monitored_brand_domain",
        sa.Column("takeover_status", sa.String(16), nullable=True),
    )
    # Valores: 'safe', 'vulnerable', 'unknown', NULL (não verificado)


def downgrade() -> None:
    op.drop_column("monitored_brand_domain", "takeover_status")
```

---

## 4. Modificar `backend/app/core/config.py`

Inserir após L110 (`TOOLS_CACHE_WEBSITE_CLONE`):

```python
    TOOLS_CACHE_SUBDOMAIN_TAKEOVER: int = 21600  # 6 horas
```

---

## 5. Modificar `backend/app/services/use_cases/tools/registry.py`

**Import** — adicionar no bloco de imports:

```python
from app.services.use_cases.tools.subdomain_takeover_check import SubdomainTakeoverCheckService
```

**Registro** — Wave 2 (após L35):

```python
    register_tool(SubdomainTakeoverCheckService())
```

---

## 6. Modificar `backend/app/models/monitored_brand_domain.py`

**Diff exato.** Inserir após L29 (`updated_at = Column(...)`) e antes de L31 (`brand = relationship(...)`):

```python
    takeover_status = Column(String(16), nullable=True)
```

O model atual tem estas colunas (L15-29):
```
id, brand_id, domain_name, registrable_domain, registrable_label,
public_suffix, hostname_stem, is_primary, is_active, created_at, updated_at
```

---

## NÃO Integrar no Pipeline de Enriquecimento

Esta tool **NÃO** entra em `_run_enrichment_tools()` porque:
- O pipeline de enriquecimento analisa **domínios suspeitos de terceiros**
- Subdomain takeover verifica vulnerabilidades nos **próprios domínios da marca**
- São direções opostas: um verifica "esse domínio suspeito é perigoso?", o outro "meu domínio oficial está vulnerável?"

### Uso recomendado

```
POST /v1/tools/subdomain_takeover_check
{"target": "blog.acme.com.br"}
```

Futuro: worker periódico que itera `MonitoredBrandDomain WHERE is_active=True` e atualiza `takeover_status`.

---

## Exemplos de Retorno

```json
// Vulnerável:
{
  "is_vulnerable": true,
  "cname_chain": ["old-blog.acmecorp.github.io"],
  "vulnerable_cname": "old-blog.acmecorp.github.io",
  "fingerprint_matched": "There isn't a GitHub Pages site here",
  "service": "GitHub Pages",
  "checked_url": "http://blog.acme.com"
}

// Seguro:
{
  "is_vulnerable": false,
  "cname_chain": ["acme.github.io"],
  "vulnerable_cname": "acme.github.io",
  "fingerprint_matched": null,
  "service": null,
  "checked_url": "http://blog.acme.com"
}

// Sem CNAME (A record direto):
{
  "is_vulnerable": false,
  "cname_chain": [],
  "vulnerable_cname": null,
  "fingerprint_matched": null,
  "service": null,
  "checked_url": null
}
```

---

## Casos de Teste

1. **GitHub Pages dangling:** CNAME para `nonexistent-org.github.io` → `is_vulnerable: true, service: "GitHub Pages"`.
2. **S3 inexistente:** CNAME para `nonexistent-bucket.s3.amazonaws.com` → `fingerprint_matched: "NoSuchBucket"`.
3. **Sem CNAME:** Domínio com A record direto → `cname_chain: [], is_vulnerable: false`.
4. **Serviço ativo:** CNAME funcional → `is_vulnerable: false`.
5. **Migration:** `alembic upgrade head` → coluna `takeover_status` existe e aceita `'safe'/'vulnerable'/'unknown'/NULL`.
