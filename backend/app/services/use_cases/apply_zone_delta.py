"""Use case: apply zone delta — parse zone file and upsert to DB."""

from __future__ import annotations

import gzip
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.repositories.domain_repository import DomainRepository

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50_000


def _parse_zone_stream(path: Path, tld: str):
    """Generator: yield normalised second-level domain names from gzipped zone file."""
    seen_in_batch: set[str] = set()

    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="ascii", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue

            owner = parts[0].lower().rstrip(".")
            if not owner.endswith(f".{tld}") and owner != tld:
                continue
            if owner == tld:
                continue

            if owner not in seen_in_batch:
                seen_in_batch.add(owner)
                yield owner

                if len(seen_in_batch) >= 500_000:
                    seen_in_batch.clear()


def apply_zone_delta(
    db: Session,
    *,
    zone_file_path: Path,
    tld: str,
    run_id: uuid.UUID,
) -> dict[str, int]:
    """Parse zone file in streaming mode and upsert directly into domain."""
    ts = datetime.now(timezone.utc)
    repo = DomainRepository(db)
    run_repo = IngestionRunRepository(db)

    batch: list[str] = []
    total_parsed = 0

    for domain_name in _parse_zone_stream(zone_file_path, tld):
        batch.append(domain_name)

        if len(batch) >= _BATCH_SIZE:
            repo.bulk_upsert(batch, tld, ts)
            total_parsed += len(batch)
            logger.info("Upserted %d domains so far...", total_parsed)
            run_repo.update_progress(run_id, domains_seen=total_parsed)
            db.commit()
            batch.clear()

    if batch:
        repo.bulk_upsert(batch, tld, ts)
        total_parsed += len(batch)

    run_repo.update_progress(run_id, domains_seen=total_parsed)
    db.commit()

    logger.info("Total domains upserted: %d", total_parsed)

    return {
        "seen": total_parsed,
        "inserted": total_parsed,
        "reactivated": 0,
        "deleted": 0,
    }
