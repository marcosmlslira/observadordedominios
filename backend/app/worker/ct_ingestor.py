"""CT Logs Ingestor Worker — CertStream (real-time) + crt.sh (daily batch).

Entry point: python -m app.worker.ct_ingestor

Architecture:
- Main thread: CertStream WebSocket (blocking)
- Daemon thread: Buffer flush loop
- BackgroundScheduler: crt.sh daily cron (Phase 3)
"""

from __future__ import annotations

import logging
import signal
import threading
import time
import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.services.tld_coverage import resolve_certstream_suffixes
from app.services.use_cases.ingest_ct_batch import ingest_ct_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ct_ingestor")

_active_crtsh_cron: str = settings.CT_CRTSH_SYNC_CRON
_crtsh_scheduler_ref = None  # set to BackgroundScheduler in main()


def _extract_tld(domain: str) -> str:
    """Extract the TLD (last label) from a domain name."""
    parts = domain.rsplit(".", 1)
    return parts[-1].lower() if len(parts) > 1 else domain.lower()


def _is_tld_enabled_certstream(tld: str) -> bool:
    """
    Check if a TLD is enabled for CertStream ingestion.
    Auto-creates the row with is_enabled=True if it doesn't exist yet.
    """
    db = SessionLocal()
    try:
        from app.repositories.ingestion_config_repository import IngestionConfigRepository
        repo = IngestionConfigRepository(db)
        policy = repo.get_tld_policy("certstream", tld)
        if policy is None:
            repo.ensure_tld("certstream", tld, is_enabled=True)
            db.commit()
            return True
        return policy.is_enabled
    except Exception:
        logger.exception("TLD policy check failed for tld=%s, allowing through", tld)
        return True
    finally:
        db.close()


def _reload_crtsh_cron_if_changed() -> None:
    global _active_crtsh_cron
    if _crtsh_scheduler_ref is None or not _crtsh_scheduler_ref.running:
        return
    db = SessionLocal()
    try:
        from app.repositories.ingestion_config_repository import IngestionConfigRepository
        from apscheduler.triggers.cron import CronTrigger
        repo = IngestionConfigRepository(db)
        db_cron = repo.get_cron("certstream") or settings.CT_CRTSH_SYNC_CRON
        if db_cron != _active_crtsh_cron:
            parts = db_cron.split()
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1], day=parts[2],
                month=parts[3], day_of_week=parts[4],
            )
            _crtsh_scheduler_ref.reschedule_job("crtsh_sync", trigger=trigger)
            logger.info("crtsh cron updated: %s → %s", _active_crtsh_cron, db_cron)
            _active_crtsh_cron = db_cron
    except Exception:
        logger.exception("Failed to reload crtsh cron from DB")
    finally:
        db.close()


# ── CTBuffer ─────────────────────────────────────────────────


class CTBuffer:
    """Thread-safe in-memory buffer for domain names with dedup.

    Collects domains from CertStream callbacks and flushes in batches
    to reduce DB write frequency.
    """

    def __init__(
        self,
        flush_size: int = 5000,
        flush_interval_seconds: int = 30,
    ) -> None:
        self._buffer: set[str] = set()
        self._lock = threading.Lock()
        self._last_flush = time.time()
        self.flush_size = flush_size
        self.flush_interval_seconds = flush_interval_seconds

    def add(self, domains: list[str]) -> None:
        with self._lock:
            self._buffer.update(domains)

    def should_flush(self) -> bool:
        return (
            len(self._buffer) >= self.flush_size
            or (
                len(self._buffer) > 0
                and time.time() - self._last_flush >= self.flush_interval_seconds
            )
        )

    def drain(self) -> list[str]:
        with self._lock:
            items = list(self._buffer)
            self._buffer.clear()
            self._last_flush = time.time()
            return items

    @property
    def size(self) -> int:
        return len(self._buffer)


# ── Flush loop ───────────────────────────────────────────────


