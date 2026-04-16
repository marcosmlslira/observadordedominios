"""CZDS Ingestor Worker — scheduled execution of zone file syncs.

Parallel processing: small TLDs (<1M domains) run concurrently via ThreadPoolExecutor.
Large TLDs run serially to avoid memory contention.
"""

from __future__ import annotations

import logging
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from sqlalchemy import text

from app.core.config import settings
from app.infra.external.czds_client import CZDSAuthRateLimitedError, CZDSClient
from app.infra.db.session import SessionLocal
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.services.tld_domain_count import refresh_tld_domain_count_mv
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

_active_cron: str = settings.CZDS_SYNC_CRON
_scheduler_ref = None  # set to BlockingScheduler in main()


def _shutdown(signum, frame) -> None:
    """SIGTERM/SIGINT handler — stops after the current TLD finishes.

    Registered at the very start of main() so Docker stop_grace_period works
    even during the initial multi-hour catchup cycle.
    """
    logger.info(
        "Received signal %s. Finishing current TLD before stopping.",
        signum,
    )
    STOP_EVENT.set()
    if _scheduler_ref is not None and _scheduler_ref.running:
        _scheduler_ref.shutdown(wait=False)

_SIZE_THRESHOLD = 1_000_000  # TLDs abaixo deste valor rodam em paralelo
_PARALLEL_WORKERS = 4


def _reload_cron_if_changed() -> None:
    """Check DB for updated cron; reschedule APScheduler job if it changed."""
    global _active_cron
    if _scheduler_ref is None or not _scheduler_ref.running:
        return
    db = SessionLocal()
    try:
        from app.repositories.ingestion_config_repository import IngestionConfigRepository
        repo = IngestionConfigRepository(db)
        db_cron = repo.get_cron("czds") or settings.CZDS_SYNC_CRON
        if db_cron != _active_cron:
            parts = db_cron.split()
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1], day=parts[2],
                month=parts[3], day_of_week=parts[4],
            )
            _scheduler_ref.reschedule_job("czds_sync", trigger=trigger)
            logger.info("CZDS cron updated: %s → %s", _active_cron, db_cron)
            _active_cron = db_cron
    except Exception:
        logger.exception("Failed to reload CZDS cron from DB")
    finally:
        db.close()


def _wait_or_stop(seconds: int) -> bool:
    """Sleep in an interruptible way. Returns True when a stop was requested."""
    return STOP_EVENT.wait(seconds)


def _get_enabled_tlds() -> list[str]:
    """
    Read enabled TLDs from the admin UI configuration (czds_tld_policy), ordered
    by the ordering_mode configured for the czds source.

    Modes:
      corpus_first   — smallest corpus first (default, preserves current behaviour)
      priority_first — explicit priority column first, then corpus size
      alphabetical   — TLD name ASC

    Returns an empty list if the DB is unavailable — never falls back to hardcoded
    lists so the admin UI remains the single source of truth.
    """
    _ORDER_BY = {
        "corpus_first":   "COALESCE(m.count, 999999999) ASC, p.priority ASC, p.tld ASC",
        "priority_first": "p.priority ASC, COALESCE(m.count, 999999999) ASC, p.tld ASC",
        "alphabetical":   "p.tld ASC",
    }

    db = SessionLocal()
    try:
        from app.repositories.ingestion_config_repository import IngestionConfigRepository
        cfg = IngestionConfigRepository(db).get_config("czds")
        ordering_mode = (cfg.ordering_mode if cfg else None) or "corpus_first"
        order_clause = _ORDER_BY.get(ordering_mode, _ORDER_BY["corpus_first"])

        result = db.execute(text(f"""
            SELECT p.tld
            FROM czds_tld_policy p
            LEFT JOIN tld_domain_count_mv m ON p.tld = m.tld
            LEFT JOIN ingestion_tld_policy itp
                   ON itp.source = 'czds' AND itp.tld = p.tld
            WHERE COALESCE(itp.is_enabled, p.is_enabled) = true
            ORDER BY {order_clause}
        """))
        return [row[0] for row in result]
    except Exception:
        logger.warning("Could not read czds_tld_policy from DB; skipping cycle.")
        return []
    finally:
        db.close()


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


def _get_tld_sizes() -> dict[str, int]:
    """Query domain counts per TLD from the materialized view."""
    db = SessionLocal()
    try:
        result = db.execute(text("SELECT tld, count FROM tld_domain_count_mv"))
        return {row[0]: row[1] for row in result}
    except Exception:
        logger.warning("Could not read tld_domain_count_mv for size classification.")
        return {}
    finally:
        db.close()


