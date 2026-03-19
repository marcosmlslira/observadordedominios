"""CZDS Ingestor Worker — scheduled execution of zone file syncs."""

from __future__ import annotations

import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.models.czds_tld_policy import CzdsTldPolicy
from app.services.use_cases.sync_czds_tld import (
    CooldownActiveError,
    SyncAlreadyRunningError,
    sync_czds_tld,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("czds_ingestor")


def _get_enabled_tlds() -> list[str]:
    """
    Read enabled TLDs from the database (preferred) or env var fallback.
    """
    db = SessionLocal()
    try:
        policies = (
            db.query(CzdsTldPolicy)
            .filter(CzdsTldPolicy.is_enabled == True)
            .order_by(CzdsTldPolicy.priority.asc(), CzdsTldPolicy.tld.asc())
            .all()
        )
        if policies:
            return [p.tld for p in policies]
    except Exception:
        logger.warning("Could not read czds_tld_policy, falling back to env.")
    finally:
        db.close()

    # Fallback to env
    raw = settings.CZDS_ENABLED_TLDS
    if raw:
        return [t.strip().lower() for t in raw.split(",") if t.strip()]

    return ["net", "org", "info"]


def run_sync_cycle() -> None:
    """Execute a full sync cycle: process each enabled TLD in priority order."""
    tlds = _get_enabled_tlds()
    logger.info("Starting sync cycle for TLDs: %s", tlds)

    for tld in tlds:
        db = SessionLocal()
        try:
            logger.info("▶ Syncing TLD=%s", tld)
            run_id = sync_czds_tld(db, tld)
            logger.info("✅ TLD=%s completed: run_id=%s", tld, run_id)
        except CooldownActiveError:
            logger.info("⏭ TLD=%s skipped (cooldown active)", tld)
        except SyncAlreadyRunningError:
            logger.warning("⏭ TLD=%s skipped (already running)", tld)
        except Exception:
            logger.exception("❌ TLD=%s failed", tld)
        finally:
            db.close()

    logger.info("Sync cycle finished.")


def main() -> None:
    logger.info("CZDS Ingestor Worker starting…")
    logger.info("Cron schedule: %s", settings.CZDS_SYNC_CRON)

    # Run initial sync on startup
    logger.info("Running initial sync cycle…")
    run_sync_cycle()

    # Schedule recurring syncs
    scheduler = BlockingScheduler()
    cron_parts = settings.CZDS_SYNC_CRON.split()
    trigger = CronTrigger(
        minute=cron_parts[0] if len(cron_parts) > 0 else "0",
        hour=cron_parts[1] if len(cron_parts) > 1 else "*",
        day=cron_parts[2] if len(cron_parts) > 2 else "*",
        month=cron_parts[3] if len(cron_parts) > 3 else "*",
        day_of_week=cron_parts[4] if len(cron_parts) > 4 else "*",
    )
    scheduler.add_job(run_sync_cycle, trigger, id="czds_sync", replace_existing=True)

    # Graceful shutdown
    def _shutdown(signum, frame):
        logger.info("Received signal %s, shutting down…", signum)
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("Scheduler started. Waiting for next trigger…")
    scheduler.start()


if __name__ == "__main__":
    main()
