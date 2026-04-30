import os
import psycopg2
import requests

BASE = 'http://127.0.0.1:8000'
EMAIL = 'admin@observador.com'
PASSWORD = 'mls1509ti'

# auth
resp = requests.post(f"{BASE}/v1/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
resp.raise_for_status()
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

# 1) Disable CZDS enabled but not authorized
cur.execute("""
WITH authorized AS (
  SELECT unnest(%s::text[]) AS tld
)
SELECT p.tld
FROM ingestion_tld_policy p
LEFT JOIN authorized a ON a.tld = p.tld
WHERE p.source='czds' AND p.is_enabled=true AND a.tld IS NULL
ORDER BY p.tld
""", ([
'ai','airtel','au','bzh','ca','co','de','es','eu','fr','gdn','helsinki','io','it','merckmsd','moscow','msd','nl','protect','uk','us','voting','williamhill','xn--80adxhks','xn--czr694b','xn--g2xx48c','xn--kput3i','xn--ses554g'
],))
unauth = [r[0] for r in cur.fetchall()]

patched_ok = 0
patched_err = 0
for tld in unauth:
    r = requests.patch(f"{BASE}/v1/ingestion/tld-policy/czds/{tld}", json={"is_enabled": False}, headers=headers, timeout=30)
    if r.status_code < 300:
        patched_ok += 1
    else:
        patched_err += 1

# 2) reload for latest r2 success and latest pg != success (only czds/openintel)
cur.execute("""
WITH latest_r2 AS (
    SELECT DISTINCT ON (source, tld)
        source, tld
    FROM ingestion_run
    WHERE phase IN ('r2', 'full')
      AND status = 'success'
      AND source IN ('czds','openintel')
    ORDER BY source, tld, started_at DESC
),
latest_pg AS (
    SELECT DISTINCT ON (source, tld)
        source, tld, status AS pg_status
    FROM ingestion_run
    WHERE phase IN ('pg', 'full')
      AND source IN ('czds','openintel')
    ORDER BY source, tld, started_at DESC
)
SELECT r.source, r.tld
FROM latest_r2 r
LEFT JOIN latest_pg p ON p.source = r.source AND p.tld = r.tld
WHERE COALESCE(p.pg_status, 'never_run') != 'success'
ORDER BY r.source, r.tld
""")
reload_targets = cur.fetchall()

reload_ok = 0
reload_err = 0
for source, tld in reload_targets:
    r = requests.post(f"{BASE}/v1/ingestion/tld/{source}/{tld}/reload", headers=headers, timeout=30)
    if r.status_code < 300:
        reload_ok += 1
    else:
        reload_err += 1

# 3) run for enabled tlds with never success (czds/openintel)
cur.execute("""
SELECT p.source, p.tld
FROM ingestion_tld_policy p
WHERE p.is_enabled = true
  AND p.source IN ('czds','openintel')
  AND NOT EXISTS (
      SELECT 1 FROM ingestion_run ir
      WHERE ir.source = p.source
        AND ir.tld = p.tld
        AND ir.status = 'success'
  )
ORDER BY p.source, p.priority NULLS LAST, p.tld
""")
run_targets = cur.fetchall()

run_ok = 0
run_err = 0
for source, tld in run_targets:
    r = requests.post(f"{BASE}/v1/ingestion/tld/{source}/{tld}/run", headers=headers, timeout=30)
    if r.status_code < 300:
        run_ok += 1
    else:
        run_err += 1

print(f"unauthorized_found={len(unauth)} patched_ok={patched_ok} patched_err={patched_err}")
print(f"reload_targets={len(reload_targets)} reload_ok={reload_ok} reload_err={reload_err}")
print(f"run_targets={len(run_targets)} run_ok={run_ok} run_err={run_err}")
