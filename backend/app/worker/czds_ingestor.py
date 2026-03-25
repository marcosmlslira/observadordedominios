"""CZDS Ingestor Worker — scheduled execution of zone file syncs."""

from __future__ import annotations

import logging
import signal
import threading

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.infra.external.czds_client import CZDSAuthRateLimitedError, CZDSClient
from app.infra.db.session import SessionLocal
from app.models.czds_tld_policy import CzdsTldPolicy
from app.repositories.ingestion_run_repository import IngestionRunRepository
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
logger = logging.getLogger("czds_ingestor")
STOP_EVENT = threading.Event()


def _wait_or_stop(seconds: int) -> bool:
    """Sleep in an interruptible way. Returns True when a stop was requested."""
    return STOP_EVENT.wait(seconds)


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


def _get_missing_bootstrap_tlds() -> list[str]:
    """Return enabled TLDs that still have no successful CZDS checkpoint."""
    tlds = _get_enabled_tlds()
    if not tlds:
        return []

    db = SessionLocal()
    try:
        completed = IngestionRunRepository(db).list_checkpoint_tlds("czds")
    finally:
        db.close()

    return [tld for tld in tlds if tld not in completed]


def run_sync_cycle(tlds: list[str] | None = None) -> None:
    """Execute a sync cycle for the provided TLDs in priority order."""
    tlds = tlds or _get_enabled_tlds()
    logger.info("Starting sync cycle for TLDs: %s", tlds)
    shared_czds_client = CZDSClient()

    for tld in tlds:
        if STOP_EVENT.is_set():
            logger.info("Stop requested. Ending sync cycle before TLD=%s.", tld)
            break
        db = SessionLocal()
        try:
            logger.info("▶ Syncing TLD=%s", tld)
            run_id = sync_czds_tld(db, tld, czds_client=shared_czds_client)
            logger.info("✅ TLD=%s completed: run_id=%s", tld, run_id)
        except CooldownActiveError:
            logger.info("⏭ TLD=%s skipped (cooldown active)", tld)
        except TldSuspendedError as exc:
            logger.info("⏭ TLD=%s skipped (%s)", tld, exc)
        except SyncAlreadyRunningError:
            logger.warning("⏭ TLD=%s skipped (already running)", tld)
        except CZDSAuthRateLimitedError:
            logger.warning(
                "CZDS authentication throttled. Waiting %d seconds before continuing.",
                settings.CZDS_AUTH_RATE_LIMIT_BACKOFF_SECONDS,
            )
            _wait_or_stop(settings.CZDS_AUTH_RATE_LIMIT_BACKOFF_SECONDS)
            break
        except Exception:
            logger.exception("❌ TLD=%s failed", tld)
        finally:
            db.close()

    logger.info("Sync cycle finished.")


def run_bootstrap_until_complete() -> None:
    """
    Keep replaying the missing-first-sync backlog until every enabled TLD
    has at least one successful checkpoint.
    """
    backoff_seconds = 60

    while not STOP_EVENT.is_set():
        missing = _get_missing_bootstrap_tlds()
        if not missing:
            logger.info("CZDS bootstrap is complete for all enabled TLDs.")
            return

        before_count = len(missing)
        logger.info(
            "Bootstrap backlog: %d enabled TLD(s) still missing a first successful sync.",
            before_count,
        )
        run_sync_cycle(missing)

        if STOP_EVENT.is_set():
            return

        remaining = _get_missing_bootstrap_tlds()
        if not remaining:
            logger.info("CZDS bootstrap is complete for all enabled TLDs.")
            return

        if len(remaining) >= before_count:
            logger.info(
                "Bootstrap backlog unchanged at %d TLD(s). Waiting %d seconds before retry.",
                len(remaining),
                backoff_seconds,
            )
            if _wait_or_stop(backoff_seconds):
                return
            continue

        logger.info(
            "Bootstrap backlog reduced from %d to %d TLD(s). Continuing immediately.",
            before_count,
            len(remaining),
        )


def run_catchup_cycle() -> None:
    """Run the normal cycle and then immediately backfill any never-synced TLDs."""
    run_sync_cycle()
    if not STOP_EVENT.is_set():
        run_bootstrap_until_complete()


def main() -> None:
    logger.info("CZDS Ingestor Worker starting…")
    logger.info("Cron schedule: %s", settings.CZDS_SYNC_CRON)

    # Run initial sync on startup
    logger.info("Running initial sync cycle…")
    run_catchup_cycle()

    if STOP_EVENT.is_set():
        logger.info("Stop requested during startup catch-up. Exiting worker.")
        return

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
    scheduler.add_job(
        run_catchup_cycle,
        trigger,
        id="czds_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    # Graceful shutdown
    def _shutdown(signum, frame):
        logger.info(
            "Received signal %s. Finishing the current TLD before stopping the worker.",
            signum,
        )
        STOP_EVENT.set()
        if scheduler.running:
            scheduler.shutdown(wait=False)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("Scheduler started. Waiting for next trigger…")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler interrupted, exiting.")
        raise


if __name__ == "__main__":
    main()
