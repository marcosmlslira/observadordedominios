"""Use case: sync a single TLD from OpenINTEL public S3 — discover, stream, upsert."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta, timezone, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infra.external.openintel_client import OpenIntelClient
from app.repositories.domain_repository import ensure_partition
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.services.use_cases.apply_zone_delta import apply_domain_names_delta

logger = logging.getLogger(__name__)


class CzdsRunningError(Exception):
    """Raised when a CZDS sync is currently running — OpenINTEL must not overlap."""


class SyncAlreadyRunningError(Exception):
    """Raised when this TLD is already being synced by another OpenINTEL worker."""


class CooldownActiveError(Exception):
    """Raised when the TLD is still within the cooldown window."""


class SnapshotNotFoundError(Exception):
    """Raised when no recent snapshot is available for this TLD."""


class SnapshotAlreadyIngestedError(Exception):
    """Raised when the discovered snapshot was already successfully ingested."""


def sync_openintel_tld(
    db: Session,
    tld: str,
    *,
    force: bool = False,
    run_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Discover and ingest the latest OpenINTEL ccTLD snapshot into the domain table.

    Returns the run_id of the completed run.

    Raises CzdsRunningError if any CZDS run is active (shared partition conflict).
    Raises CooldownActiveError if the TLD was successfully synced within the last
    OPENINTEL_FORCE_COOLDOWN_HOURS hours and force=False.
    Raises SnapshotNotFoundError if no recent S3 data is available.
    Raises SnapshotAlreadyIngestedError if today's snapshot was already processed.
    """
    source = "openintel"
    run_repo = IngestionRunRepository(db)

    # ── 1. Abort if CZDS is currently writing to the same partitions ──────────
    if run_repo.has_any_source_running("czds"):
        raise CzdsRunningError(
            "CZDS sync is currently running — OpenINTEL cannot write to the same "
            "partitions. Retry after CZDS finishes."
        )

    # ── 2. Recover stale OpenINTEL runs for this TLD ──────────────────────────
    stale = run_repo.recover_stale_runs(
        source,
        tld,
        stale_after_minutes=settings.OPENINTEL_RUNNING_STALE_MINUTES,
        exclude_run_id=run_id,
    )
    if stale:
        db.commit()
        logger.warning("Recovered %d stale OpenINTEL run(s) for TLD=%s", len(stale), tld)

    # ── 3. Advisory lock per TLD (prevent duplicate workers) ─────────────────
    lock_key = hash(f"openintel_sync_{tld}") & 0x7FFFFFFF
    acquired = db.execute(
        text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
    ).scalar()
    if not acquired:
        raise SyncAlreadyRunningError(
            f"Could not acquire advisory lock for OpenINTEL TLD={tld}"
        )

    try:
        # ── 4. Check for already-running sync ─────────────────────────────────
        if run_repo.has_running_run(source, tld, exclude_run_id=run_id):
            raise SyncAlreadyRunningError(f"OpenINTEL sync already running for TLD={tld}")

        # ── 5. Ensure TLD partition exists ────────────────────────────────────
        ensure_partition(db, tld)

        # ── 6. Cooldown check ─────────────────────────────────────────────────
        if not force:
            checkpoint = run_repo.get_checkpoint(source, tld)
            if checkpoint and checkpoint.last_successful_run_at:
                cooldown = timedelta(hours=settings.OPENINTEL_FORCE_COOLDOWN_HOURS)
                age = datetime.now(timezone.utc) - checkpoint.last_successful_run_at
                if age < cooldown:
                    raise CooldownActiveError(
                        f"OpenINTEL cooldown active for TLD={tld}. "
                        f"Last sync: {checkpoint.last_successful_run_at.isoformat()}"
                    )

        # ── 7. Discover snapshot ──────────────────────────────────────────────
        client = OpenIntelClient()
        result = client.discover_snapshot(tld)
        if result is None:
            raise SnapshotNotFoundError(
                f"No OpenINTEL snapshot found for TLD={tld} "
                f"within {settings.OPENINTEL_MAX_LOOKBACK_DAYS} days"
            )
        s3_key, snapshot_date = result

        # ── 8. Idempotency: skip if this snapshot was already ingested ────────
        if not force and run_repo.has_successful_run_after(source, tld, snapshot_date):
            raise SnapshotAlreadyIngestedError(
                f"OpenINTEL snapshot for TLD={tld} date={snapshot_date} "
                f"was already successfully ingested"
            )

        # ── 9. Create ingestion run ───────────────────────────────────────────
        if run_id:
            run = run_repo.get_run(run_id) or run_repo.create_run(source, tld)
        else:
            run = run_repo.create_run(source, tld)
        db.commit()
        logger.info(
            "OpenINTEL run=%s TLD=%s snapshot=%s key=%s",
            run.id,
            tld,
            snapshot_date,
            s3_key,
        )

        try:
            # ── 10. Stream Parquet → apply delta ──────────────────────────────
            domain_iter = client.stream_apex_domains(s3_key, tld)
            metrics = apply_domain_names_delta(
                db,
                domain_iter,
                tld=tld,
                run_id=run.id,
            )

            # ── 11. Finalise run ──────────────────────────────────────────────
            run_repo.finish_run(run, status="success", metrics=metrics)
            run_repo.upsert_checkpoint(source, tld, run)
            db.commit()

            logger.info(
                "OpenINTEL SUCCESS: run_id=%s TLD=%s snapshot=%s metrics=%s",
                run.id,
                tld,
                snapshot_date,
                metrics,
            )
            return run.id

        except Exception as exc:
            logger.exception(
                "OpenINTEL FAILED: TLD=%s run_id=%s", tld, run.id
            )
            db.rollback()
            run_repo.finish_run(run, status="failed", error_message=str(exc))
            db.commit()
            raise

    finally:
        db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
