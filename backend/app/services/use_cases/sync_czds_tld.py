"""Use case: sync a single TLD from CZDS — orchestrates download, upload, and delta."""

from __future__ import annotations

import logging
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infra.external.czds_client import CZDSClient
from app.infra.external.s3_storage import S3Storage
from app.repositories.domain_repository import ensure_partition
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.repositories.zone_artifact_repository import ZoneArtifactRepository
from app.services.use_cases.apply_zone_delta import apply_zone_delta

logger = logging.getLogger(__name__)


class SyncAlreadyRunningError(Exception):
    """Raised when a sync for this TLD is already running."""
    pass


class CooldownActiveError(Exception):
    """Raised when the TLD is still within the cooldown window."""
    pass


def sync_czds_tld(
    db: Session,
    tld: str,
    *,
    force: bool = False,
    czds_client: CZDSClient | None = None,
    s3_storage: S3Storage | None = None,
    run_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """
    Full orchestration: lock → cooldown check → download → S3 → delta → checkpoint.

    Returns the run_id of the completed run.
    """
    source = "czds"
    run_repo = IngestionRunRepository(db)
    artifact_repo = ZoneArtifactRepository(db)
    czds = czds_client or CZDSClient()
    s3 = s3_storage or S3Storage()

    stale_runs = run_repo.recover_stale_runs(
        source,
        tld,
        stale_after_minutes=settings.CZDS_RUNNING_STALE_MINUTES,
        exclude_run_id=run_id,
    )
    if stale_runs:
        db.commit()
        logger.warning(
            "Recovered %d stale running runs for TLD=%s",
            len(stale_runs),
            tld,
        )

    # ── 1. Check for already-running sync ───────────────────
    if run_repo.has_running_run(source, tld, exclude_run_id=run_id):
        raise SyncAlreadyRunningError(f"Sync already running for TLD={tld}")

    # ── 2. Advisory lock per TLD (prevent parallel workers) ─
    lock_key = hash(f"czds_sync_{tld}") & 0x7FFFFFFF
    acquired = db.execute(
        text("SELECT pg_try_advisory_lock(:key)"), {"key": lock_key}
    ).scalar()
    if not acquired:
        raise SyncAlreadyRunningError(f"Could not acquire lock for TLD={tld}")

    try:
        # ── 2b. Ensure TLD partition exists ───────────────────
        ensure_partition(db, tld)

        # ── 3. Cooldown check ───────────────────────────────
        if not force:
            checkpoint = run_repo.get_checkpoint(source, tld)
            if checkpoint and checkpoint.last_successful_run_at:
                cooldown = timedelta(hours=settings.CZDS_FORCE_COOLDOWN_HOURS)
                if datetime.now(timezone.utc) - checkpoint.last_successful_run_at < cooldown:
                    raise CooldownActiveError(
                        f"Cooldown active for TLD={tld}. "
                        f"Last sync: {checkpoint.last_successful_run_at}"
                    )

        # ── 4. Create or fetch ingestion run ────────────────
        if run_id:
            run = run_repo.get_run(run_id)
            if not run:
                run = run_repo.create_run(source, tld)
        else:
            run = run_repo.create_run(source, tld)
        db.commit()
        logger.info("Created ingestion run %s for TLD=%s", run.id, tld)

        object_key: str | None = None
        artifact = None
        local_path: Path | None = None

        try:
            # ── 5. Download zone file or reuse local ────────
            data_dir = Path("/data/czds")
            data_dir.mkdir(parents=True, exist_ok=True)
            local_path = data_dir / f"{tld}.zone.gz"

            download_needed = True
            if local_path.exists():
                mtime = datetime.fromtimestamp(local_path.stat().st_mtime, timezone.utc)
                if datetime.now(timezone.utc) - mtime < timedelta(hours=24):
                    logger.info("Local zone file %s is recent, skipping download.", local_path)
                    download_needed = False

            run_repo.touch_run(run)
            db.commit()
            if download_needed:
                local_path, sha256, size_bytes = czds.download_zone(tld, dest_dir=str(data_dir))
            else:
                import hashlib
                hasher = hashlib.sha256()
                size_bytes = 0
                logger.info("Hashing local zone file: %s", local_path)
                with open(local_path, "rb") as f:
                    for chunk in iter(lambda: f.read(8192 * 4), b""):
                        hasher.update(chunk)
                        size_bytes += len(chunk)
                sha256 = hasher.hexdigest()

            run_repo.touch_run(run)
            db.commit()

            # ── 6. Upload to S3 ─────────────────────────────
            s3.ensure_bucket()
            object_key = S3Storage.build_object_key(tld, run.id)
            etag = s3.upload_zone_file(
                local_path, object_key,
                tld=tld, run_id=run.id, sha256=sha256,
            )
            run_repo.touch_run(run)
            db.commit()

            # ── 7. Persist artifact metadata ────────────────
            artifact = artifact_repo.create_artifact(
                source=source,
                tld=tld,
                bucket=settings.S3_BUCKET,
                object_key=object_key,
                etag=etag,
                sha256=sha256,
                size_bytes=size_bytes,
            )
            db.flush()

            # ── 8. Parse & apply delta ──────────────────────
            metrics = apply_zone_delta(
                db, zone_file_path=local_path, tld=tld, run_id=run.id,
            )

            # ── 9. Finalise run as success ──────────────────
            run_repo.finish_run(
                run,
                status="success",
                metrics=metrics,
                artifact_id=artifact.id,
            )
            run_repo.upsert_checkpoint(source, tld, run)
            db.commit()

            # Clean up local cache after successful sync (R4)
            if local_path.exists():
                try:
                    local_path.unlink()
                    logger.info("Cleaned up local cache: %s", local_path)
                except OSError:
                    logger.warning("Failed to delete local cache: %s", local_path, exc_info=True)

            logger.info(
                "Sync SUCCESS: run_id=%s tld=%s metrics=%s",
                run.id, tld, metrics,
            )
            return run.id

        except Exception as exc:
            logger.exception("Sync FAILED for TLD=%s run_id=%s", tld, run.id)
            db.rollback()

            # Cleanup S3 artifact from failed run (avoid orphans)
            if object_key is not None:
                try:
                    s3.delete_object(object_key)
                    logger.info("Cleaned up orphan S3 artifact: %s", object_key)
                except Exception:
                    logger.warning("Failed to cleanup S3 artifact: %s", object_key, exc_info=True)

            # Cleanup artifact DB record if it was created
            if artifact is not None:
                try:
                    db.delete(artifact)
                    db.flush()
                except Exception:
                    logger.warning("Failed to cleanup artifact DB record", exc_info=True)

            run_repo.finish_run(run, status="failed", error_message=str(exc))
            db.commit()
            raise

        finally:
            # Clean up temp files ONLY if we used tempfile (not /data/)
            if local_path is not None:
                parent = local_path.parent
                if "czds_" in parent.name and "/data" not in str(parent):
                    shutil.rmtree(parent, ignore_errors=True)

    finally:
        # Release advisory lock
        db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})
