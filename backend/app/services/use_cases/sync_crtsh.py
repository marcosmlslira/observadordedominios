"""Use case: sync domains from crt.sh — daily batch complement to CertStream.

Orchestrates: lock -> cooldown check -> query crt.sh per sub-TLD -> ingest batch -> checkpoint.
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
from app.services.use_cases.ingest_ct_batch import ingest_ct_batch

logger = logging.getLogger(__name__)

SOURCE = "crtsh"
TLD = "br"


def sync_crtsh_tld(
    db: Session,
    *,
    force: bool = False,
    crtsh_client: CrtShClient | None = None,
) -> None:
    """Run a full crt.sh sync cycle for all configured .br sub-TLDs.

    Creates an ingestion_run, queries crt.sh for each sub-TLD,
    and feeds results through the shared CT batch pipeline.
    """
    run_repo = IngestionRunRepository(db)
    crtsh = crtsh_client or CrtShClient()

    # ── 1. Recover stale runs ──────────────────────────────
    stale_runs = run_repo.recover_stale_runs(
        SOURCE, TLD, stale_after_minutes=180,
    )
    if stale_runs:
        db.commit()
        logger.warning("Recovered %d stale crtsh runs", len(stale_runs))

    # ── 2. Check for already-running sync ──────────────────
    if run_repo.has_running_run(SOURCE, TLD):
        logger.info("crt.sh sync already running, skipping")
        return

    # ── 3. Advisory lock ───────────────────────────────────
    lock_key = hash(f"crtsh_sync_br") & 0x7FFFFFFF
    acquired = db.execute(
        text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
    ).scalar()
    if not acquired:
        logger.info("Could not acquire crt.sh advisory lock, skipping")
        return

    try:
        # ── 4. Cooldown check ──────────────────────────────
        if not force:
            checkpoint = run_repo.get_checkpoint(SOURCE, TLD)
            if checkpoint and checkpoint.last_successful_run_at:
                cooldown = timedelta(hours=settings.CT_CRTSH_COOLDOWN_HOURS)
                if datetime.now(timezone.utc) - checkpoint.last_successful_run_at < cooldown:
                    logger.info(
                        "crt.sh cooldown active (last: %s), skipping",
                        checkpoint.last_successful_run_at,
                    )
                    return

        # ── 5. Create ingestion run ────────────────────────
        run = run_repo.create_run(SOURCE, TLD)
        db.commit()
        logger.info("Created crt.sh ingestion run: %s", run.id)

        try:
            # ── 6. Determine time filter ───────────────────
            overlap_hours = settings.CT_CRTSH_QUERY_OVERLAP_HOURS
            min_not_before = datetime.now(timezone.utc) - timedelta(hours=overlap_hours)

            # ── 7. Query each sub-TLD ──────────────────────
            subtlds = [
                t.strip() for t in settings.CT_BR_SUBTLDS.split(",")
                if t.strip() and t.strip() != "br"  # Skip bare "br" — crt.sh query would be too broad
            ]

            total_domains = 0
            for subtld in subtlds:
                logger.info("Querying crt.sh for *.%s...", subtld)
                try:
                    raw_domains = crtsh.query_br_domains(
                        subtld, min_not_before=min_not_before,
                    )
                    if raw_domains:
                        metrics = ingest_ct_batch(
                            db, raw_domains,
                            source=SOURCE, run_id=run.id,
                        )
                        db.commit()  # Commit per sub-TLD batch
                        total_domains += metrics.get("domains_inserted", 0)
                        logger.info(
                            "crt.sh %s: %d raw -> %d inserted",
                            subtld, len(raw_domains), metrics.get("domains_inserted", 0),
                        )
                except Exception:
                    logger.exception("crt.sh query failed for %s", subtld)
                    continue

            # ── 8. Finalize run ────────────────────────────
            # Metrics already accumulated by ingest_ct_batch via run.domains_seen/inserted
            run_repo.finish_run(run, status="success")
            run_repo.upsert_checkpoint(SOURCE, TLD, run)
            db.commit()

            logger.info("crt.sh sync SUCCESS: run_id=%s total_domains=%d", run.id, total_domains)

        except Exception as exc:
            logger.exception("crt.sh sync FAILED: run_id=%s", run.id)
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
        sync_crtsh_tld(db)
    except Exception:
        logger.exception("crt.sh sync cycle failed")
    finally:
        db.close()
    logger.info("crt.sh sync cycle finished.")
