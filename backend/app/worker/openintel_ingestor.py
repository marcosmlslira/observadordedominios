"""OpenINTEL Ingestor Worker — daily scheduled sync of ccTLD apex-domain snapshots.

Runs serially (one TLD at a time) to stay within S3 streaming bandwidth and
avoid contention on the advisory locks. Much lighter than CZDS: no downloads,
no S3 uploads, just Parquet streaming.
"""

from __future__ import annotations

import logging
import signal
import threading

from sqlalchemy import text
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.repositories.domain_repository import ensure_partition
from app.repositories.ingestion_run_repository import IngestionRunRepository
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
_active_cron: str = settings.OPENINTEL_SYNC_CRON
_scheduler_ref: BlockingScheduler | None = None


def _get_enabled_tlds() -> list[str]:
    """Read enabled TLDs from DB; fall back to env if table is empty."""
    db = SessionLocal()
    try:
        from app.repositories.ingestion_config_repository import IngestionConfigRepository
        repo = IngestionConfigRepository(db)
        db_tlds = repo.list_enabled_tlds("openintel")
        if db_tlds:
            return db_tlds
    except Exception:
        logger.exception("Failed to read OpenINTEL TLDs from DB, falling back to env")
    finally:
        db.close()
    raw = settings.OPENINTEL_ENABLED_TLDS
    if not raw:
        return []
    return [t.strip().lower() for t in raw.split(",") if t.strip()]


def _reload_cron_if_changed() -> None:
    """Check DB for updated cron; reschedule APScheduler job if it changed."""
    global _active_cron
    if _scheduler_ref is None or not _scheduler_ref.running:
        return
    db = SessionLocal()
    try:
        from app.repositories.ingestion_config_repository import IngestionConfigRepository
        repo = IngestionConfigRepository(db)
        db_cron = repo.get_cron("openintel") or settings.OPENINTEL_SYNC_CRON
        if db_cron != _active_cron:
            parts = db_cron.split()
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1], day=parts[2],
                month=parts[3], day_of_week=parts[4],
            )
            _scheduler_ref.reschedule_job("openintel_sync", trigger=trigger)
            logger.info("Cron updated: %s → %s", _active_cron, db_cron)
            _active_cron = db_cron
    except Exception:
        logger.exception("Failed to reload cron from DB")
    finally:
        db.close()


def _prewarm_all_partitions(tlds: list[str]) -> None:
    """Pre-create domain table partitions for all configured TLDs.

    Running DDL (CREATE TABLE ... PARTITION OF) during the ingest hot-path
    requires ACCESS EXCLUSIVE on the parent domain table, which blocks concurrent
    INSERT batches from other workers. By creating all partitions at startup —
    before any ingest cycle begins — ensure_partition() becomes a no-op during
    the hot-path, eliminating the DDL/DML lock contention entirely.
    """
    if not tlds:
        return
    db = SessionLocal()
    try:
        created = 0
        for tld in tlds:
            try:
                before = db.execute(
                    text("SELECT 1 FROM pg_class WHERE relname = :n"),
                    {"n": f"domain_{tld.replace('-', '_').replace('.', '_')}"},
                ).scalar()
                if not before:
                    ensure_partition(db, tld)
                    created += 1
            except Exception:
                logger.warning("Could not pre-create partition for TLD=%s", tld, exc_info=True)
        if created:
            logger.info("Pre-created %d new partition(s) at startup.", created)
        else:
            logger.info("All %d TLD partitions already exist.", len(tlds))
    finally:
        db.close()


def _recover_stale_at_cycle_start() -> None:
    """Mark orphaned running OpenINTEL runs as failed before starting a new cycle."""
    db = SessionLocal()
    try:
        run_repo = IngestionRunRepository(db)
        stale = run_repo.recover_all_stale_for_source(
            "openintel", stale_after_minutes=settings.OPENINTEL_RUNNING_STALE_MINUTES
        )
        if stale:
            db.commit()
            logger.warning(
                "Recovered %d stale OpenINTEL run(s) at cycle start: %s",
                len(stale),
                [r.tld for r in stale],
            )
    except Exception:
        logger.warning("Could not recover stale OpenINTEL runs", exc_info=True)
    finally:
        db.close()


def run_sync_cycle() -> None:
    """Sync all enabled TLDs serially.

    Aborts the entire cycle if CZDS is detected as running (shared partition
    conflict). Skips individual TLDs on cooldown, already-ingested snapshots,
    or missing S3 data — without failing the cycle.
    """
    _recover_stale_at_cycle_start()
    _reload_cron_if_changed()
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


def _shutdown(signum, frame) -> None:
    """SIGTERM/SIGINT handler — stops after the current TLD finishes."""
    logger.info(
        "Received signal %s. Finishing current TLD before stopping.",
        signum,
    )
    STOP_EVENT.set()
    if _scheduler_ref is not None and _scheduler_ref.running:
        _scheduler_ref.shutdown(wait=False)


def main() -> None:
    # Register signal handlers before the initial sync so Docker stop_grace_period works.
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("OpenINTEL Ingestor Worker starting…")
    logger.info("Cron schedule: %s", settings.OPENINTEL_SYNC_CRON)

    # Pre-create all TLD partitions so ensure_partition() is a no-op during
    # the hot-path and can never block concurrent INSERT batches from other workers.
    _prewarm_all_partitions(_get_enabled_tlds())

    logger.info("Running initial sync cycle…")
    run_sync_cycle()

    if STOP_EVENT.is_set():
        logger.info("Stop requested during startup. Exiting worker.")
        return

    global _scheduler_ref
    scheduler = BlockingScheduler()
    _scheduler_ref = scheduler
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

    logger.info("Scheduler started. Waiting for next trigger…")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler interrupted, exiting.")
        raise


if __name__ == "__main__":
    main()
