"""OpenINTEL Ingestor Worker — daily scheduled sync of ccTLD apex-domain snapshots.

Runs serially (one TLD at a time) to stay within S3 streaming bandwidth and
avoid contention on the advisory locks. Much lighter than CZDS: no downloads,
no S3 uploads, just Parquet streaming.
"""

from __future__ import annotations

import logging
import signal
import threading

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.services.use_cases.sync_openintel_tld import (
    CooldownActiveError,
    CzdsRunningError,
    SnapshotAlreadyIngestedError,
    SnapshotNotFoundError,
    SyncAlreadyRunningError,
    sync_openintel_tld,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("openintel_ingestor")
STOP_EVENT = threading.Event()


def _get_enabled_tlds() -> list[str]:
    raw = settings.OPENINTEL_ENABLED_TLDS
    if not raw:
        return []
    return [t.strip().lower() for t in raw.split(",") if t.strip()]


def run_sync_cycle() -> None:
    """Sync all enabled TLDs serially.

    Aborts the entire cycle if CZDS is detected as running (shared partition
    conflict). Skips individual TLDs on cooldown, already-ingested snapshots,
    or missing S3 data — without failing the cycle.
    """
    tlds = _get_enabled_tlds()
    if not tlds:
        logger.info("No OpenINTEL TLDs configured. Skipping cycle.")
        return

    logger.info("Starting OpenINTEL sync cycle for TLDs: %s", tlds)

    for tld in tlds:
        if STOP_EVENT.is_set():
            logger.info("Stop requested. Ending cycle before TLD=%s.", tld)
            break

        db = SessionLocal()
        try:
            logger.info("▶ Syncing TLD=%s", tld)
            run_id = sync_openintel_tld(db, tld)
            logger.info("✅ TLD=%s completed: run_id=%s", tld, run_id)

        except CzdsRunningError as exc:
            logger.warning(
                "⚠ CZDS is running — aborting entire OpenINTEL cycle. (%s)", exc
            )
            break

        except CooldownActiveError:
            logger.info("⏭ TLD=%s skipped (cooldown active)", tld)

        except SnapshotAlreadyIngestedError:
            logger.info("⏭ TLD=%s skipped (snapshot already ingested)", tld)

        except SnapshotNotFoundError:
            logger.info("⏭ TLD=%s skipped (no snapshot available)", tld)

        except SyncAlreadyRunningError:
            logger.warning("⏭ TLD=%s skipped (already running)", tld)

        except Exception:
            logger.exception("❌ TLD=%s failed", tld)

        finally:
            db.close()

    logger.info("OpenINTEL sync cycle finished.")


def main() -> None:
    logger.info("OpenINTEL Ingestor Worker starting…")
    logger.info("Cron schedule: %s", settings.OPENINTEL_SYNC_CRON)

    logger.info("Running initial sync cycle…")
    run_sync_cycle()

    if STOP_EVENT.is_set():
        logger.info("Stop requested during startup. Exiting worker.")
        return

    scheduler = BlockingScheduler()
    cron_parts = settings.OPENINTEL_SYNC_CRON.split()
    trigger = CronTrigger(
        minute=cron_parts[0] if len(cron_parts) > 0 else "0",
        hour=cron_parts[1] if len(cron_parts) > 1 else "2",
        day=cron_parts[2] if len(cron_parts) > 2 else "*",
        month=cron_parts[3] if len(cron_parts) > 3 else "*",
        day_of_week=cron_parts[4] if len(cron_parts) > 4 else "*",
    )
    scheduler.add_job(
        run_sync_cycle,
        trigger,
        id="openintel_sync",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    def _shutdown(signum, frame):
        logger.info(
            "Received signal %s. Finishing current TLD before stopping.",
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