def _flush_loop(
    buffer: CTBuffer,
    run_id: uuid.UUID,
    stop_event: threading.Event,
) -> None:
    """Daemon thread that periodically flushes the buffer to DB.

    Creates its own DB session per flush (thread safety).
    """
    logger.info("Flush loop started (size=%d, interval=%ds)",
                buffer.flush_size, buffer.flush_interval_seconds)

    while not stop_event.is_set():
        stop_event.wait(timeout=2)  # Check every 2 seconds

        if not buffer.should_flush():
            continue

        domains = buffer.drain()
        if not domains:
            continue

        # Filter to enabled TLDs only
        filtered = [d for d in domains if _is_tld_enabled_certstream(_extract_tld(d))]
        if not filtered:
            logger.debug("All %d domains filtered out by TLD policy", len(domains))
            continue
        domains = filtered

        db = SessionLocal()
        try:
            metrics = ingest_ct_batch(
                db, domains, source="certstream", run_id=run_id,
            )
            db.commit()
            logger.info(
                "Flushed %d domains: inserted=%d by_tld=%s",
                len(domains),
                metrics["domains_inserted"],
                metrics["by_tld"],
            )
        except Exception:
            logger.exception("Flush failed for %d domains", len(domains))
            db.rollback()
        finally:
            db.close()

    # Final flush on shutdown
    domains = buffer.drain()
    if domains:
        domains = [d for d in domains if _is_tld_enabled_certstream(_extract_tld(d))]
    if domains:
        db = SessionLocal()
        try:
            ingest_ct_batch(db, domains, source="certstream", run_id=run_id)
            db.commit()
            logger.info("Final flush: %d domains", len(domains))
        except Exception:
            logger.exception("Final flush failed")
            db.rollback()
        finally:
            db.close()

    logger.info("Flush loop stopped.")


# ── Ingestion run management ─────────────────────────────────


def _create_daily_run(run_tld: str) -> uuid.UUID:
    """Create an ingestion_run for the current CertStream session."""
    db = SessionLocal()
    try:
        run_repo = IngestionRunRepository(db)
        run = run_repo.create_run(source="certstream", tld=run_tld)
        db.commit()
        logger.info("Created CertStream ingestion run: %s (%s)", run.id, run_tld)
        return run.id
    finally:
        db.close()


def _finalize_run(run_id: uuid.UUID, run_tld: str) -> None:
    """Finalize the CertStream ingestion run on shutdown."""
    db = SessionLocal()
    try:
        run_repo = IngestionRunRepository(db)
        run = run_repo.get_run(run_id)
        if run and run.status == "running":
            run_repo.finish_run(run, status="success")
            run_repo.upsert_checkpoint("certstream", run_tld, run)
            db.commit()
            logger.info(
                "Finalized CertStream run %s: seen=%s inserted=%s",
                run.id, run.domains_seen, run.domains_inserted,
            )
    except Exception:
        logger.exception("Failed to finalize CertStream run %s", run_id)
        db.rollback()
    finally:
        db.close()


def _recover_orphaned_certstream_runs() -> int:
    """Fail leftover CertStream runs before creating a new live session."""
    db = SessionLocal()
    try:
        run_repo = IngestionRunRepository(db)
        recovered = run_repo.mark_running_source_runs_failed(
            "certstream",
            error_message=(
                "Marked as failed on worker startup because a previous "
                "CertStream session did not finalize cleanly"
            ),
        )
        if recovered:
            db.commit()
            logger.warning(
                "Recovered %d orphaned CertStream run(s) before startup.",
                len(recovered),
            )
        return len(recovered)
    except Exception:
        logger.exception("Failed to recover orphaned CertStream runs")
        db.rollback()
        raise
    finally:
        db.close()


# ── Main ─────────────────────────────────────────────────────


