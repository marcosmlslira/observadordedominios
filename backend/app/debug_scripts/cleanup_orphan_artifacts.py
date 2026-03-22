"""One-off script: cleanup orphan S3 artifacts from failed ingestion runs.

Usage (inside container):
    python -m app.debug_scripts.cleanup_orphan_artifacts
    python -m app.debug_scripts.cleanup_orphan_artifacts --dry-run
"""

from __future__ import annotations

import argparse
import logging

from sqlalchemy import text

from app.infra.db.session import SessionLocal
from app.infra.external.s3_storage import S3Storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main(dry_run: bool = False) -> None:
    db = SessionLocal()
    s3 = S3Storage()

    try:
        # Find artifacts linked to failed runs or not linked to any successful run
        orphans = db.execute(text("""
            SELECT a.id, a.object_key, a.tld, a.size_bytes
            FROM zone_file_artifact a
            WHERE NOT EXISTS (
                SELECT 1 FROM ingestion_run r
                WHERE r.artifact_id = a.id
                  AND r.status = 'success'
            )
        """)).fetchall()

        if not orphans:
            logger.info("No orphan artifacts found.")
            return

        total_bytes = 0
        for row in orphans:
            artifact_id, object_key, tld, size_bytes = row
            total_bytes += size_bytes
            logger.info(
                "%s artifact id=%s tld=%s key=%s size=%.1f MB",
                "[DRY-RUN]" if dry_run else "DELETING",
                artifact_id, tld, object_key, size_bytes / 1024 / 1024,
            )

            if not dry_run:
                try:
                    s3.delete_object(object_key)
                except Exception:
                    logger.warning("Failed to delete S3 object: %s", object_key, exc_info=True)

                db.execute(
                    text("DELETE FROM zone_file_artifact WHERE id = :id"),
                    {"id": artifact_id},
                )

        if not dry_run:
            db.commit()

        logger.info(
            "%s %d orphan artifacts, freed %.1f MB",
            "Would delete" if dry_run else "Deleted",
            len(orphans),
            total_bytes / 1024 / 1024,
        )

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="List orphans without deleting")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
