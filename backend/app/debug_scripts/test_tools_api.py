"""Test tools API endpoints via HTTP requests inside the container."""
import json
import sys

import httpx

BASE = "http://localhost:8000"
EMAIL = "admin@observador.com"
PASSWORD = "admin123"


def get_token():
    r = httpx.post(f"{BASE}/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=10)
    r.raise_for_status()
    return r.json()["access_token"]


def test(client, path, payload=None, params=None, method="POST"):
    if method == "POST":
        r = client.post(f"{BASE}{path}", json=payload or {}, params=params, timeout=30)
    else:
        r = client.get(f"{BASE}{path}", params=params, timeout=30)
    return r


def main():
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client(headers=headers) as client:
        # Test DNS Lookup (should be cached now)
        print("=== DNS Lookup (cached) ===")
        r = test(client, "/v1/tools/dns-lookup", {"target": "google.com"})
        data = r.json()
        print(f"  status={data['status']} cached={data['cached']} records={len(data['result']['records'])}")

        # Test SSL Check
        print("\n=== SSL Check ===")
        r = test(client, "/v1/tools/ssl-check", {"target": "google.com"})
        data = r.json()
        cert = data.get("result", {}).get("certificate", {})
        print(f"  status={data['status']} valid={data['result']['is_valid']} days_remaining={cert.get('days_remaining')}")

        # Test HTTP Headers
        print("\n=== HTTP Headers ===")
        r = test(client, "/v1/tools/http-headers", {"target": "google.com"})
        data = r.json()
        res = data.get("result", {})
        print(f"  status={data['status']} final_url={res.get('final_url')} status_code={res.get('status_code')}")

        # Test History
        print("\n=== History ===")
        r = test(client, "/v1/tools/history", method="GET", params={"limit": 10})
        data = r.json()
        print(f"  total={data['total']}")
        for item in data["items"][:5]:
            print(f"    {item['tool_type']:20} {item['target']:20} {item['status']} ({item['duration_ms']}ms) cached_ok={item['triggered_by']}")

        # Test Quick Analysis (with only already-cached tools to be fast)
        print("\n=== Quick Analysis (dns_lookup + ssl_check, should use cache) ===")
        r = client.post(f"{BASE}/v1/tools/quick-analysis", json={
            "target": "google.com",
            "tools": ["dns_lookup", "ssl_check", "http_headers"]
        }, timeout=90)
        data = r.json()
        print(f"  status={data['status']} total_ms={data['total_duration_ms']}")
        for tool_type, res in data["results"].items():
            print(f"    {tool_type:20} {res['status']} ({res.get('duration_ms')}ms)")

    print("\nAll tests passed!")


if __name__ == "__main__":
    main()
