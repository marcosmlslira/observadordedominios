"""Assessment Worker — LLM assessment of matches whose state has changed.

Runs every 15 minutes. Processes snapshots where:
  - llm_source_fingerprint != state_fingerprint (state changed)
  - OR llm_assessment IS NULL (never assessed)
  - OR last_derived_at > 7 days (TTL)

needs_llm_assessment() already filters to immediate_attention/defensive_gap only.
Batch: 10 snapshots per cycle.
"""
from __future__ import annotations

import logging
import signal
import sys
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.infra.db.session import SessionLocal
from app.repositories.match_state_snapshot_repository import MatchStateSnapshotRepository
from app.repositories.monitoring_event_repository import MonitoringEventRepository
from app.services.use_cases.generate_llm_assessment import generate_llm_assessment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("assessment_worker")

ASSESSMENT_INTERVAL_MINUTES = 15
LLM_BATCH_SIZE = 10

_last_cycle_completed_at: datetime | None = None


def _get_cycle_id_for_brand(db: Session, brand_id):
    """Look up today's monitoring_cycle.id for a brand. May return None."""
    from sqlalchemy import text
    from datetime import date
    row = db.execute(
        text(
            "SELECT id FROM monitoring_cycle"
            " WHERE brand_id = :brand_id AND cycle_date = :today LIMIT 1"
        ),
        {"brand_id": brand_id, "today": date.today()},
    ).fetchone()
    return row[0] if row else None


def _gather_tool_results(db: Session, snapshot) -> dict:
    """Collect latest tool results for the snapshot's match from recent events."""
    events = MonitoringEventRepository(db).list_for_match(
        match_id=snapshot.match_id, limit=50
    )
    results = {}
    for evt in reversed(events):
        if evt.tool_name and evt.result_data:
            results[evt.tool_name] = evt.result_data
    return results


def run_assessment_cycle(db: Session | None = None) -> None:
    """Run one batch of LLM assessments for snapshots that need it."""
    global _last_cycle_completed_at

    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    try:
        snapshot_repo = MatchStateSnapshotRepository(db)
        event_repo = MonitoringEventRepository(db)

        snapshots = snapshot_repo.needs_llm_assessment(limit=LLM_BATCH_SIZE)

        if not snapshots:
            logger.debug("assessment_worker: no snapshots need LLM assessment.")
            return

        logger.info("assessment_worker: processing %d snapshots", len(snapshots))
        assessed = 0

        for snapshot in snapshots:
            try:
                match_dict: dict = {
                    "attention_bucket": snapshot.derived_bucket,
                    "risk_level": snapshot.derived_risk,
                    "score_final": snapshot.derived_score,
                    "domain_name": None,
                }

                from app.models.similarity_match import SimilarityMatch
                match_obj = db.get(SimilarityMatch, snapshot.match_id)
                if match_obj:
                    match_dict["domain_name"] = match_obj.domain_name

                from app.models.monitored_brand import MonitoredBrand
                brand = db.get(MonitoredBrand, snapshot.brand_id)
                brand_name = brand.brand_name if brand else "Unknown"

                tool_results = _gather_tool_results(db, snapshot)

                llm_result = generate_llm_assessment(
                    match=match_dict,
                    brand_name=str(brand_name),
                    tool_results=tool_results,
                    signals=snapshot.active_signals or [],
                )

                if llm_result is None:
                    logger.debug(
                        "LLM assessment skipped for snapshot=%s (gate/no key)", snapshot.id
                    )
                    continue

                cycle_id = _get_cycle_id_for_brand(db, snapshot.brand_id)

                event_repo.create(
                    organization_id=snapshot.organization_id,
                    brand_id=snapshot.brand_id,
                    match_id=snapshot.match_id,
                    cycle_id=cycle_id,
                    event_type="llm_assessment",
                    event_source="assessment",
                    tool_name="llm",
                    result_data=llm_result,
                )
                db.flush()

                import json
                from psycopg2.extras import Json as PgJson
                from sqlalchemy import text
                db.execute(
                    text(
                        "UPDATE match_state_snapshot"
                        " SET llm_assessment = :assessment,"
                        "     llm_source_fingerprint = :fingerprint,"
                        "     updated_at = NOW()"
                        " WHERE id = :snapshot_id"
                    ),
                    {
                        "assessment": PgJson(llm_result),
                        "fingerprint": snapshot.state_fingerprint,
                        "snapshot_id": snapshot.id,
                    },
                )
                db.commit()
                assessed += 1
                logger.info(
                    "LLM assessed snapshot=%s bucket=%s",
                    snapshot.id, snapshot.derived_bucket,
                )

            except Exception:
                db.rollback()
                logger.exception("LLM assessment failed for snapshot=%s", snapshot.id)

        _last_cycle_completed_at = datetime.now(timezone.utc)
        logger.info("assessment_worker cycle complete: assessed=%d", assessed)

    except Exception:
        logger.exception("assessment_worker cycle failed")
    finally:
        if owns_session:
            db.close()


def emit_heartbeat() -> None:
    last_ok = _last_cycle_completed_at.isoformat() if _last_cycle_completed_at else "never"
    logger.info("[HEARTBEAT] assessment_worker alive last_cycle=%s", last_ok)


def main() -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.interval import IntervalTrigger

    logger.info(
        "Assessment Worker starting. Interval: every %d minutes",
        ASSESSMENT_INTERVAL_MINUTES,
    )
    run_assessment_cycle()

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_assessment_cycle,
        IntervalTrigger(minutes=ASSESSMENT_INTERVAL_MINUTES),
        id="llm_assessment",
        replace_existing=True,
    )
    scheduler.add_job(
        emit_heartbeat,
        IntervalTrigger(minutes=5),
        id="assessment_heartbeat",
        replace_existing=True,
    )

    def _shutdown(signum, frame):
        logger.info("Shutting down assessment_worker...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    scheduler.start()


if __name__ == "__main__":
    main()
