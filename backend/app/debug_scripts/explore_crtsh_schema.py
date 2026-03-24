"""Explore crt.sh schema to find the right query approach."""
import psycopg2

conn = psycopg2.connect("host=crt.sh port=5432 dbname=certwatch user=guest", connect_timeout=30)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor()
cur.execute("SET statement_timeout = '55s'")

# Test what x509_altNames returns
print("=== x509_altNames(cert, 2) test ===")
cur.execute("""
    SELECT c.id, x509_altNames(c.certificate, 2) AS sans
    FROM certificate c
    WHERE identities(c.certificate) @@ plainto_tsquery('certwatch', 'net.br')
      AND x509_notAfter(c.certificate) >= '2026-01-01'::timestamp
      AND x509_notAfter(c.certificate) < '2026-04-01'::timestamp
    ORDER BY c.id
    LIMIT 3
""")
for row in cur.fetchall():
    print(f"  id={row[0]} type={type(row[1]).__name__} value={repr(row[1][:300] if row[1] else None)}")

conn.close()
