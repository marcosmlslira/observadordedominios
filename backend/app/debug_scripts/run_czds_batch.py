"""Manual batch runner for CZDS TLDs that have never been successfully executed.

Usage (inside backend container):
    python app/debug_scripts/run_czds_batch.py [--limit N] [--tlds tld1,tld2,...]

Runs TLDs sequentially, ordered by priority (smallest first).
Skips suspended, already-running, or cooldown-active TLDs.
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import text

from app.infra.db.session import SessionLocal
from app.services.use_cases.sync_czds_tld import (
    CooldownActiveError,
    SyncAlreadyRunningError,
    TldSuspendedError,
    sync_czds_tld,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("czds_batch")


def get_pending_tlds(limit: int) -> list[str]:
    db = SessionLocal()
    try:
        rows = db.execute(text("""
            SELECT p.tld
            FROM czds_tld_policy p
            WHERE p.is_enabled = true
              AND (p.suspended_until IS NULL OR p.suspended_until < NOW())
              AND p.tld NOT IN (
                  SELECT DISTINCT tld FROM ingestion_run
                  WHERE source = 'czds' AND status IN ('running', 'success')
              )
            ORDER BY p.priority ASC, p.tld ASC
            LIMIT :limit
        """), {"limit": limit})
        return [r[0] for r in rows]
    finally:
        db.close()


def run_tld(tld: str) -> str:
    db = SessionLocal()
    try:
        sync_czds_tld(db, tld)
        return "ok"
    except SyncAlreadyRunningError:
        return "already_running"
    except CooldownActiveError:
        return "cooldown"
    except TldSuspendedError:
        return "suspended"
    except Exception as e:
        return f"error: {e}"
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30, help="Max TLDs to process")
    parser.add_argument("--tlds", type=str, default="", help="Comma-separated TLD list (overrides DB query)")
    args = parser.parse_args()

    if args.tlds:
        tlds = [t.strip().lower() for t in args.tlds.split(",") if t.strip()]
    else:
        tlds = get_pending_tlds(args.limit)

    logger.info("Starting batch for %d TLDs: %s", len(tlds), tlds)

    results: dict[str, list[str]] = {"ok": [], "skipped": [], "error": []}

    for i, tld in enumerate(tlds, 1):
        logger.info("[%d/%d] Processing .%s ...", i, len(tlds), tld)
        result = run_tld(tld)
        if result == "ok":
            logger.info("  ✓ .%s done", tld)
            results["ok"].append(tld)
        elif result in ("already_running", "cooldown", "suspended"):
            logger.info("  ~ .%s skipped (%s)", tld, result)
            results["skipped"].append(f"{tld}({result})")
        else:
            logger.warning("  ✗ .%s %s", tld, result)
            results["error"].append(f"{tld}: {result}")

    logger.info("=== DONE: %d ok, %d skipped, %d errors ===",
                len(results["ok"]), len(results["skipped"]), len(results["error"]))
    if results["error"]:
        logger.warning("Errors: %s", results["error"])


if __name__ == "__main__":
    main()
