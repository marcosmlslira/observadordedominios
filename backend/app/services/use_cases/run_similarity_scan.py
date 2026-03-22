"""Use case: run similarity scan for a monitored brand against a TLD.

Orchestrates: cursor management → candidate fetching → scoring → match persistence.
Supports both initial (full) and delta (incremental) scans via watermark.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.monitored_brand import MonitoredBrand
from app.repositories.similarity_repository import SimilarityRepository
from app.services.use_cases.compute_similarity import (
    compute_scores,
    generate_typo_candidates,
)

logger = logging.getLogger(__name__)

# Minimum composite score to persist a match
SCORE_THRESHOLD = 0.30


def run_similarity_scan(
    db: Session,
    brand: MonitoredBrand,
    tld: str,
) -> dict[str, int]:
    """Run a similarity scan for a single brand × TLD combination.

    Returns metrics dict: {candidates, matched, scanned}.
    """
    repo = SimilarityRepository(db)
    cursor = repo.get_or_create_cursor(brand.id, tld)

    # Determine watermark for delta scans
    watermark_at = None
    if cursor.scan_phase == "delta" and cursor.watermark_at:
        watermark_at = cursor.watermark_at
        logger.info(
            "Delta scan for brand=%s tld=%s watermark=%s",
            brand.brand_label, tld, watermark_at,
        )
    else:
        logger.info("Initial scan for brand=%s tld=%s", brand.brand_label, tld)

    repo.start_scan(cursor)
    db.commit()

    try:
        # ── 1. Generate typo candidates ────────────────────────
        typo_candidates = list(generate_typo_candidates(brand.brand_label))
        logger.info(
            "Generated %d typo candidates for '%s'",
            len(typo_candidates), brand.brand_label,
        )

        # ── 2. Fetch candidates from domain table ──────────────
        candidates = repo.fetch_candidates(
            brand_label=brand.brand_label,
            tld=tld,
            typo_candidates=typo_candidates,
            watermark_at=watermark_at,
            limit=5000,
        )
        logger.info("Found %d candidates for brand=%s tld=%s",
                     len(candidates), brand.brand_label, tld)

        # ── 3. Score each candidate ────────────────────────────
        matches_to_upsert: list[dict] = []
        now = datetime.now(timezone.utc)

        for cand in candidates:
            scores = compute_scores(
                label=cand["label"],
                brand_label=brand.brand_label,
                brand_keywords=brand.keywords or [],
                trigram_sim=cand["sim_trigram"],
            )

            if scores["score_final"] < SCORE_THRESHOLD:
                continue

            matches_to_upsert.append({
                "brand_id": brand.id,
                "domain_name": cand["name"],
                "tld": cand["tld"],
                "label": cand["label"],
                "score_final": scores["score_final"],
                "score_trigram": scores["score_trigram"],
                "score_levenshtein": scores["score_levenshtein"],
                "score_brand_hit": scores["score_brand_hit"],
                "score_keyword": scores["score_keyword"],
                "score_homograph": scores["score_homograph"],
                "reasons": scores["reasons"],
                "risk_level": scores["risk_level"],
                "first_detected_at": now,
                "domain_first_seen": cand["first_seen_at"],
            })

        # ── 4. Persist matches ─────────────────────────────────
        matched_count = repo.upsert_matches(matches_to_upsert)
        logger.info("Upserted %d matches for brand=%s tld=%s",
                     matched_count, brand.brand_label, tld)

        # ── 5. Update watermark ────────────────────────────────
        # Set watermark to the max first_seen_at across ALL domains in this TLD
        # (not just candidates) so delta picks up everything new next time
        new_watermark = db.execute(
            text("SELECT MAX(first_seen_at) FROM domain WHERE tld = :tld"),
            {"tld": tld},
        ).scalar()

        repo.finish_scan(
            cursor,
            status="complete",
            watermark_at=new_watermark,
            domains_scanned=len(candidates),
            domains_matched=matched_count,
        )
        db.commit()

        metrics = {
            "candidates": len(candidates),
            "matched": matched_count,
            "scanned": len(candidates),
        }

        logger.info(
            "Scan COMPLETE: brand=%s tld=%s metrics=%s",
            brand.brand_label, tld, metrics,
        )
        return metrics

    except Exception as exc:
        logger.exception(
            "Scan FAILED: brand=%s tld=%s", brand.brand_label, tld,
        )
        db.rollback()
        repo.finish_scan(
            cursor,
            status="failed",
            error_message=str(exc),
        )
        db.commit()
        raise


def run_similarity_scan_all(
    db: Session,
    brand: MonitoredBrand,
) -> dict[str, dict[str, int]]:
    """Run similarity scan across all TLDs for a brand.

    If brand.tld_scope is set, scans only those TLDs.
    Otherwise scans all TLDs that have partitions.

    Returns: {tld: metrics_dict, ...}
    """
    if brand.tld_scope:
        tlds = brand.tld_scope
    else:
        # Get all TLD partitions from the database
        rows = db.execute(text("""
            SELECT DISTINCT tld FROM similarity_scan_cursor WHERE brand_id = :bid
            UNION
            SELECT REPLACE(relname, 'domain_', '') AS tld
            FROM pg_class
            WHERE relname LIKE 'domain_%'
              AND relkind = 'r'
              AND relname != 'domain_old'
        """), {"bid": brand.id}).fetchall()
        tlds = [r[0] for r in rows] if rows else []

    if not tlds:
        logger.warning("No TLDs found for brand=%s", brand.brand_label)
        return {}

    results: dict[str, dict[str, int]] = {}
    for tld in tlds:
        try:
            results[tld] = run_similarity_scan(db, brand, tld)
        except Exception:
            logger.exception("Failed scan for brand=%s tld=%s", brand.brand_label, tld)
            results[tld] = {"candidates": 0, "matched": 0, "scanned": 0, "error": True}

    return results
