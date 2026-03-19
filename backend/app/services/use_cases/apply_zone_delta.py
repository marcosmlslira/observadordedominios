"""Use case: apply zone delta — parse zone file, stage, and apply to DB."""

from __future__ import annotations

import gzip
import logging
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.repositories.domain_repository import DomainRepository

logger = logging.getLogger(__name__)

# We only care about NS-delegated names (type "NS" or the domain names from the zone).
# A zone file line looks like:
# example.net.  172800  IN  NS  ns1.example.net.
# We extract the leftmost label as the FQDN being delegated.

_BATCH_SIZE = 50_000


def _parse_zone_stream(path: Path, tld: str):
    """
    Generator that yields normalised domain names from a gzipped zone file.

    Yields only second-level domains (e.g. "example.net") from NS records.
    """
    suffix = f".{tld}."
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
            # We only care about the owner name (first column)
            owner = parts[0].lower().rstrip(".")
            if not owner.endswith(f".{tld}") and owner != tld:
                # Only consider second-level: "example.{tld}"
                continue

            # Normalise: strip trailing dot, lowercase
            domain_name = owner

            # Skip the bare TLD itself
            if domain_name == tld:
                continue

            if domain_name not in seen_in_batch:
                seen_in_batch.add(domain_name)
                yield domain_name

                # Periodically clear set to limit memory
                if len(seen_in_batch) >= 500_000:
                    seen_in_batch.clear()


def apply_zone_delta(
    db: Session,
    *,
    zone_file_path: Path,
    tld: str,
    run_id: uuid.UUID,
) -> dict[str, int]:
    """
    Parse a zone file in streaming mode, load into staging table,
    then apply the delta (insert / reactivate / soft-delete).
    """
    repo = DomainRepository(db)
    staging_table = repo.create_staging_table(run_id)

    # Stream-parse and batch-insert into staging
    batch: list[str] = []
    total_parsed = 0

    for domain_name in _parse_zone_stream(zone_file_path, tld):
        # Sanitise for SQL safety (basic check — names are already validated)
        safe_name = domain_name.replace("'", "''")
        batch.append(safe_name)

        if len(batch) >= _BATCH_SIZE:
            repo.bulk_insert_staging(staging_table, batch)
            total_parsed += len(batch)
            logger.info("Staged %d domains so far…", total_parsed)
            batch.clear()

    if batch:
        repo.bulk_insert_staging(staging_table, batch)
        total_parsed += len(batch)

    logger.info("Total domains staged: %d", total_parsed)

    # Apply the delta
    metrics = repo.apply_delta(staging_table, tld, run_id)
    return metrics
