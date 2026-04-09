"""
Full OpenINTEL ingestion benchmark — .fr only (full 4 parts, ~3.5GB).
Compare timing and rate against CZDS runs.
"""
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, "/app")

from app.infra.db.session import SessionLocal
from app.infra.external.openintel_client import OpenIntelClient
from app.repositories.domain_repository import ensure_partition
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.services.use_cases.apply_zone_delta import apply_domain_names_delta
from sqlalchemy import text

db = SessionLocal()

print("=" * 65)
print("OpenINTEL Full Ingestion Benchmark — .fr (all 4 parts, ~3.5 GB)")
print(f"Started: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
print("=" * 65)

# ── CZDS comparison data ─────────────────────────────────────────
print("\n[CZDS run history for comparison]")
czds_runs = db.execute(text("""
    SELECT tld, status, domains_seen, domains_inserted,
           started_at, finished_at,
           EXTRACT(EPOCH FROM (finished_at - started_at)) AS elapsed_s
    FROM ingestion_run
    WHERE source = 'czds' AND status = 'success'
    ORDER BY domains_seen DESC
    LIMIT 15
""")).fetchall()
if czds_runs:
    print(f"  {'TLD':<12} {'Seen':>12} {'Time(s)':>10} {'dom/s':>10}")
    print("  " + "-" * 48)
    for r in czds_runs:
        if r[6] and r[6] > 0:
            rate = int(r[2] / r[6])
            print(f"  {r[0]:<12} {r[2]:>12,} {int(r[6]):>10,} {rate:>10,}")
else:
    print("  No completed CZDS runs found")

# ── Delete previous test run (1000 domains) ─────────────────────
print("\n[Clearing previous fr test data]")
db.execute(text("DELETE FROM domain_fr"))
db.execute(text("DELETE FROM ingestion_run WHERE source='openintel' AND tld='fr'"))
db.execute(text("DELETE FROM ingestion_checkpoint WHERE source='openintel' AND tld='fr'"))
db.commit()
count_after = db.execute(text("SELECT COUNT(*) FROM domain_fr")).scalar()
print(f"  domain_fr rows after clear: {count_after}")

# ── Full .fr ingestion ────────────────────────────────────────────
print("\n[Starting full .fr ingestion]")
client = OpenIntelClient()
result = client.discover_snapshot("fr")
keys, snap_date = result
total_mb = 3475.8  # from earlier check
print(f"  snapshot={snap_date}  parts={len(keys)}  ~{total_mb:.0f} MB compressed")
for k in keys:
    print(f"    {k.split('/')[-1]}")

ensure_partition(db, "fr")
run_repo = IngestionRunRepository(db)
run = run_repo.create_run("openintel", "fr")
db.commit()
print(f"  run_id={run.id}")

t0 = time.time()
last_report = t0
domain_count = 0

def instrumented_stream():
    """Wrap stream to print progress every 500k domains."""
    global domain_count, last_report
    for domain in client.stream_apex_domains(keys, "fr"):
        domain_count += 1
        now = time.time()
        if now - last_report >= 30:
            elapsed = now - t0
            rate = domain_count / elapsed
            print(
                f"  [{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}] "
                f"{domain_count:,} domains streamed  "
                f"elapsed={elapsed:.0f}s  rate={int(rate):,} dom/s"
            )
            last_report = now
        yield domain

metrics = apply_domain_names_delta(db, instrumented_stream(), tld="fr", run_id=run.id)
elapsed = time.time() - t0

run_repo.finish_run(run, status="success", metrics=metrics)
run_repo.upsert_checkpoint("openintel", "fr", run)
db.commit()

rate = metrics["seen"] / elapsed if elapsed > 0 else 0

print(f"\n{'=' * 65}")
print("RESULT")
print(f"{'=' * 65}")
print(f"  TLD:        fr")
print(f"  Snapshot:   {snap_date}")
print(f"  Parts:      {len(keys)} Parquet files (~3.5 GB compressed)")
print(f"  Domains:    {metrics['seen']:,} seen  /  {metrics['inserted']:,} inserted")
print(f"  Elapsed:    {elapsed:.1f}s  ({elapsed/60:.1f} min)")
print(f"  Rate:       {int(rate):,} domains/sec")

if czds_runs:
    # Find best comparable CZDS run
    best_czds = max(czds_runs, key=lambda r: r[2] or 0)
    if best_czds[6] and best_czds[6] > 0:
        czds_rate = int(best_czds[2] / best_czds[6])
        print(f"\n  vs CZDS {best_czds[0]:12s}  {best_czds[2]:,} domains  "
              f"{int(best_czds[6])}s  {czds_rate:,} dom/s")
        ratio = rate / czds_rate if czds_rate > 0 else 0
        print(f"  OpenINTEL/CZDS rate ratio: {ratio:.2f}x")

db.close()
print(f"\nFinished: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
