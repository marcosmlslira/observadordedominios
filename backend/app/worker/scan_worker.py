"""Scan Worker — daily similarity scan with monitoring cycle integration.

Scheduled at 09:00 UTC. Wraps run_similarity_scan_all, registers progress
in monitoring_cycle, and computes enrichment_budget_rank after scanning.
Also drains manual queued scan jobs every 15 seconds.
"""
from __future__ import annotations

import logging
import signal
import sys
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.repositories.monitored_brand_repository import MonitoredBrandRepository
from app.repositories.monitoring_cycle_repository import MonitoringCycleRepository
from app.repositories.similarity_repository import SimilarityRepository
from app.services.monitoring_cycle_service import MonitoringCycleService
from app.services.use_cases.run_similarity_scan import run_similarity_scan_all, run_similarity_scan_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scan_worker")

SCAN_CRON = settings.SIMILARITY_SCAN_CRON

_consecutive_cycle_failures = 0
_last_cycle_completed_at: datetime | None = None


def run_scan_cycle(db: Session | None = None) -> None:
    """Scan all active brands and compute enrichment budget ranks."""
    global _consecutive_cycle_failures, _last_cycle_completed_at

    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    try:
        brand_repo = MonitoredBrandRepository(db)
        brands = brand_repo.list_active()

        if not brands:
            logger.info("No active brands to scan.")
            return

        logger.info("Starting scan cycle for %d brands", len(brands))

        for brand in brands:
            try:
                cycle_repo = MonitoringCycleRepository(db)
                cycle, created = cycle_repo.get_or_create_today(
                    brand_id=brand.id,
                    organization_id=brand.organization_id,
                )
                if created:
                    db.commit()

                if cycle.scan_status == "completed":
                    logger.info(
                        "Scan already completed for brand=%s today", brand.brand_name
                    )
                    continue

                svc = MonitoringCycleService(db, cycle_repo=cycle_repo)
                svc.begin_stage(cycle.id, stage="scan")
                db.commit()

                logger.info("Scanning brand=%s", brand.brand_name)
                results = run_similarity_scan_all(db, brand)

                total_matched = sum(r.get("matched", 0) for r in results.values())
                total_candidates = sum(r.get("candidates", 0) for r in results.values())

                sim_repo = SimilarityRepository(db)
                ranked = sim_repo.compute_enrichment_budget_rank(brand.id, limit=50)

                svc.finish_stage(cycle.id, stage="scan", success=True)
                db.commit()

                logger.info(
                    "Scan complete: brand=%s candidates=%d matched=%d ranked=%d",
                    brand.brand_name, total_candidates, total_matched, ranked,
                )

            except Exception:
                db.rollback()
                logger.exception("Scan failed for brand=%s", brand.brand_name)

        _last_cycle_completed_at = datetime.now(timezone.utc)
        _consecutive_cycle_failures = 0

    except Exception:
        _consecutive_cycle_failures += 1
        logger.exception(
            "Scan cycle failed (consecutive=%d)", _consecutive_cycle_failures
        )
    finally:
        if owns_session:
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
            logger.info("Processing queued job=%s brand=%s", job.id, job.brand_id)
            try:
                run_similarity_scan_job(db, job.id)
            except Exception:
                logger.exception("Queued job failed: %s", job.id)
            processed += 1
    finally:
        db.close()


def emit_heartbeat() -> None:
    last_ok = _last_cycle_completed_at.isoformat() if _last_cycle_completed_at else "never"
    logger.info(
        "[HEARTBEAT] scan_worker alive last_cycle=%s consecutive_failures=%d",
        last_ok, _consecutive_cycle_failures,
    )


def main() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    logger.info("Scan Worker starting. Cron: %s", SCAN_CRON)
    run_scan_cycle()

    scheduler = BlockingScheduler()
    cron_parts = SCAN_CRON.split()
    scheduler.add_job(
        run_scan_cycle,
        CronTrigger(
            minute=cron_parts[0], hour=cron_parts[1],
            day=cron_parts[2], month=cron_parts[3], day_of_week=cron_parts[4],
        ),
        id="similarity_scan",
        replace_existing=True,
    )
    scheduler.add_job(
        run_queued_jobs_cycle,
        IntervalTrigger(seconds=15),
        id="queued_jobs",
        replace_existing=True,
    )
    scheduler.add_job(
        emit_heartbeat,
        IntervalTrigger(minutes=5),
        id="scan_heartbeat",
        replace_existing=True,
    )

    def _shutdown(signum, frame):
        logger.info("Shutting down scan_worker...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    scheduler.start()


if __name__ == "__main__":
    main()
