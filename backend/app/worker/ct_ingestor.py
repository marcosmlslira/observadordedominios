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
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.repositories.domain_repository import ensure_partition
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.services.use_cases.ingest_ct_batch import ingest_ct_batch

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ct_ingestor")


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


# ── Partition setup ──────────────────────────────────────────


def _ensure_br_partitions() -> None:
    """Ensure all configured .br TLD partitions exist."""
    subtlds = [t.strip() for t in settings.CT_BR_SUBTLDS.split(",") if t.strip()]
    db = SessionLocal()
    try:
        for tld in subtlds:
            ensure_partition(db, tld)
        logger.info("Ensured %d .br partitions: %s", len(subtlds), subtlds)
    finally:
        db.close()


# ── Ingestion run management ─────────────────────────────────


def _create_daily_run() -> uuid.UUID:
    """Create an ingestion_run for the current CertStream session."""
    db = SessionLocal()
    try:
        run_repo = IngestionRunRepository(db)
        run = run_repo.create_run(source="certstream", tld="br")
        db.commit()
        logger.info("Created CertStream ingestion run: %s", run.id)
        return run.id
    finally:
        db.close()


def _finalize_run(run_id: uuid.UUID) -> None:
    """Finalize the CertStream ingestion run on shutdown."""
    db = SessionLocal()
    try:
        run_repo = IngestionRunRepository(db)
        run = run_repo.get_run(run_id)
        if run and run.status == "running":
            run_repo.finish_run(run, status="success")
            run_repo.upsert_checkpoint("certstream", "br", run)
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


# ── Main ─────────────────────────────────────────────────────


def main() -> None:
    logger.info("CT Ingestor Worker starting...")

    # 1. Ensure .br partitions
    _ensure_br_partitions()

    # 2. Create daily ingestion run
    run_id = _create_daily_run()

    # 3. Initialize buffer
    buffer = CTBuffer(
        flush_size=settings.CT_BUFFER_FLUSH_SIZE,
        flush_interval_seconds=settings.CT_BUFFER_FLUSH_SECONDS,
    )

    # 4. Stop event for graceful shutdown
    stop_event = threading.Event()

    # 5. Start crt.sh scheduler if enabled (BackgroundScheduler)
    scheduler = None
    if settings.CT_CRTSH_ENABLED:
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.cron import CronTrigger

            from app.services.use_cases.sync_crtsh import run_crtsh_sync

            scheduler = BackgroundScheduler()
            cron_parts = settings.CT_CRTSH_SYNC_CRON.split()
            trigger = CronTrigger(
                minute=cron_parts[0] if len(cron_parts) > 0 else "0",
                hour=cron_parts[1] if len(cron_parts) > 1 else "*",
                day=cron_parts[2] if len(cron_parts) > 2 else "*",
                month=cron_parts[3] if len(cron_parts) > 3 else "*",
                day_of_week=cron_parts[4] if len(cron_parts) > 4 else "*",
            )
            scheduler.add_job(
                run_crtsh_sync, trigger,
                id="crtsh_sync", replace_existing=True,
            )
            scheduler.start()
            logger.info("crt.sh scheduler started: cron=%s", settings.CT_CRTSH_SYNC_CRON)
        except ImportError:
            logger.warning("sync_crtsh not yet implemented, skipping crt.sh scheduler")
        except Exception:
            logger.exception("Failed to start crt.sh scheduler")

    # 6. Start flush loop (daemon thread)
    flush_thread = threading.Thread(
        target=_flush_loop,
        args=(buffer, run_id, stop_event),
        daemon=True,
        name="ct-flush",
    )
    flush_thread.start()

    # 7. Initialize CertStream client ref BEFORE signal handler (avoids UnboundLocalError)
    certstream_client = None

    # 8. Graceful shutdown handler
    def _shutdown(signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        stop_event.set()
        if scheduler:
            scheduler.shutdown(wait=False)
        if certstream_client:
            certstream_client.stop()
        # Wait for flush thread to finish final flush
        flush_thread.join(timeout=10)
        # Finalize the CertStream ingestion run
        _finalize_run(run_id)
        logger.info("CT Ingestor Worker stopped.")
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    # 9. Start CertStream (blocks main thread)
    if settings.CT_CERTSTREAM_ENABLED:
        from app.infra.external.certstream_client import CertStreamClient

        certstream_client = CertStreamClient(
            on_domains_callback=buffer.add,
            filter_suffix=".br",
        )
        logger.info("Starting CertStream client...")
        certstream_client.start()  # Blocks until stop() is called
    else:
        logger.info("CertStream disabled. Worker running crt.sh scheduler only.")
        stop_event.wait()


if __name__ == "__main__":
    main()
