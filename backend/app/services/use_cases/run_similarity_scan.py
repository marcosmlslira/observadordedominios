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
from app.services.monitoring_profile import iter_scan_seeds, pick_matched_rule
from app.services.use_cases.compute_actionability import compute_actionability
from app.services.use_cases.compute_similarity import (
    compute_seeded_scores,
    generate_typo_candidates,
)

logger = logging.getLogger(__name__)

# Minimum composite score to persist a match
SCORE_THRESHOLD = 0.40

# North Star disposition taxonomy — pre-enrichment mapping from attention bucket + rule
_BUCKET_DISPOSITION_MAP = {
    "immediate_attention": "live_but_unknown",
    "defensive_gap": "defensive_gap",
    "watchlist": "inconclusive",
}


def _bucket_to_disposition(bucket: str, matched_rule: str | None) -> str:
    return _BUCKET_DISPOSITION_MAP.get(bucket, "inconclusive")
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
        official_domains = {
            (domain.registrable_domain or domain.domain_name).strip().lower()
            for domain in (brand.domains or [])
            if getattr(domain, "is_active", True)
        }
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
                if cand["name"].strip().lower() in official_domains:
                    continue
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
                matched_rule = pick_matched_rule(scores["reasons"], matched_channel)
                actionability = compute_actionability(
                    brand,
                    domain_name=cand["name"],
                    tld=cand["tld"],
                    score_final=scores["score_final"],
                    risk_level=scores["risk_level"],
                    reasons=scores["reasons"],
                    matched_rule=matched_rule,
                    matched_seed_type=seed.seed_type,
                    matched_seed_value=seed.seed_value,
                    matched_channel=matched_channel,
                    domain_first_seen=cand["first_seen_at"],
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
                    "matched_rule": matched_rule,
                    "source_stream": "czds",
                    "actionability_score": actionability["actionability_score"],
                    "attention_bucket": actionability["attention_bucket"],
                    "attention_reasons": actionability["attention_reasons"],
                    "recommended_action": actionability["recommended_action"],
                    "ownership_classification": "third_party_unknown",
                    "self_owned": False,
                    "disposition": _bucket_to_disposition(actionability["attention_bucket"], matched_rule),
                    "confidence": round(scores["score_final"], 4),
                    "delivery_risk": "none",
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

        # Enrichment deferred to enrichment_worker — set status to pending
        for match in matches_to_upsert:
            match.setdefault("enrichment_status", "pending")
            match.setdefault("enrichment_summary", None)
            match.setdefault("last_enriched_at", None)

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
        # Use raw SQL after rollback — the ORM cursor object may be in a stale state
        # after rollback (SQLAlchemy flush errors leave the session identity map
        # inconsistent), so we bypass the ORM to safely update the cursor.
        try:
            db.execute(
                text(
                    "UPDATE similarity_scan_cursor"
                    " SET status='failed', error_message=:err,"
                    "     finished_at=NOW(), updated_at=NOW()"
                    " WHERE brand_id=:bid AND tld=:tld"
                ),
                {"err": str(exc)[:2000], "bid": brand.id, "tld": tld},
            )
            db.commit()
        except Exception:
            logger.exception(
                "Failed to persist scan failure state for brand=%s tld=%s",
                brand.brand_label, tld,
            )
            db.rollback()
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


def run_similarity_scan_job(
    db: Session,
    job_id: uuid.UUID,
) -> dict[str, dict[str, int]]:
    repo = SimilarityRepository(db)
    job = repo.get_scan_job(job_id)
    if not job:
        raise ValueError(f"similarity scan job {job_id} not found")

    brand = db.get(MonitoredBrand, job.brand_id)
    if not brand:
        raise ValueError(f"brand {job.brand_id} not found")

    if job.status != "running":
        repo.start_scan_job(job)
        db.commit()

    results: dict[str, dict[str, int]] = {}
    for tld in list(job.effective_tlds or []):
        started_at = datetime.now(timezone.utc)
        repo.update_scan_job_tld(job, tld=tld, status="running", started_at=started_at)
        db.commit()
        try:
            metrics = run_similarity_scan(
                db,
                brand,
                tld,
                force_full=bool(job.force_full),
            )
            repo.update_scan_job_tld(
                job,
                tld=tld,
                status="completed",
                candidates=int(metrics.get("candidates", 0)),
                matched=int(metrics.get("matched", 0)),
                removed=int(metrics.get("removed", 0)),
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )
            repo.heartbeat_scan_job(job)
            db.commit()
            results[tld] = metrics
        except Exception as exc:
            logger.exception("Queued similarity scan failed for brand=%s tld=%s", brand.brand_label, tld)
            repo.update_scan_job_tld(
                job,
                tld=tld,
                status="failed",
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                error_message=str(exc),
            )
            repo.heartbeat_scan_job(job)
            db.commit()
            results[tld] = {"candidates": 0, "matched": 0, "scanned": 0, "removed": 0, "error": True}

    repo.finalize_scan_job(job)
    db.commit()
    return results
