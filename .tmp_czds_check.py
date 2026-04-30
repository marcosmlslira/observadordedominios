import psycopg2
from ingestion.config.settings import get_settings
from ingestion.sources.czds.client import CZDSClient

cfg = get_settings()
client = CZDSClient(cfg)
token = client.authenticate()
authorized = client.authorized_tlds(token)

conn = psycopg2.connect(cfg.database_url)
with conn.cursor() as cur:
    cur.execute("SELECT tld FROM ingestion_tld_policy WHERE source='czds' AND is_enabled")
    in_policy = {r[0] for r in cur.fetchall()}

not_seeded = authorized - in_policy
not_authorized = in_policy - authorized

print(f'authorized_count={len(authorized)}')
print(f'policy_enabled_count={len(in_policy)}')
print(f'not_seeded_count={len(not_seeded)}')
print(f'not_authorized_count={len(not_authorized)}')
print('not_seeded_sample=' + ','.join(sorted(not_seeded)[:30]))
print('not_authorized_sample=' + ','.join(sorted(not_authorized)[:30]))