def main() -> None:
    logger.info("CT Ingestor Worker starting...")

    # 2. Recover orphaned runs from previous worker sessions
    _recover_orphaned_certstream_runs()

    db = SessionLocal()
    try:
        certstream_suffixes = resolve_certstream_suffixes(db)
    finally:
        db.close()
    run_tld = "multi" if len(certstream_suffixes) > 1 else certstream_suffixes[0].lstrip(".")

    logger.info("Resolved CertStream suffixes: %s", certstream_suffixes)

    # 3. Create daily ingestion run
    run_id = _create_daily_run(run_tld)

    # 4. Initialize buffer
    buffer = CTBuffer(
        flush_size=settings.CT_BUFFER_FLUSH_SIZE,
        flush_interval_seconds=settings.CT_BUFFER_FLUSH_SECONDS,
    )

    # 5. Stop event for graceful shutdown
    stop_event = threading.Event()
    shutdown_requested = threading.Event()

    # 6. Start crt.sh scheduler if enabled (BackgroundScheduler)
    scheduler = None
    if settings.CT_CRTSH_ENABLED:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger

            from app.services.use_cases.sync_crtsh import run_crtsh_sync

            scheduler = BackgroundScheduler()
            global _crtsh_scheduler_ref
            _crtsh_scheduler_ref = scheduler
            cron_parts = settings.CT_CRTSH_SYNC_CRON.split()
            trigger = CronTrigger(
                minute=cron_parts[0] if len(cron_parts) > 0 else "0",
                hour=cron_parts[1] if len(cron_parts) > 1 else "*",
                day=cron_parts[2] if len(cron_parts) > 2 else "*",
                month=cron_parts[3] if len(cron_parts) > 3 else "*",
                day_of_week=cron_parts[4] if len(cron_parts) > 4 else "*",
            )
            def _run_crtsh():
                _reload_crtsh_cron_if_changed()
                run_crtsh_sync()

            scheduler.add_job(
                _run_crtsh, trigger,
                id="crtsh_sync", replace_existing=True,
            )
            scheduler.start()
            job = scheduler.get_job("crtsh_sync")
            next_run = job.next_run_time.isoformat() if job and job.next_run_time else None
            logger.info(
                "crt.sh scheduler started: cron=%s next_run=%s",
                settings.CT_CRTSH_SYNC_CRON,
                next_run or "pending",
            )
            logger.info("crt.sh is cron-only in production. No startup backfill will run.")
        except ImportError:
            logger.warning("sync_crtsh not yet implemented, skipping crt.sh scheduler")
        except Exception:
            logger.exception("Failed to start crt.sh scheduler")

    # 7. Start flush loop (daemon thread)
    flush_thread = threading.Thread(
        target=_flush_loop,
        args=(buffer, run_id, stop_event),
        daemon=True,
        name="ct-flush",
    )
    flush_thread.start()

    # 8. Initialize CertStream client ref BEFORE signal handler
    certstream_client = None

    # 9. Graceful shutdown handler
    def _shutdown(signum, frame):
        logger.info("Received signal %s, draining CertStream session before exit...", signum)
        shutdown_requested.set()
        stop_event.set()
        if scheduler:
            scheduler.shutdown(wait=False)
        if certstream_client:
            certstream_client.stop()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # 10. Start CertStream (blocks main thread)
    try:
        if settings.CT_CERTSTREAM_ENABLED:
            from app.infra.external.certstream_client import CertStreamClient

            certstream_client = CertStreamClient(
                on_domains_callback=buffer.add,
                filter_suffixes=certstream_suffixes,
            )
            logger.info("Starting CertStream client...")
            certstream_client.start()  # Blocks until stop() is called
        else:
            logger.info("CertStream disabled. Worker running crt.sh scheduler only.")
            stop_event.wait()
    finally:
        stop_event.set()
        flush_thread.join()
        _finalize_run(run_id, run_tld)
        if shutdown_requested.is_set():
            logger.info("CT Ingestor Worker stopped after graceful drain.")
        else:
            logger.info("CT Ingestor Worker stopped.")


if __name__ == "__main__":
    main()
