"""Similarity Worker — scheduled scanning of monitored brands against domain table.

Runs after CZDS ingestion completes or on its own cron schedule.
Processes all active brands across all TLD partitions.
"""

from __future__ import annotations

import logging
import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.repositories.monitored_brand_repository import MonitoredBrandRepository
from app.repositories.similarity_repository import SimilarityRepository
from app.services.use_cases.run_similarity_scan import run_similarity_scan_all, run_similarity_scan_job
from app.services.use_cases.sync_monitoring_profile import ensure_monitoring_profile_integrity

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("similarity_worker")

# Default: run at 09:00 daily (2 hours after CZDS sync at 07:00)
SIMILARITY_CRON = settings.SIMILARITY_SCAN_CRON


def run_scan_cycle() -> None:
    """Scan all active brands across all TLDs."""
    db = SessionLocal()
    try:
        repo = MonitoredBrandRepository(db)
        brands = repo.list_active()

        if not brands:
            logger.info("No active brands to scan.")
            return

        logger.info("Starting similarity scan cycle for %d brands", len(brands))

        for brand in brands:
            ensure_monitoring_profile_integrity(repo, brand)
            db.commit()
            logger.info("Scanning brand=%s (label=%s)", brand.brand_name, brand.brand_label)
            try:
                results = run_similarity_scan_all(db, brand)
                total_matched = sum(r.get("matched", 0) for r in results.values())
                total_candidates = sum(r.get("candidates", 0) for r in results.values())
                logger.info(
                    "Brand=%s complete: %d TLDs, %d candidates, %d matches",
                    brand.brand_name, len(results), total_candidates, total_matched,
                )
            except Exception:
                logger.exception("Failed scanning brand=%s", brand.brand_name)

        logger.info("Similarity scan cycle finished.")
    finally:
        db.close()


def run_queued_jobs_cycle() -> None:
    """Drain queued manual scan jobs created by the API."""
    db = SessionLocal()
    try:
        repo = SimilarityRepository(db)
        processed = 0
        while processed < 5:
            job = repo.claim_next_queued_scan_job()
            if not job:
                break
            db.commit()
            logger.info("Processing queued similarity job=%s brand=%s", job.id, job.brand_id)
            try:
                run_similarity_scan_job(db, job.id)
            except Exception:
                logger.exception("Queued similarity job failed: %s", job.id)
            processed += 1
    finally:
        db.close()


def main() -> None:
    logger.info("Similarity Worker starting...")
    logger.info("Cron schedule: %s", SIMILARITY_CRON)

    # Run initial scan on startup
    logger.info("Running initial scan cycle...")
    run_scan_cycle()

    # Schedule recurring scans
    scheduler = BlockingScheduler()
    cron_parts = SIMILARITY_CRON.split()
    trigger = CronTrigger(
        minute=cron_parts[0] if len(cron_parts) > 0 else "0",
        hour=cron_parts[1] if len(cron_parts) > 1 else "*",
        day=cron_parts[2] if len(cron_parts) > 2 else "*",
        month=cron_parts[3] if len(cron_parts) > 3 else "*",
        day_of_week=cron_parts[4] if len(cron_parts) > 4 else "*",
    )
    scheduler.add_job(run_scan_cycle, trigger, id="similarity_scan", replace_existing=True)
    scheduler.add_job(
        run_queued_jobs_cycle,
        IntervalTrigger(seconds=15),
        id="similarity_scan_manual_jobs",
        replace_existing=True,
    )

    # Graceful shutdown
    def _shutdown(signum, frame):
        logger.info("Received signal %s, shutting down...", signum)
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    logger.info("Scheduler started. Waiting for next trigger...")
    scheduler.start()


if __name__ == "__main__":
    main()
