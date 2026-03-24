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
from app.repositories.domain_repository import list_partition_tlds
from app.repositories.similarity_repository import SimilarityRepository
from app.services.use_cases.compute_similarity import (
    compute_seeded_scores,
    generate_typo_candidates,
)
from app.services.monitoring_profile import iter_scan_seeds, pick_matched_rule

logger = logging.getLogger(__name__)

# Minimum composite score to persist a match
SCORE_THRESHOLD = 0.40
NOISE_MODE_THRESHOLDS = {
    "conservative": 0.60,
    "standard": 0.50,
    "broad": 0.42,
}


def run_similarity_scan(
    db: Session,
    brand: MonitoredBrand,
    tld: str,
    *,
    force_full: bool = False,
) -> dict[str, int]:
    """Run a similarity scan for a single brand × TLD combination.

    Returns metrics dict: {candidates, matched, scanned}.
    """
    repo = SimilarityRepository(db)
    cursor = repo.get_or_create_cursor(brand.id, tld)

    # Determine watermark for delta scans
    watermark_at = None
    if not force_full and cursor.scan_phase == "delta" and cursor.watermark_at:
        watermark_at = cursor.watermark_at
        logger.info(
            "Delta scan for brand=%s tld=%s watermark=%s",
            brand.brand_label, tld, watermark_at,
        )
    else:
        logger.info(
            "Full scan for brand=%s tld=%s force_full=%s",
            brand.brand_label, tld, force_full,
        )

    repo.start_scan(cursor)
    db.commit()

    try:
        scan_seeds = iter_scan_seeds(list(brand.seeds or []))
        if not scan_seeds:
            logger.warning("No scan seeds available for brand=%s", brand.brand_name)
            repo.finish_scan(
                cursor,
                status="complete",
                domains_scanned=0,
                domains_matched=0,
            )
            db.commit()
            return {"candidates": 0, "matched": 0, "scanned": 0, "removed": 0}

        per_seed_limit = max(250, min(1500, int(5000 / max(1, len(scan_seeds)))))
        logger.info(
            "Scanning brand=%s with %d seeds for tld=%s (per_seed_limit=%d)",
            brand.brand_name,
            len(scan_seeds),
            tld,
            per_seed_limit,
        )

        threshold = NOISE_MODE_THRESHOLDS.get(brand.noise_mode, SCORE_THRESHOLD)
        best_matches_by_domain: dict[str, dict] = {}
        candidate_domain_names: set[str] = set()
        now = datetime.now(timezone.utc)

        for seed in scan_seeds:
            typo_candidates = list(generate_typo_candidates(seed.seed_value))
            candidates = repo.fetch_candidates(
                brand_label=seed.seed_value,
                tld=tld,
                typo_candidates=typo_candidates,
                watermark_at=watermark_at,
                limit=per_seed_limit,
            )
            logger.info(
                "Found %d candidates for brand=%s seed=%s tld=%s",
                len(candidates),
                brand.brand_name,
                seed.seed_value,
                tld,
            )

            for cand in candidates:
                candidate_domain_names.add(cand["name"])
                scores = compute_seeded_scores(
                    label=cand["label"],
                    seed_value=seed.seed_value,
                    brand_keywords=brand.keywords or [],
                    trigram_sim=cand["sim_trigram"],
                    seed_weight=seed.base_weight,
                    channel_scope=seed.channel_scope,
                )

                if scores["score_final"] < threshold:
                    continue

                matched_channel = (
                    "registrable_domain"
                    if seed.seed_type == "domain_label"
                    else "associated_brand"
                )
                candidate_match = {
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
                    "matched_channel": matched_channel,
                    "matched_seed_id": seed.id,
                    "matched_seed_value": seed.seed_value,
                    "matched_seed_type": seed.seed_type,
                    "matched_rule": pick_matched_rule(scores["reasons"], matched_channel),
                    "source_stream": "czds",
                }
                previous = best_matches_by_domain.get(cand["name"])
                if not previous or (
                    candidate_match["score_final"],
                    seed.base_weight,
                ) > (
                    previous["score_final"],
                    next(
                        (row.base_weight for row in scan_seeds if row.id == previous["matched_seed_id"]),
                        0.0,
                    ),
                ):
                    best_matches_by_domain[cand["name"]] = candidate_match

        # ── 4. Persist matches ─────────────────────────────────
        matches_to_upsert = list(best_matches_by_domain.values())
        matched_count = repo.upsert_matches(matches_to_upsert)
        kept_domain_names = sorted(best_matches_by_domain.keys())
        candidate_domain_names_sorted = sorted(candidate_domain_names)

        removed_subdomain_matches = repo.delete_subdomain_matches(brand.id, tld)
        removed_stale_matches = 0
        if force_full or watermark_at is None:
            removed_stale_matches = repo.reconcile_matches_for_brand_tld(
                brand.id,
                tld,
                kept_domain_names,
            )
        else:
            removed_stale_matches = repo.delete_matches_for_brand_tld(
                brand.id,
                tld,
                sorted(set(candidate_domain_names_sorted) - set(kept_domain_names)),
            )

        logger.info("Upserted %d matches for brand=%s tld=%s",
                     matched_count, brand.brand_label, tld)
        logger.info(
            "Pruned %d stale matches and %d subdomain matches for brand=%s tld=%s",
            removed_stale_matches,
            removed_subdomain_matches,
            brand.brand_label,
            tld,
        )

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
            domains_scanned=len(candidate_domain_names_sorted),
            domains_matched=matched_count,
        )
        db.commit()

        metrics = {
            "candidates": len(candidate_domain_names_sorted),
            "matched": matched_count,
            "scanned": len(candidate_domain_names_sorted),
            "removed": removed_stale_matches + removed_subdomain_matches,
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
    *,
    force_full: bool = False,
) -> dict[str, dict[str, int]]:
    """Run similarity scan across all TLDs for a brand.

    If brand.tld_scope is set, scans only those TLDs.
    Otherwise scans all TLDs that have partitions.

    Returns: {tld: metrics_dict, ...}
    """
    if brand.tld_scope:
        tlds = brand.tld_scope
    else:
        # Get all TLD partitions from partition bounds (handles multi-level TLDs
        # like "com.br" correctly, unlike parsing partition table names)
        partition_tlds = list_partition_tlds(db)

        # Also include TLDs from existing scan cursors for this brand
        cursor_rows = db.execute(text(
            "SELECT DISTINCT tld FROM similarity_scan_cursor WHERE brand_id = :bid"
        ), {"bid": brand.id}).fetchall()
        cursor_tlds = {r[0] for r in cursor_rows}

        tlds = sorted(set(partition_tlds) | cursor_tlds)

    if not tlds:
        logger.warning("No TLDs found for brand=%s", brand.brand_label)
        return {}

    results: dict[str, dict[str, int]] = {}
    for tld in tlds:
        try:
            results[tld] = run_similarity_scan(
                db,
                brand,
                tld,
                force_full=force_full,
            )
        except Exception:
            logger.exception("Failed scan for brand=%s tld=%s", brand.brand_label, tld)
            results[tld] = {"candidates": 0, "matched": 0, "scanned": 0, "error": True}

    return results
