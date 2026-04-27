"""Idempotent TLD provisioning — creates domain partitions and staging tables.

Guarantees:
  - Runs under pg_advisory_lock to prevent concurrent execution.
  - Each TLD is wrapped in a SAVEPOINT so one failure cannot cancel others.
  - Safe to re-run multiple times: all operations use IF NOT EXISTS checks.
  - Never called from inside the daily ingestion cycle (hot path stays DDL-free).

CLI usage:
  python -m ingestion.provisioning.provision_tld

Programmatic usage:
  from ingestion.provisioning.provision_tld import provision_all_tlds
  summary = provision_all_tlds(db_url)
"""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

import psycopg2

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

# pg_advisory_lock key — consistent across all worker instances
_ADVISORY_LOCK_KEY = "ingestion_provision"


def _safe_tld(tld: str) -> str:
    return tld.replace("-", "_").replace(".", "_")


def _provision_single_tld(conn, tld: str) -> dict[str, list[str]]:
    """Create partition + staging tables for one TLD. Called inside a SAVEPOINT."""
    safe = _safe_tld(tld)
    created: list[str] = []

    with conn.cursor() as cur:
        # ── domain partition ──────────────────────────────────────────────────
        cur.execute(
            "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename = %s",
            (f"domain_{safe}",),
        )
        if not cur.fetchone():
            cur.execute(
                f"CREATE TABLE domain_{safe} PARTITION OF domain FOR VALUES IN ('{tld}')"
            )
            created.append(f"domain_{safe}")
            log.info("provision: created domain_%s", safe)

        # ── domain_removed partition ──────────────────────────────────────────
        cur.execute(
            "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename = %s",
            (f"domain_removed_{safe}",),
        )
        if not cur.fetchone():
            cur.execute(
                f"CREATE TABLE domain_removed_{safe} PARTITION OF domain_removed FOR VALUES IN ('{tld}')"
            )
            created.append(f"domain_removed_{safe}")
            log.info("provision: created domain_removed_%s", safe)

        # ── staging table (no indexes, no constraints — pure staging) ─────────
        cur.execute(
            "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename = %s",
            (f"staging_{safe}",),
        )
        if not cur.fetchone():
            cur.execute(
                f"""
                CREATE TABLE staging_{safe} (
                    name     TEXT,
                    tld      TEXT,
                    label    TEXT,
                    added_day INTEGER
                )
                """
            )
            created.append(f"staging_{safe}")
            log.info("provision: created staging_%s", safe)

        # ── staging_removed table ─────────────────────────────────────────────
        cur.execute(
            "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename = %s",
            (f"staging_removed_{safe}",),
        )
        if not cur.fetchone():
            cur.execute(
                f"""
                CREATE TABLE staging_removed_{safe} (
                    name        TEXT,
                    tld         TEXT,
                    removed_day INTEGER
                )
                """
            )
            created.append(f"staging_removed_{safe}")
            log.info("provision: created staging_removed_%s", safe)

    return {"created": created}


def provision_all_tlds(db_url: str) -> dict:
    """Provision all enabled TLDs from ingestion_tld_policy.

    Returns:
        {
          "tlds_processed": int,
          "tables_created": list[str],
          "errors": list[tuple[str, str]],
          "skipped": bool,   # True if advisory lock was held by another process
        }
    """
    conn = psycopg2.connect(db_url)
    try:
        # Advisory lock — non-blocking; skip if already running elsewhere
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s))", (_ADVISORY_LOCK_KEY,)
            )
            locked: bool = cur.fetchone()[0]

        if not locked:
            log.info("provision: advisory lock held by another process — skipping")
            return {"skipped": True, "tlds_processed": 0, "tables_created": [], "errors": []}

        try:
            # Discover enabled TLDs
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT DISTINCT tld FROM ingestion_tld_policy
                    WHERE is_enabled = true
                    ORDER BY tld
                    """
                )
                rows = cur.fetchall()

            tlds = [r[0] for r in rows]
            log.info("provision: %d enabled TLDs to check", len(tlds))

            all_created: list[str] = []
            errors: list[tuple[str, str]] = []

            for tld in tlds:
                try:
                    conn.execute("SAVEPOINT sp_provision_tld")
                    result = _provision_single_tld(conn, tld)
                    conn.execute("RELEASE SAVEPOINT sp_provision_tld")
                    all_created.extend(result["created"])
                except Exception as exc:  # noqa: BLE001
                    conn.execute("ROLLBACK TO SAVEPOINT sp_provision_tld")
                    log.error("provision: failed for tld=%s: %s", tld, exc)
                    errors.append((tld, str(exc)))

            conn.commit()

            log.info(
                "provision: done — %d TLDs processed, %d tables created, %d errors",
                len(tlds),
                len(all_created),
                len(errors),
            )
            return {
                "skipped": False,
                "tlds_processed": len(tlds),
                "tables_created": all_created,
                "errors": errors,
            }
        finally:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT pg_advisory_unlock(hashtext(%s))", (_ADVISORY_LOCK_KEY,)
                )
    finally:
        conn.close()


def main() -> None:
    """CLI entry point: provision_tld.py DATABASE_URL"""
    import os

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    db_url = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("ERROR: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    result = provision_all_tlds(db_url)
    if result.get("skipped"):
        print("Skipped: another provisioning process holds the advisory lock.")
        sys.exit(0)

    print(
        f"Provisioned {result['tlds_processed']} TLDs — "
        f"{len(result['tables_created'])} tables created, "
        f"{len(result['errors'])} errors"
    )
    if result["errors"]:
        for tld, err in result["errors"]:
            print(f"  ERROR {tld}: {err}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
