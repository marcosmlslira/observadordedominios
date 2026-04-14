"""Check DB active queries and ingestion run status"""
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("158.69.211.109", username="ubuntu", password="mls1509ti", timeout=20)

PG = "observador_postgres.1.qdl4bsndspya0zr8vwjmkxsvt"

def query(sql):
    cmd = f'docker exec -i {PG} psql -U obs -d obs -c "{sql}"'
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode()
    err = stderr.read().decode().strip()
    if err:
        print("STDERR:", err[:200])
    return out

print("=== Active queries ===")
print(query(
    "SELECT pid, state, wait_event_type, wait_event, "
    "left(query, 80) as q, "
    "extract(epoch from (now()-query_start))::int as secs "
    "FROM pg_stat_activity "
    "WHERE state != 'idle' AND pid != pg_backend_pid() "
    "ORDER BY secs DESC NULLS LAST LIMIT 15;"
))

print("=== Locks (not granted) ===")
print(query(
    "SELECT l.pid, l.mode, l.granted, "
    "a.state, left(a.query, 60) as q "
    "FROM pg_locks l JOIN pg_stat_activity a ON l.pid = a.pid "
    "WHERE NOT l.granted "
    "ORDER BY l.granted LIMIT 20;"
))

print("=== Running ingestion_run ===")
print(query(
    "SELECT id, source, tld, status, domains_seen, domains_inserted, "
    "started_at, updated_at "
    "FROM ingestion_run "
    "WHERE status = 'running' "
    "ORDER BY started_at DESC LIMIT 10;"
))

print("=== Recent ingestion_run (last 5 hours) ===")
print(query(
    "SELECT id, source, tld, status, domains_seen, domains_inserted, "
    "started_at, finished_at "
    "FROM ingestion_run "
    "WHERE started_at > now() - interval '5 hours' "
    "ORDER BY started_at DESC LIMIT 20;"
))

client.close()

