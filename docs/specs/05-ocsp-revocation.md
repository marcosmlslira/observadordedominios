# GAP 5 — OCSP / Certificate Revocation

**Prioridade:** Média | **Peso:** 70 | **Fase:** 2

---

## Contexto

**OCSP** permite verificar se um certificado SSL foi revogado. Certificado revogado = CA confirmou uso indevido — sinal forte de atividade maliciosa.

O `ssl_checker.py` atual (L1-112) captura o cert via `ssock.getpeercert()` (dict Python) que **não expõe** extensões X.509 raw como `authorityInfoAccess` (onde a URL OCSP fica). É necessário também capturar `ssock.getpeercert(binary_form=True)` e parsear com `cryptography`.

### Dependência

`cryptography` está no projeto como transitiva de `python-jose[cryptography]`, mas **não como dependência explícita**. Precisa ser adicionada.

---

## 1. Modificar `backend/pyproject.toml`

**Diff.** Adicionar após L31 (`s3fs = ">=2024.1.0"`):

```python
cryptography = ">=42.0.0"
```

Rodar `poetry lock && poetry install` após.

---

## 2. Modificar `backend/app/infra/external/ssl_checker.py`

### 2a. Adicionar imports (após L8, `from datetime import datetime, timezone`)

```python
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.x509 import ocsp as x509_ocsp
from cryptography.x509.oid import ExtensionOID

import httpx
```

E adicionar constante após L12 (`CONNECT_TIMEOUT = 10`):

```python
OCSP_TIMEOUT = 5
```

### 2b. Capturar DER cert no bloco TLS (L32-33)

O código atual (L31-33):
```python
        with socket.create_connection((domain, port), timeout=CONNECT_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
```

**Adicionar após L33:**

```python
                cert_der = ssock.getpeercert(binary_form=True)
```

### 2c. Adicionar `ocsp_status` ao dict `certificate` (após L89)

O `certificate` dict é montado em L79-89. Após L89 (`"version": cert.get("version")`), adicionar:

```python
                certificate["ocsp_status"] = _check_ocsp(cert_der) if cert_der else "unavailable"
```

### 2d. Adicionar 3 funções auxiliares no final do arquivo (após L112)

```python
def _check_ocsp(cert_der: bytes) -> str:
    """Check certificate revocation via OCSP. Returns: "good"|"revoked"|"unknown"|"unavailable"."""
    try:
        cert = x509.load_der_x509_certificate(cert_der)
    except Exception as exc:
        logger.debug("Failed to parse DER certificate: %s", exc)
        return "unavailable"

    ocsp_url = _extract_ocsp_url(cert)
    if not ocsp_url:
        return "unavailable"

    issuer_cert = _fetch_issuer_cert(cert)
    if not issuer_cert:
        return "unavailable"

    try:
        builder = x509_ocsp.OCSPRequestBuilder()
        builder = builder.add_certificate(cert, issuer_cert, hashes.SHA1())
        ocsp_request = builder.build()
        request_data = ocsp_request.public_bytes(serialization.Encoding.DER)
    except Exception as exc:
        logger.debug("Failed to build OCSP request: %s", exc)
        return "unavailable"

    try:
        resp = httpx.post(
            ocsp_url,
            content=request_data,
            headers={"Content-Type": "application/ocsp-request"},
            timeout=OCSP_TIMEOUT,
        )
        resp.raise_for_status()
        ocsp_response = x509_ocsp.load_der_ocsp_response(resp.content)
    except Exception as exc:
        logger.debug("OCSP request failed for %s: %s", ocsp_url, exc)
        return "unavailable"

    status = ocsp_response.certificate_status
    if status == x509_ocsp.OCSPCertStatus.GOOD:
        return "good"
    elif status == x509_ocsp.OCSPCertStatus.REVOKED:
        return "revoked"
    else:
        return "unknown"


def _extract_ocsp_url(cert: x509.Certificate) -> str | None:
    """Extract OCSP responder URL from authorityInfoAccess extension."""
    try:
        aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
        for access_desc in aia.value:
            if access_desc.access_method == x509.AuthorityInformationAccessOID.OCSP:
                return access_desc.access_location.value
    except x509.ExtensionNotFound:
        pass
    except Exception as exc:
        logger.debug("Failed to extract OCSP URL: %s", exc)
    return None


def _fetch_issuer_cert(cert: x509.Certificate) -> x509.Certificate | None:
    """Fetch issuer certificate via caIssuers AIA extension."""
    try:
        aia = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
        for access_desc in aia.value:
            if access_desc.access_method == x509.AuthorityInformationAccessOID.CA_ISSUERS:
                issuer_url = access_desc.access_location.value
                resp = httpx.get(issuer_url, timeout=OCSP_TIMEOUT)
                resp.raise_for_status()
                return x509.load_der_x509_certificate(resp.content)
    except x509.ExtensionNotFound:
        pass
    except Exception as exc:
        logger.debug("Failed to fetch issuer cert: %s", exc)
    return None
```

