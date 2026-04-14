# GAP 4 — CAA Record Analysis

**Prioridade:** Média | **Peso:** 70 | **Fase:** 2

---

## Contexto

**CAA (Certification Authority Authorization)** records restringem quais CAs podem emitir certificados para um domínio. Domínios legítimos bem configurados tipicamente têm CAA. A maioria dos domínios de phishing descartáveis não.

Este gap é a **menor mudança de todos** — apenas adicionar `"CAA"` à lista de record types no DNS resolver e expor `has_caa` no compact summary. Sem nova tool, sem novo arquivo, sem ajuste de score.

---

## 1. Modificar `backend/app/infra/external/dns_resolver.py`

**Diff exato (L14):**

```diff
- DEFAULT_RECORD_TYPES = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]
+ DEFAULT_RECORD_TYPES = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA", "CAA"]
```

Nenhuma outra mudança necessária — `resolve_domain()` (L17-62) já itera sobre todos os tipos e captura `NoAnswer` silenciosamente. Registros CAA são retornados no mesmo formato:

```python
{"type": "CAA", "name": "example.com", "value": '0 issue "letsencrypt.org"', "ttl": 3600}
```

---

## 2. Modificar `backend/app/services/use_cases/enrich_similarity_match.py`

**Diff exato em `_compact_summary()` (L619-626).** O case `dns_lookup` atual:

```python
    if tool_type == "dns_lookup":
        records = result.get("records") or []
        types_found = sorted({str(r.get("type")) for r in records})
        return {
            "record_types": types_found,
            "has_mx": "MX" in types_found,
            "has_a": "A" in types_found or "AAAA" in types_found,
            "nameservers": result.get("nameservers") or [],
        }
```

**Substituir por:**

```python
    if tool_type == "dns_lookup":
        records = result.get("records") or []
        types_found = sorted({str(r.get("type")) for r in records})
        return {
            "record_types": types_found,
            "has_mx": "MX" in types_found,
            "has_a": "A" in types_found or "AAAA" in types_found,
            "has_caa": "CAA" in types_found,
            "nameservers": result.get("nameservers") or [],
        }
```

---

## Sem Ajuste de Score

A ausência de CAA **não é penalizada** — a maioria dos domínios legítimos também não tem CAA. O dado fica disponível:
- No `enrichment_summary.tools.dns_lookup.summary.has_caa` para a LLM assessment
- No frontend para analistas

---

## Resultado no Enrichment Summary

```json
{
  "tools": {
    "dns_lookup": {
      "status": "completed",
      "summary": {
        "record_types": ["A", "CAA", "MX", "NS", "SOA", "TXT"],
        "has_mx": true,
        "has_a": true,
        "has_caa": true,
        "nameservers": ["ns1.cloudflare.com", "ns2.cloudflare.com"]
      }
    }
  }
}
```

---

## Casos de Teste

1. **Domínio com CAA:** `cloudflare.com` → `"CAA"` em `record_types`, `has_caa: true`.
2. **Domínio sem CAA:** Domínio qualquer sem CAA → `has_caa: false`, sem erro.
3. **Regressão:** Tempo de resolução DNS não aumenta significativamente (dnspython captura `NoAnswer` rápido).
