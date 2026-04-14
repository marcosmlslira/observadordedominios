"""Temporary DB check script - run via: python scripts/check_db.py"""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("158.69.211.109", username="ubuntu", password="mls1509ti", timeout=20)

# Find postgres container name
stdin, stdout, stderr = client.exec_command(
    "docker ps --format '{{.Names}}' | grep postgres | head -1"
)
pg_cid = stdout.read().decode().strip()
print(f"Postgres container: {pg_cid}")

# Check active queries
sql = (
    "SELECT pid, state, wait_event_type, wait_event, "
    "left(query, 80) as q, "
    "extract(epoch from (now()-query_start))::int as secs "
    "FROM pg_stat_activity "
    "WHERE state != 'idle' "
    "ORDER BY secs DESC NULLS LAST LIMIT 15;"
)
stdin, stdout, stderr = client.exec_command(
    f'docker exec -i {pg_cid} psql -U postgres -c "{sql}"'
)
print(stdout.read().decode())
e = stderr.read().decode().strip()
if e:
    print("STDERR:", e[:300])

# Check locks
lock_sql = (
    "SELECT l.pid, l.mode, l.granted, l.relation::regclass as rel, "
    "a.state, left(a.query, 60) as q "
    "FROM pg_locks l JOIN pg_stat_activity a ON l.pid = a.pid "
    "WHERE NOT l.granted OR l.mode IN ('ExclusiveLock','AccessExclusiveLock') "
    "ORDER BY l.granted LIMIT 20;"
)
stdin, stdout, stderr = client.exec_command(
    f'docker exec -i {pg_cid} psql -U postgres -c "{lock_sql}"'
)
print("\n--- Locks ---")
print(stdout.read().decode())

client.close()
