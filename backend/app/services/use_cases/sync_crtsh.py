"""Use case: sync domains from crt.sh — daily batch complement to CertStream.

Orchestrates: lock -> cooldown check -> query crt.sh per TLD -> ingest batch -> checkpoint.
Follows the same pattern as sync_czds_tld.py.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.infra.external.crtsh_client import CrtShClient
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.services.tld_coverage import resolve_ct_fallback_tlds
from app.services.use_cases.ingest_ct_batch import ingest_ct_batch

logger = logging.getLogger(__name__)

SOURCE = "crtsh"


def sync_crtsh_tld(
    db: Session,
    tld: str,
    *,
    force: bool = False,
    crtsh_client: CrtShClient | None = None,
) -> None:
    """Run a crt.sh sync cycle for one effective fallback TLD.

    Creates an ingestion_run, queries crt.sh for the target suffix,
    and feeds results through the shared CT batch pipeline.
    """
    run_repo = IngestionRunRepository(db)
    crtsh = crtsh_client or CrtShClient()

    # ── 1. Recover stale runs ──────────────────────────────
    stale_runs = run_repo.recover_stale_runs(
        SOURCE, tld, stale_after_minutes=180,
    )
    if stale_runs:
        db.commit()
        logger.warning("Recovered %d stale crtsh runs", len(stale_runs))

    # ── 2. Check for already-running sync ──────────────────
    if run_repo.has_running_run(SOURCE, tld):
        logger.info("crt.sh sync already running for %s, skipping", tld)
        return

    # ── 3. Advisory lock ───────────────────────────────────
    lock_key = hash(f"crtsh_sync_{tld}") & 0x7FFFFFFF
    acquired = db.execute(
        text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
    ).scalar()
    if not acquired:
        logger.info("Could not acquire crt.sh advisory lock, skipping")
        return

    try:
        # ── 4. Cooldown check ──────────────────────────────
        if not force:
            checkpoint = run_repo.get_checkpoint(SOURCE, tld)
            if checkpoint and checkpoint.last_successful_run_at:
                cooldown = timedelta(hours=settings.CT_CRTSH_COOLDOWN_HOURS)
                if datetime.now(timezone.utc) - checkpoint.last_successful_run_at < cooldown:
                    logger.info(
                        "crt.sh cooldown active for %s (last: %s), skipping",
                        tld,
                        checkpoint.last_successful_run_at,
                    )
                    return

        # ── 5. Create ingestion run ────────────────────────
        run = run_repo.create_run(SOURCE, tld)
        db.commit()
        logger.info("Created crt.sh ingestion run: %s for %s", run.id, tld)

        try:
            # ── 6. Determine time filter ───────────────────
            overlap_hours = settings.CT_CRTSH_QUERY_OVERLAP_HOURS
            min_not_before = datetime.now(timezone.utc) - timedelta(hours=overlap_hours)

            total_domains = 0
            logger.info("Querying crt.sh for %s...", tld)
            raw_domains = crtsh.query_tld_domains(
                tld, min_not_before=min_not_before,
            )
            if raw_domains:
                metrics = ingest_ct_batch(
                    db, raw_domains,
                    source=SOURCE, run_id=run.id,
                )
                db.commit()
                total_domains += metrics.get("domains_inserted", 0)
                logger.info(
                    "crt.sh %s: %d raw -> %d inserted",
                    tld, len(raw_domains), metrics.get("domains_inserted", 0),
                )

            # ── 8. Finalize run ────────────────────────────
            # Metrics already accumulated by ingest_ct_batch via run.domains_seen/inserted
            run_repo.finish_run(run, status="success")
            run_repo.upsert_checkpoint(SOURCE, tld, run)
            db.commit()

            logger.info("crt.sh sync SUCCESS: run_id=%s tld=%s total_domains=%d", run.id, tld, total_domains)

        except Exception as exc:
            logger.exception("crt.sh sync FAILED: run_id=%s tld=%s", run.id, tld)
            db.rollback()
            run_repo.finish_run(run, status="failed", error_message=str(exc))
            db.commit()
            raise

    finally:
        db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})


def run_crtsh_sync() -> None:
    """Top-level function called by APScheduler. Creates its own DB session."""
    logger.info("Starting crt.sh sync cycle...")
    db = SessionLocal()
    try:
        fallback_tlds = resolve_ct_fallback_tlds(db)
        if not fallback_tlds:
            logger.info("No CT fallback TLDs resolved for crt.sh sync.")
            return
        client = CrtShClient()
        for tld in fallback_tlds:
            try:
                sync_crtsh_tld(db, tld, crtsh_client=client)
            except Exception:
                logger.exception("crt.sh sync failed for fallback TLD=%s", tld)
    except Exception:
        logger.exception("crt.sh sync cycle failed")
    finally:
        db.close()
    logger.info("crt.sh sync cycle finished.")
