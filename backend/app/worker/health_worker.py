"""Health Worker — daily health check of official brand domains.

Scheduled at 06:00 UTC. Runs 10 monitoring tools per domain,
creates monitoring_event records, recalculates brand_domain_health.
"""
from __future__ import annotations

import logging
import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.repositories.monitored_brand_repository import MonitoredBrandRepository
from app.repositories.monitoring_cycle_repository import MonitoringCycleRepository
from app.services.monitoring_cycle_service import MonitoringCycleService
from app.services.use_cases.run_health_check_domain import run_health_check_domain

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("health_worker")

HEALTH_CRON = getattr(settings, "HEALTH_CHECK_CRON", "0 6 * * *")

_consecutive_cycle_failures = 0
_last_cycle_completed_at: datetime | None = None


def run_health_cycle(db: Session | None = None) -> None:
    """Run health checks for all active brands. Accepts optional db for testing."""
    global _consecutive_cycle_failures, _last_cycle_completed_at

    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    try:
        brand_repo = MonitoredBrandRepository(db)
        brands = brand_repo.list_active()

        if not brands:
            logger.info("No active brands for health check.")
            return

        logger.info("Starting health check cycle for %d brands", len(brands))

        for brand in brands:
            try:
                # Step 1: Get or create today's cycle for this brand
                cycle_repo = MonitoringCycleRepository(db)
                cycle, created = cycle_repo.get_or_create_today(
                    brand_id=brand.id,
                    organization_id=brand.organization_id,
                )
                if created:
                    db.commit()

                # Step 2: Idempotency — skip if health stage already completed today
                if cycle.health_status == "completed":
                    logger.info(
                        "Health check already completed for brand=%s today",
                        brand.brand_name,
                    )
                    continue

                # Step 3: Mark stage as running
                svc = MonitoringCycleService(db, cycle_repo=cycle_repo)
                svc.begin_stage(cycle.id, stage="health")
                db.commit()

                domains = [
                    d for d in (brand.domains or [])
                    if getattr(d, "is_active", True)
                ]
                domains_ok = 0
                domains_failed = 0

                for domain in domains:
                    try:
                        summary = run_health_check_domain(
                            db,
                            domain,
                            brand_id=brand.id,
                            organization_id=brand.organization_id,
                            cycle_id=cycle.id,
                        )
                        domains_ok += 1
                        logger.info(
                            "health_check brand=%s domain=%s status=%s tools_failed=%d",
                            brand.brand_name, domain.domain_name,
                            summary["overall_status"], summary["tools_failed"],
                        )
                    except Exception:
                        domains_failed += 1
                        logger.exception(
                            "health_check FAILED brand=%s domain=%s",
                            brand.brand_name, domain.domain_name,
                        )

                # Step 4: Mark stage complete
                svc.finish_stage(cycle.id, stage="health", success=True)
                db.commit()
                logger.info(
                    "Health cycle complete: brand=%s domains_ok=%d domains_failed=%d",
                    brand.brand_name, domains_ok, domains_failed,
                )

            except Exception:
                db.rollback()
                logger.exception("Health cycle failed for brand=%s", brand.brand_name)

        _last_cycle_completed_at = datetime.now(timezone.utc)
        _consecutive_cycle_failures = 0

    except Exception:
        _consecutive_cycle_failures += 1
        logger.exception(
            "Health worker cycle failed (consecutive=%d)", _consecutive_cycle_failures
        )
    finally:
        if owns_session:
            db.close()


def emit_heartbeat() -> None:
    last_ok = _last_cycle_completed_at.isoformat() if _last_cycle_completed_at else "never"
    logger.info(
        "[HEARTBEAT] health_worker alive last_cycle=%s consecutive_failures=%d",
        last_ok, _consecutive_cycle_failures,
    )


def main() -> None:
    logger.info("Health Worker starting. Cron: %s", HEALTH_CRON)
    run_health_cycle()

    scheduler = BlockingScheduler()
    cron_parts = HEALTH_CRON.split()
    scheduler.add_job(
        run_health_cycle,
        CronTrigger(
            minute=cron_parts[0], hour=cron_parts[1],
            day=cron_parts[2], month=cron_parts[3], day_of_week=cron_parts[4],
        ),
        id="health_check",
        replace_existing=True,
    )
    scheduler.add_job(
        emit_heartbeat,
        IntervalTrigger(minutes=5),
        id="health_heartbeat",
        replace_existing=True,
    )

    def _shutdown(signum, frame):
        logger.info("Shutting down health_worker...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    scheduler.start()


if __name__ == "__main__":
    main()
