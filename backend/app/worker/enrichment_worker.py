"""Enrichment Worker — daily enrichment of top-50 ranked matches per brand.

Scheduled at 12:00 UTC. Processes matches with enrichment_budget_rank set,
runs 12 tools per match, recalculates snapshots, applies auto-dismiss.
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
from app.services.monitoring_cycle_service import MonitoringCycleService
from app.services.use_cases.run_enrichment_cycle_match import run_enrichment_cycle_match

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("enrichment_worker")

ENRICHMENT_CRON = getattr(settings, "ENRICHMENT_CRON", "0 12 * * *")

_consecutive_cycle_failures = 0
_last_cycle_completed_at: datetime | None = None


def _fetch_ranked_matches(db: Session, brand_id, *, limit: int = 50):
    from sqlalchemy import text
    from app.models.similarity_match import SimilarityMatch

    rows = db.execute(
        text(
            "SELECT id FROM similarity_match"
            " WHERE brand_id = :brand_id"
            "   AND enrichment_budget_rank IS NOT NULL"
            " ORDER BY enrichment_budget_rank ASC"
            " LIMIT :limit"
        ),
        {"brand_id": brand_id, "limit": limit},
    ).fetchall()
    match_ids = [r[0] for r in rows]
    if not match_ids:
        return []

    return (
        db.query(SimilarityMatch)
        .filter(SimilarityMatch.id.in_(match_ids))
        .order_by(SimilarityMatch.enrichment_budget_rank.asc())
        .all()
    )


def run_enrichment_cycle(db: Session | None = None) -> None:
    """Run enrichment cycle for all active brands."""
    global _consecutive_cycle_failures, _last_cycle_completed_at

    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    try:
        brand_repo = MonitoredBrandRepository(db)
        brands = brand_repo.list_active()

        if not brands:
            logger.info("No active brands for enrichment.")
            return

        logger.info("Starting enrichment cycle for %d brands", len(brands))

        for brand in brands:
            try:
                db.refresh(brand)

                cycle_repo = MonitoringCycleRepository(db)
                cycle, created = cycle_repo.get_or_create_today(
                    brand_id=brand.id,
                    organization_id=brand.organization_id,
                )
                if created:
                    db.commit()

                if cycle.enrichment_status == "completed":
                    logger.info(
                        "Enrichment already completed for brand=%s today", brand.brand_name
                    )
                    continue

                svc = MonitoringCycleService(db, cycle_repo=cycle_repo)
                svc.begin_stage(cycle.id, stage="enrichment")
                db.commit()

                matches = _fetch_ranked_matches(db, brand.id, limit=50)
                logger.info("Enriching %d matches for brand=%s", len(matches), brand.brand_name)

                for match in matches:
                    try:
                        result = run_enrichment_cycle_match(
                            db,
                            match,
                            brand=brand,
                            cycle_id=cycle.id,
                        )
                        if result["auto_dismissed"]:
                            svc.record_dismissed(cycle.id)
                            db.commit()
                        elif result["derived_bucket"] == "immediate_attention":
                            svc.record_escalated(cycle.id)
                            db.commit()
                        logger.debug(
                            "enriched match=%s bucket=%s dismissed=%s",
                            match.id, result["derived_bucket"], result["auto_dismissed"],
                        )
                    except Exception:
                        logger.exception("Enrichment failed for match=%s", match.id)

                svc.finish_stage(cycle.id, stage="enrichment", success=True)
                db.commit()

                logger.info(
                    "Enrichment complete for brand=%s (%d matches)",
                    brand.brand_name, len(matches),
                )

            except Exception:
                db.rollback()
                logger.exception("Enrichment cycle failed for brand=%s", brand.brand_name)

        _last_cycle_completed_at = datetime.now(timezone.utc)
        _consecutive_cycle_failures = 0

    except Exception:
        _consecutive_cycle_failures += 1
        logger.exception(
            "Enrichment worker cycle failed (consecutive=%d)", _consecutive_cycle_failures
        )
    finally:
        if owns_session:
            db.close()


def emit_heartbeat() -> None:
    last_ok = _last_cycle_completed_at.isoformat() if _last_cycle_completed_at else "never"
    logger.info(
        "[HEARTBEAT] enrichment_worker alive last_cycle=%s consecutive_failures=%d",
        last_ok, _consecutive_cycle_failures,
    )


def main() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger

    logger.info("Enrichment Worker starting. Cron: %s", ENRICHMENT_CRON)
    run_enrichment_cycle()

    scheduler = BlockingScheduler()
    cron_parts = ENRICHMENT_CRON.split()
    scheduler.add_job(
        run_enrichment_cycle,
        CronTrigger(
            minute=cron_parts[0], hour=cron_parts[1],
            day=cron_parts[2], month=cron_parts[3], day_of_week=cron_parts[4],
        ),
        id="enrichment",
        replace_existing=True,
    )
    scheduler.add_job(
        emit_heartbeat,
        IntervalTrigger(minutes=5),
        id="enrichment_heartbeat",
        replace_existing=True,
    )

    def _shutdown(signum, frame):
        logger.info("Shutting down enrichment_worker...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    scheduler.start()


if __name__ == "__main__":
    main()
