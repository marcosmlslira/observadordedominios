"""
Full OpenINTEL ingestion benchmark — all available TLDs, timed.
Bypasses CZDS guard (partitions are disjoint).
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

# Ordered smallest → largest (warm up on small TLDs first)
TLDS = ["root", "gov", "li", "ee", "nu", "sk", "se", "ch", "fr"]

results = []
client = OpenIntelClient()

for tld in TLDS:
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"TLD: {tld}  [{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}]")
    print(sep)

    db = SessionLocal()
    try:
        result = client.discover_snapshot(tld)
        if not result:
            print("  SKIP: no snapshot found")
            results.append({"tld": tld, "skipped": True})
            continue

        keys, snap_date = result
        print(f"  snapshot={snap_date}  parts={len(keys)}")

        ensure_partition(db, tld)

        run_repo = IngestionRunRepository(db)
        run = run_repo.create_run("openintel", tld)
        db.commit()
        print(f"  run_id={run.id}")

        t0 = time.time()
        domain_stream = client.stream_apex_domains(keys, tld)
        metrics = apply_domain_names_delta(db, domain_stream, tld=tld, run_id=run.id)
        elapsed = time.time() - t0

        run_repo.finish_run(run, status="success", metrics=metrics)
        run_repo.upsert_checkpoint("openintel", tld, run)
        db.commit()

        rate = metrics["seen"] / elapsed if elapsed > 0 else 0
        print(
            f"  DONE: seen={metrics['seen']:,}  inserted={metrics['inserted']:,}"
            f"  elapsed={elapsed:.1f}s  rate={int(rate):,} dom/s"
        )
        results.append(
            {
                "tld": tld,
                "seen": metrics["seen"],
                "inserted": metrics["inserted"],
                "elapsed_s": round(elapsed, 1),
                "rate_dom_s": int(rate),
            }
        )

    except Exception as e:
        db.rollback()
        print(f"  ERROR: {e}")
        results.append({"tld": tld, "error": str(e)})
    finally:
        db.close()

print("\n")
print("=" * 60)
print("BENCHMARK SUMMARY")
print("=" * 60)
header = f"{'TLD':<10} {'Domains':>10} {'Inserted':>10} {'Time(s)':>9} {'dom/s':>10}"
print(header)
print("-" * 55)
for r in results:
    if r.get("skipped"):
        print(f"{r['tld']:<10} (no snapshot)")
    elif r.get("error"):
        print(f"{r['tld']:<10} ERROR  {str(r['error'])[:40]}")
    else:
        print(
            f"{r['tld']:<10} {r['seen']:>10,} {r['inserted']:>10,}"
            f" {r['elapsed_s']:>9.1f} {r['rate_dom_s']:>10,}"
        )

total_domains = sum(r.get("seen", 0) for r in results)
total_time = sum(r.get("elapsed_s", 0.0) for r in results)
print(f"\nTOTAL: {total_domains:,} domains in {total_time:.1f}s")