---

## 3. Modificar `backend/app/services/use_cases/enrich_similarity_match.py`

### 3a. Nova função `_apply_ssl_adjustments()`

Inserir após `_apply_geo_adjustments()` (L362, ou após as funções dos GAPs 1-2 se já implementados):

```python
def _apply_ssl_adjustments(
    tool_data: dict | None,
    score: float,
    signals: list[dict[str, object]],
) -> tuple[float, list[dict[str, object]]]:
    if not tool_data or tool_data.get("status") != "completed":
        return score, signals
    result = tool_data.get("result") or {}
    cert = result.get("certificate") or {}
    ocsp_status = cert.get("ocsp_status")

    if ocsp_status == "revoked":
        score += 0.25
        signals.append(_signal(
            "certificate_revoked",
            "critical",
            "SSL certificate has been revoked by the issuing CA.",
        ))

    return score, signals
```

### 3b. Chamada na orquestração

Em `enrich_similarity_match()`, inserir após a chamada de `_apply_geo_adjustments` (ou após GAPs 1-2):

```python
    score, signals = _apply_ssl_adjustments(tool_results.get("ssl_check"), score, signals)
```

### 3c. Em `_compact_summary()` — case `ssl_check` (L642-650)

O case atual:
```python
    if tool_type == "ssl_check":
        cert = result.get("certificate") or {}
        return {
            "is_valid": result.get("is_valid"),
            "issuer": cert.get("issuer"),
            "days_remaining": cert.get("days_remaining"),
            "san_count": len(cert.get("san") or []),
        }
```

**Substituir por:**
```python
    if tool_type == "ssl_check":
        cert = result.get("certificate") or {}
        return {
            "is_valid": result.get("is_valid"),
            "issuer": cert.get("issuer"),
            "days_remaining": cert.get("days_remaining"),
            "san_count": len(cert.get("san") or []),
            "ocsp_status": cert.get("ocsp_status"),
        }
```

---

## Ajuste de Score

| Condição | Delta | Sinal | Severidade |
|---|---|---|---|
| `ocsp_status == "revoked"` | `+0.25` | `certificate_revoked` | `critical` |
| `"unavailable"` / `"good"` / `"unknown"` | `0` | nenhum | — |

---

## Tratamento de Falhas

OCSP pode falhar sem relação com ameaça: responder offline, self-signed sem AIA, timeout. **Todos retornam `"unavailable"` sem alterar score.** Função é best-effort.

---

## Exemplo de Retorno Atualizado do `check_ssl()`

```json
{
  "is_valid": true,
  "certificate": {
    "subject": "example.com",
    "issuer": "Let's Encrypt",
    "days_remaining": 45,
    "san": ["example.com", "www.example.com"],
    "ocsp_status": "good"
  },
  "chain_length": 2,
  "protocol_version": "TLSv1.3",
  "cipher_suite": "TLS_AES_256_GCM_SHA384",
  "issues": []
}
```

---

## Casos de Teste

1. **Cert ativo:** `google.com` → `ocsp_status: "good"`.
2. **Cert revogado:** `revoked.badssl.com` → `ocsp_status: "revoked"`, sinal `certificate_revoked`.
3. **Self-signed (sem AIA):** → `ocsp_status: "unavailable"`, sem erro, sem delta.
4. **Regressão:** Campos existentes (`is_valid`, `issuer`, `days_remaining`, `san`) inalterados.
