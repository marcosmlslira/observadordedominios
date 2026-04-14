# GAP 7 — MTA-STS

**Prioridade:** Baixa | **Peso:** 55 | **Fase:** 3

---

## Contexto

**MTA-STS** permite que um domínio declare que seu servidor de e-mail suporta TLS e que remetentes devem recusar entregas inseguras. Presença ou ausência deste mecanismo enriquece o contexto de `email_security` — não como sinal de ameaça, mas como indicador da sofisticação da infraestrutura de e-mail.

Nenhum novo arquivo — extensão de `backend/app/infra/external/email_security_client.py` (207 linhas).

**Sem ajuste de score** — apenas dados adicionais para LLM assessment e analistas.

---

## 1. Modificar `backend/app/infra/external/email_security_client.py`

### 1a. Adicionar import (após L6, `import re`)

```python
import httpx
```

**Nota:** `httpx` já é dependência do projeto (`pyproject.toml` L15). Mas este arquivo atualmente só usa `dns.resolver`. Adicionar o import.

### 1b. Nova função `_check_mta_sts()` (inserir após L191, antes de `check_email_security()`)

```python
def _check_mta_sts(domain: str) -> dict:
    """Check MTA-STS policy.

    MTA-STS requer:
    1. TXT record em _mta-sts.<domain> com formato "v=STSv1; id=<policy_id>"
    2. Policy file em https://mta-sts.<domain>/.well-known/mta-sts.txt

    Returns:
        {
            "has_record": bool,
            "has_policy_file": bool,
            "mode": str | None,       # "enforce" | "testing" | "none"
            "policy_id": str | None,
        }
    """
    # 1. TXT record
    has_record = False
    policy_id = None
    txt_name = f"_mta-sts.{domain}"
    try:
        answers = dns.resolver.resolve(txt_name, "TXT", lifetime=5)
        for rdata in answers:
            for s in rdata.strings:
                decoded = s.decode("utf-8", errors="replace")
                if decoded.startswith("v=STSv1"):
                    has_record = True
                    for part in decoded.split(";"):
                        part = part.strip()
                        if part.startswith("id="):
                            policy_id = part[3:].strip()
                    break
    except Exception:
        pass

    # 2. Policy file
    has_policy_file = False
    mode = None
    policy_url = f"https://mta-sts.{domain}/.well-known/mta-sts.txt"
    try:
        resp = httpx.get(policy_url, timeout=5, follow_redirects=False)
        if resp.status_code == 200:
            has_policy_file = True
            for line in resp.text.splitlines():
                line = line.strip()
                if line.startswith("mode:"):
                    mode = line.split(":", 1)[1].strip().lower()
                    break
    except Exception:
        pass

    return {
        "has_record": has_record,
        "has_policy_file": has_policy_file,
        "mode": mode,
        "policy_id": policy_id,
    }
```

### 1c. Integrar em `check_email_security()` (L193-206)

A função atual retorna (L200-206):
```python
    return {
        "domain": domain,
        "spf": spf,
        "dmarc": dmarc,
        "dkim": dkim,
        "spoofing_risk": spoofing_risk,
    }
```

**Substituir por:**
```python
    mta_sts = _check_mta_sts(domain)

    return {
        "domain": domain,
        "spf": spf,
        "dmarc": dmarc,
        "dkim": dkim,
        "spoofing_risk": spoofing_risk,
        "mta_sts": mta_sts,
    }
```

---

## 2. Modificar `backend/app/services/use_cases/enrich_similarity_match.py`

### 2a. Em `_compact_summary()` — case `email_security` (L641)

O case atual:
```python
    if tool_type == "email_security":
        return {"spoofing_risk": result.get("spoofing_risk")}
```

**Substituir por:**
```python
    if tool_type == "email_security":
        mta_sts = result.get("mta_sts") or {}
        return {
            "spoofing_risk": result.get("spoofing_risk"),
            "mta_sts_mode": mta_sts.get("mode"),
        }
```

---

## Sem Ajuste de Score

MTA-STS sozinho não justifica ajuste — é contexto para LLM e analistas:
- Domínio suspeito com MTA-STS `enforce` = infraestrutura de e-mail profissional e deliberada
- Sem MTA-STS = configuração padrão (não incriminante)

O dado fica disponível em `enrichment_summary.tools.email_security.summary.mta_sts_mode`.

---

## Exemplos de Retorno

```json
// MTA-STS enforce:
{"has_record": true, "has_policy_file": true, "mode": "enforce", "policy_id": "20240101T120000"}

// Sem MTA-STS:
{"has_record": false, "has_policy_file": false, "mode": null, "policy_id": null}

// Record sem policy (misconfiguration):
{"has_record": true, "has_policy_file": false, "mode": null, "policy_id": "20240101T000000"}
```

---

## Casos de Teste

1. **Com MTA-STS:** `google.com` ou `microsoft.com` → `has_record: true, mode: "enforce"`.
2. **Sem MTA-STS:** Domínio sem configuração → `has_record: false, has_policy_file: false`.
3. **Timeout gracioso:** Servidor `mta-sts.<domain>` inacessível → `has_policy_file: false`, sem erro propagado.
4. **Regressão:** Campos existentes (`spoofing_risk`, `spf`, `dmarc`, `dkim`) inalterados.
