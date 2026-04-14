"""
Backfill match_state_snapshot for brands that have similarity_match records
but no corresponding snapshots.

Usage:
    python app/debug_scripts/backfill_snapshots.py [brand_id]

If brand_id is provided, only that brand is processed.
If omitted, all brands with missing snapshots are processed.
"""
from __future__ import annotations

import sys
import logging
from uuid import UUID

from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_snapshots")


def backfill_brand(db, brand_id: str) -> int:
    """Create initial match_state_snapshot for all unsnapshotted matches of a brand."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.similarity_match import SimilarityMatch
    from app.services.state_aggregator import StateAggregator

    brand = db.get(MonitoredBrand, brand_id)
    if not brand:
        logger.error("Brand %s not found", brand_id)
        return 0

    # Find matches without snapshots
    rows = db.execute(
        text(
            "SELECT sm.id, sm.brand_id, sm.score_final, sm.attention_bucket"
            " FROM similarity_match sm"
            " LEFT JOIN match_state_snapshot mss ON mss.match_id = sm.id"
            " WHERE sm.brand_id = :brand_id AND mss.id IS NULL"
        ),
        {"brand_id": brand_id},
    ).fetchall()

    if not rows:
        logger.info("Brand %s (%s): no missing snapshots", brand.brand_name, brand_id)
        return 0

    logger.info("Brand %s (%s): creating %d snapshots...", brand.brand_name, brand_id, len(rows))

    aggregator = StateAggregator(db)
    created = 0

    for row in rows:
        match_id = row[0]
        score_final = float(row[2] or 0.5)

        try:
            aggregator.recalculate_match_snapshot(
                match_id=match_id,
                brand_id=UUID(str(brand_id)),
                organization_id=brand.organization_id,
                base_lexical_score=score_final,
                domain_age_days=None,
            )
            created += 1
            if created % 50 == 0:
                logger.info("  ... %d/%d done", created, len(rows))
        except Exception as e:
            logger.warning("  match %s failed: %s", match_id, e)

            logger.info("Brand %s: created %d snapshots", brand.brand_name, created)
    return created


def main():
    from app.infra.db.session import SessionLocal

    db = SessionLocal()
    try:
        if len(sys.argv) > 1:
            brand_id = sys.argv[1].strip()
            total = backfill_brand(db, brand_id)
            logger.info("Total snapshots created: %d", total)
        else:
            # Find all brands with missing snapshots
            rows = db.execute(
                text(
                    "SELECT DISTINCT sm.brand_id, mb.name"
                    " FROM similarity_match sm"
                    " JOIN monitored_brand mb ON mb.id = sm.brand_id"
                    " LEFT JOIN match_state_snapshot mss ON mss.match_id = sm.id"
                    " WHERE mss.id IS NULL"
                )
            ).fetchall()

            if not rows:
                logger.info("All brands have complete snapshots.")
                return

            logger.info("Found %d brands with missing snapshots", len(rows))
            grand_total = 0
            for brand_id, brand_name in rows:
                grand_total += backfill_brand(db, str(brand_id))

            logger.info("Grand total snapshots created: %d", grand_total)
    finally:
        db.close()


if __name__ == "__main__":
    main()
