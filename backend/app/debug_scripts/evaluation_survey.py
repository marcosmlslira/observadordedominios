"""
Avaliação completa do Observador de Domínios — 10 empresas brasileiras.
Simula o ponto de vista de um profissional de segurança digital / threat intel.
"""
import httpx
import json
import time
import sys
from datetime import datetime

API = "https://api.observadordedominios.com.br"
EMAIL = "admin@observador.com"
PASSWORD = "mls1509ti"

COMPANIES = [
    {
        "name": "Nubank",
        "brand_name": "nubank",
        "keywords": ["nu", "nuconta", "nubank"],
        "official_domains": ["nubank.com.br", "nu.com.br"],
        "tld_scope": ["com", "net", "org", "com.br", "net.br", "app", "io", "online", "site", "xyz", "top", "info", "store", "club", "live", "digital", "bank", "finance", "pay"],
    },
    {
        "name": "Itaú",
        "brand_name": "itau",
        "existing": True,
        "keywords": ["itau", "itaucard", "itaupersonnalite"],
        "official_domains": ["itau.com.br"],
        "tld_scope": ["com", "net", "org", "com.br", "net.br", "app", "io", "online", "site", "xyz", "top", "info", "bank", "finance"],
    },
    {
        "name": "Banco Inter",
        "brand_name": "bancointer",
        "keywords": ["inter", "bancointer", "interpag"],
        "official_domains": ["bancointer.com.br", "inter.co"],
        "tld_scope": ["com", "net", "org", "com.br", "net.br", "app", "io", "online", "site", "xyz", "top", "info", "bank", "finance", "pay"],
    },
    {
        "name": "Mercado Livre",
        "brand_name": "mercadolivre",
        "keywords": ["mercadolivre", "mercadopago", "meli"],
        "official_domains": ["mercadolivre.com.br", "mercadopago.com.br"],
        "tld_scope": ["com", "net", "org", "com.br", "net.br", "app", "io", "online", "site", "xyz", "top", "info", "store", "shop"],
    },
    {
        "name": "Magazine Luiza",
        "brand_name": "magalu",
        "keywords": ["magalu", "magazineluiza", "magalucom"],
        "official_domains": ["magazineluiza.com.br", "magalu.com.br"],
        "tld_scope": ["com", "net", "org", "com.br", "net.br", "app", "io", "online", "site", "xyz", "top", "info", "store", "shop"],
    },
    {
        "name": "Claro",
        "brand_name": "claro",
        "existing": True,
        "keywords": ["minhaclaro", "claro", "claromusica"],
        "official_domains": ["claro.com.br"],
        "tld_scope": ["com", "net", "org", "com.br", "net.br", "app", "io", "online", "site", "xyz", "top", "info", "live", "digital"],
    },
    {
        "name": "Vivo",
        "brand_name": "vivo",
        "keywords": ["vivo", "meuvivo", "vivofibra"],
        "official_domains": ["vivo.com.br"],
        "tld_scope": ["com", "net", "org", "com.br", "net.br", "app", "io", "online", "site", "xyz", "top", "info", "live", "digital"],
    },
    {
        "name": "iFood",
        "brand_name": "ifood",
        "keywords": ["ifood", "ifoodpay"],
        "official_domains": ["ifood.com.br"],
        "tld_scope": ["com", "net", "org", "com.br", "net.br", "app", "io", "online", "site", "xyz", "top", "info", "store", "delivery"],
    },
    {
        "name": "LATAM Airlines",
        "brand_name": "latam",
        "keywords": ["latam", "latamairlines", "latampass"],
        "official_domains": ["latam.com", "latamairlines.com"],
        "tld_scope": ["com", "net", "org", "com.br", "net.br", "app", "io", "online", "site", "xyz", "top", "info", "travel", "flights"],
    },
    {
        "name": "Hapvida",
        "brand_name": "hapvida",
        "keywords": ["hapvida", "hapvidasaude"],
        "official_domains": ["hapvida.com.br"],
        "tld_scope": ["com", "net", "org", "com.br", "net.br", "app", "io", "online", "site", "xyz", "top", "info", "health"],
    },
]