def _sync_single_tld(tld: str, czds_client: CZDSClient | None = None) -> None:
    """Sync one TLD with its own DB session. Re-raises CZDSAuthRateLimitedError."""
    db = SessionLocal()
    try:
        logger.info("▶ Syncing TLD=%s", tld)
        run_id = sync_czds_tld(db, tld, czds_client=czds_client)
        logger.info("✅ TLD=%s completed: run_id=%s", tld, run_id)
    except CooldownActiveError:
        logger.info("⏭ TLD=%s skipped (cooldown active)", tld)
    except TldSuspendedError as exc:
        logger.info("⏭ TLD=%s skipped (%s)", tld, exc)
    except SyncAlreadyRunningError:
        logger.warning("⏭ TLD=%s skipped (already running)", tld)
    except CZDSAuthRateLimitedError:
        raise
    except Exception:
        logger.exception("❌ TLD=%s failed", tld)
    finally:
        db.close()


def _recover_stale_at_cycle_start() -> None:
    """Mark orphaned running CZDS runs as failed before starting a new cycle."""
    db = SessionLocal()
    try:
        from app.repositories.ingestion_run_repository import IngestionRunRepository
        run_repo = IngestionRunRepository(db)
        stale = run_repo.recover_all_stale_for_source(
            "czds", stale_after_minutes=settings.CZDS_RUNNING_STALE_MINUTES
        )
        if stale:
            db.commit()
            logger.info(
                "Recovered %d stale CZDS run(s) at cycle start: %s",
                len(stale),
                [r.tld for r in stale],
            )
    except Exception:
        logger.warning("Could not recover stale CZDS runs", exc_info=True)
    finally:
        db.close()


def run_sync_cycle(tlds: list[str] | None = None) -> None:
    """Execute a sync cycle: small TLDs in parallel, large TLDs serially.

    A single CZDSClient is shared across the entire cycle so the ICANN JWT
    is obtained once and reused, avoiding authentication rate limits (HTTP 429).
    """
    _recover_stale_at_cycle_start()
    _reload_cron_if_changed()
    tlds = tlds or _get_enabled_tlds()
    logger.info("Starting sync cycle for TLDs: %s", tlds)

    # One shared client for the whole cycle — authenticates once, reuses token
    czds_client = CZDSClient()

    sizes = _get_tld_sizes()
    small_tlds = [t for t in tlds if sizes.get(t, _SIZE_THRESHOLD) < _SIZE_THRESHOLD]
    large_tlds = [t for t in tlds if sizes.get(t, _SIZE_THRESHOLD) >= _SIZE_THRESHOLD]
    logger.info(
        "TLD split: %d small (parallel, max_workers=%d), %d large (serial)",
        len(small_tlds), _PARALLEL_WORKERS, len(large_tlds),
    )

    # ── Small TLDs in parallel ────────────────────────────────────────────────
    if small_tlds and not STOP_EVENT.is_set():
        auth_throttled = False
        with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as pool:
            futures = {
                pool.submit(_sync_single_tld, tld, czds_client): tld
                for tld in small_tlds
                if not STOP_EVENT.is_set()
            }
            for future in as_completed(futures):
                tld = futures[future]
                try:
                    future.result()
                except CZDSAuthRateLimitedError:
                    logger.warning(
                        "CZDS auth throttled during parallel sync of TLD=%s. "
                        "Waiting %d seconds.",
                        tld, settings.CZDS_AUTH_RATE_LIMIT_BACKOFF_SECONDS,
                    )
                    auth_throttled = True
                except Exception:
                    logger.exception("❌ TLD=%s failed (parallel)", tld)

        if auth_throttled:
            _wait_or_stop(settings.CZDS_AUTH_RATE_LIMIT_BACKOFF_SECONDS)
            logger.info("Sync cycle aborted after auth throttle.")
            return

    # ── Large TLDs serially ───────────────────────────────────────────────────
    for tld in large_tlds:
        if STOP_EVENT.is_set():
            logger.info("Stop requested. Ending sync cycle before TLD=%s.", tld)
            break
        db = SessionLocal()
        try:
            logger.info("▶ Syncing TLD=%s", tld)
            run_id = sync_czds_tld(db, tld, czds_client=czds_client)
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
    """Run the normal cycle, backfill missing TLDs, then refresh snapshot."""
    run_sync_cycle()
    if not STOP_EVENT.is_set():
        run_bootstrap_until_complete()
    if not STOP_EVENT.is_set():
        refresh_tld_domain_count_mv()


def main() -> None:
    # Register signal handlers BEFORE the initial sync so Docker stop_grace_period
    # works even if the container receives SIGTERM during the multi-hour catchup cycle.
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("CZDS Ingestor Worker starting…")
    logger.info("Cron schedule: %s", settings.CZDS_SYNC_CRON)

    # Run initial sync on startup
    logger.info("Running initial sync cycle…")
    run_catchup_cycle()

    if STOP_EVENT.is_set():
        logger.info("Stop requested during startup catch-up. Exiting worker.")
        return

    # Schedule recurring syncs
    global _scheduler_ref
    scheduler = BlockingScheduler()
    _scheduler_ref = scheduler
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

    logger.info("Scheduler started. Waiting for next trigger…")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler interrupted, exiting.")
        raise


if __name__ == "__main__":
    main()
