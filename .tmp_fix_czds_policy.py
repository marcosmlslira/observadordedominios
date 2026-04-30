import psycopg2
from ingestion.config.settings import get_settings
from ingestion.sources.czds.client import CZDSClient

cfg = get_settings()
client = CZDSClient(cfg)
token = client.authenticate()
authorized = client.authorized_tlds(token)

conn = psycopg2.connect(cfg.database_url)
conn.autocommit = False
cur = conn.cursor()

cur.execute("SELECT count(*) FROM ingestion_tld_policy WHERE source='czds'")
total = cur.fetchone()[0]

cur.execute("UPDATE ingestion_tld_policy SET is_enabled=false WHERE source='czds'")
cur.execute("UPDATE ingestion_tld_policy SET is_enabled=true WHERE source='czds' AND tld = ANY(%s)", (list(authorized),))

cur.execute("SELECT count(*) FROM ingestion_tld_policy WHERE source='czds' AND is_enabled=true")
enabled_after = cur.fetchone()[0]
cur.execute("SELECT count(*) FROM ingestion_tld_policy WHERE source='czds' AND is_enabled=false")
disabled_after = cur.fetchone()[0]

conn.commit()
print(f'czds_total={total}')
print(f'authorized_count={len(authorized)}')
print(f'enabled_after={enabled_after}')
print(f'disabled_after={disabled_after}')