def authenticate(client: httpx.Client) -> str:
    r = client.post(f"{API}/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    r.raise_for_status()
    return r.json()["access_token"]


def get_brands(client: httpx.Client, headers: dict) -> dict:
    r = client.get(f"{API}/v1/brands?active_only=false", headers=headers)
    r.raise_for_status()
    return {b["brand_name"]: b for b in r.json()["items"]}


def create_brand(client: httpx.Client, headers: dict, company: dict) -> dict:
    payload = {
        "brand_name": company["brand_name"],
        "primary_brand_name": company["brand_name"],
        "official_domains": company.get("official_domains", []),
        "keywords": company.get("keywords", []),
        "tld_scope": company.get("tld_scope", []),
    }
    r = client.post(f"{API}/v1/brands", json=payload, headers=headers)
    r.raise_for_status()
    return r.json()


def trigger_scan(client: httpx.Client, headers: dict, brand_id: str) -> dict:
    r = client.post(f"{API}/v1/brands/{brand_id}/scan?force_full=true", headers=headers)
    if r.status_code == 409:
        print(f"    Scan already running for {brand_id}")
        return {"status": "already_running"}
    r.raise_for_status()
    return r.json()


def get_matches(client: httpx.Client, headers: dict, brand_id: str, limit: int = 50) -> dict:
    r = client.get(f"{API}/v1/brands/{brand_id}/matches?limit={limit}", headers=headers)
    r.raise_for_status()
    return r.json()


def get_matches_by_bucket(client: httpx.Client, headers: dict, brand_id: str, bucket: str, limit: int = 20) -> dict:
    r = client.get(f"{API}/v1/brands/{brand_id}/matches?attention_bucket={bucket}&limit={limit}", headers=headers)
    r.raise_for_status()
    return r.json()


def sync_search(client: httpx.Client, headers: dict, brand_name: str, keywords: list, tld_scope: list) -> dict:
    payload = {
        "brand_name": brand_name,
        "keywords": keywords,
        "tld_scope": tld_scope[:5],  # limit to avoid timeout
    }
    r = client.post(f"{API}/v1/similarity/search", json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    return r.json()


def enrich_domain(client: httpx.Client, headers: dict, domain: str, tools: list = None) -> dict:
    if tools is None:
        tools = ["dns_lookup", "whois", "ssl_check"]
    r = client.post(
        f"{API}/v1/tools/quick-analysis",
        json={"target": domain, "tools": tools},
        headers=headers,
        timeout=60,
    )
    if r.status_code != 200:
        return {"error": r.status_code, "detail": r.text[:200]}
    return r.json()


def format_match(m: dict) -> str:
    return (
        f"  {m.get('domain_name','?'):<35} "
        f"TLD=.{m.get('tld','?'):<8} "
        f"score={m.get('score_final',0):.3f}  "
        f"risk={m.get('risk_level','?'):<10} "
        f"bucket={m.get('attention_bucket','?'):<22} "
        f"reasons={m.get('reasons',[])} "
        f"enriched={m.get('enrichment_status','?')}"
    )


def format_enrichment(data: dict) -> str:
    lines = []
    for tool_name, result in data.get("results", {}).items():
        if isinstance(result, dict):
            status = result.get("status", "?")
            lines.append(f"    [{tool_name}] status={status}")
            if tool_name == "dns_lookup" and "result" in result:
                r = result["result"]
                if isinstance(r, dict):
                    a_records = r.get("a_records", r.get("A", []))
                    mx = r.get("mx_records", r.get("MX", []))
                    ns = r.get("ns_records", r.get("NS", []))
                    lines.append(f"      A={a_records}  MX={mx}  NS={ns}")
            elif tool_name == "ssl_check" and "result" in result:
                r = result["result"]
                if isinstance(r, dict):
                    issuer = r.get("issuer", r.get("issuer_organization", "?"))
                    valid = r.get("is_valid", r.get("valid", "?"))
                    lines.append(f"      issuer={issuer}  valid={valid}")
            elif tool_name == "whois" and "result" in result:
                r = result["result"]
                if isinstance(r, dict):
                    registrar = r.get("registrar", "?")
                    created = r.get("creation_date", r.get("created", "?"))
                    lines.append(f"      registrar={registrar}  created={created}")
        else:
            lines.append(f"    [{tool_name}] {str(result)[:100]}")
    return "\n".join(lines) if lines else "    (no enrichment data)"


def main():
    client = httpx.Client(timeout=30, verify=True)

    print("=" * 70)
    print("AUTENTICANDO...")
    token = authenticate(client)
    headers = {"Authorization": f"Bearer {token}"}
    print(f"Token obtido: {token[:20]}...")

    # Get existing brands
    existing_brands = get_brands(client, headers)
    print(f"\nMarcas existentes: {list(existing_brands.keys())}")

    results = {}

    for i, company in enumerate(COMPANIES, 1):
        name = company["name"]
        brand_name = company["brand_name"]
        print(f"\n{'='*70}")
        print(f"[{i}/10] {name} (brand: {brand_name})")
        print("=" * 70)

        # Step 1: Create or find brand
        if brand_name in existing_brands:
            brand = existing_brands[brand_name]
            print(f"  Brand already exists: {brand['id']}")
        else:
            try:
                brand = create_brand(client, headers, company)
                print(f"  Brand created: {brand['id']}")
            except Exception as e:
                print(f"  ERROR creating brand: {e}")
                results[name] = {"error": str(e)}
                continue

        brand_id = brand["id"]

        # Step 2: Get existing matches
        print(f"\n  --- Existing matches ---")
        try:
            matches_data = get_matches(client, headers, brand_id, limit=50)
            total = matches_data.get("total", 0)
            matches = matches_data.get("items", [])
            print(f"  Total matches: {total}")

            # Show by bucket
            for bucket in ["immediate_attention", "defensive_gap", "watchlist"]:
                bucket_data = get_matches_by_bucket(client, headers, brand_id, bucket, limit=10)
                bucket_items = bucket_data.get("items", [])
                bucket_total = bucket_data.get("total", 0)
                print(f"\n  [{bucket}] ({bucket_total} total)")
                for m in bucket_items[:5]:
                    print(format_match(m))
        except Exception as e:
            print(f"  ERROR getting matches: {e}")
            matches = []
            total = 0

        # Step 3: Trigger scan (async, won't wait)
        print(f"\n  --- Triggering scan ---")
        try:
            scan_result = trigger_scan(client, headers, brand_id)
            print(f"  Scan triggered: {json.dumps(scan_result)[:200]}")
        except Exception as e:
            print(f"  Scan trigger failed: {e}")

        # Step 4: Sync search for immediate results if no matches
        sync_results = None
        if total == 0:
            print(f"\n  --- Sync search (no existing matches) ---")
            try:
                sync_results = sync_search(
                    client, headers, brand_name,
                    company.get("keywords", []),
                    company.get("tld_scope", [])
                )
                sync_matches = sync_results.get("matches", sync_results.get("results", []))
                if isinstance(sync_matches, list):
                    print(f"  Sync found: {len(sync_matches)} results")
                    for m in sync_matches[:10]:
                        if isinstance(m, dict):
                            print(f"    {m.get('domain_name', m.get('domain', '?')):<35} score={m.get('score_final', m.get('score', '?'))}")
                else:
                    print(f"  Sync result type: {type(sync_matches)}")
                    print(f"  Raw: {json.dumps(sync_results)[:500]}")
            except Exception as e:
                print(f"  Sync search failed: {e}")

        # Step 5: Enrich top 3 suspicious domains
        print(f"\n  --- Enrichment (top 3 suspicious) ---")
        enrichment_targets = []

        # Prioritize: immediate_attention > defensive_gap > watchlist
        for m in matches:
            if m.get("attention_bucket") == "immediate_attention":
                enrichment_targets.append(m["domain_name"])
            if len(enrichment_targets) >= 3:
                break
        if len(enrichment_targets) < 3:
            for m in matches:
                if m.get("attention_bucket") == "defensive_gap" and m["domain_name"] not in enrichment_targets:
                    enrichment_targets.append(m["domain_name"])
                if len(enrichment_targets) >= 3:
                    break
        if len(enrichment_targets) < 3:
            for m in matches:
                if m["domain_name"] not in enrichment_targets:
                    enrichment_targets.append(m["domain_name"])
                if len(enrichment_targets) >= 3:
                    break

        enrichments = {}
        for domain in enrichment_targets:
            print(f"\n  Enriching: {domain}")
            try:
                enrich_data = enrich_domain(client, headers, domain)
                enrichments[domain] = enrich_data
                print(format_enrichment(enrich_data))
            except Exception as e:
                print(f"    ERROR: {e}")
                enrichments[domain] = {"error": str(e)}

        results[name] = {
            "brand_id": brand_id,
            "total_matches": total,
            "matches": matches,
            "sync_results": sync_results,
            "enrichments": enrichments,
            "enrichment_targets": enrichment_targets,
        }

        # Brief pause between companies
        time.sleep(1)

    # Step 6: Global metrics
    print(f"\n{'='*70}")
    print("GLOBAL METRICS")
    print("=" * 70)
    try:
        r = client.get(f"{API}/v1/similarity/metrics", headers=headers)
        metrics = r.json()
        print(json.dumps(metrics, indent=2)[:2000])
    except Exception as e:
        print(f"Metrics error: {e}")

    # Step 7: Trends
    print(f"\n{'='*70}")
    print("DISCOVERY TRENDS (30 days)")
    print("=" * 70)
    try:
        r = client.get(f"{API}/v1/similarity/trends?days=30", headers=headers)
        trends = r.json()
        print(json.dumps(trends, indent=2)[:2000])
    except Exception as e:
        print(f"Trends error: {e}")

    # Save raw results
    output_path = "/tmp/evaluation_results.json"
    with open(output_path, "w") as f:
        # Convert non-serializable to strings
        json.dump(results, f, indent=2, default=str)
    print(f"\nRaw results saved to {output_path}")

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print("=" * 70)
    for name, data in results.items():
        if "error" in data:
            print(f"  {name:<20} ERROR: {data['error']}")
        else:
            total = data.get("total_matches", 0)
            enriched = len(data.get("enrichments", {}))
            print(f"  {name:<20} matches={total:<6} enriched={enriched}")


if __name__ == "__main__":
    main()
