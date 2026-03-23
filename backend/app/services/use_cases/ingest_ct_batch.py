"""Use case: ingest a batch of raw domain names from CT Log sources.

Shared pipeline for both CertStream (real-time) and crt.sh (daily batch).
Normalizes, ensures partitions, and upserts into the domain table.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.repositories.domain_repository import (
    DomainRepository,
    ensure_partition,
)
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.services.domain_normalizer import normalize_ct_domains

logger = logging.getLogger(__name__)


def ingest_ct_batch(
    db: Session,
    raw_domains: list[str],
    *,
    source: str,
    run_id=None,
) -> dict:
    """Normalize and upsert a batch of raw domain names from CT sources.

    Args:
        db: Database session (caller owns transaction).
        raw_domains: Raw domain names from CertStream or crt.sh.
        source: Source identifier ("certstream" or "crtsh").
        run_id: Optional ingestion_run ID to update metrics.

    Returns:
        Metrics dict: {domains_seen, domains_inserted, by_tld}.
    """
    if not raw_domains:
        return {"domains_seen": 0, "domains_inserted": 0, "by_tld": {}}

    now = datetime.now(timezone.utc)

    # 1. Normalize: lowercase, strip wildcards, tldextract, filter .br, dedup
    normalized = normalize_ct_domains(raw_domains)
    domains_seen = len(raw_domains)
    domains_normalized = len(normalized)

    if not normalized:
        logger.debug(
            "CT batch: %d raw domains, 0 after normalization (source=%s)",
            domains_seen, source,
        )
        return {"domains_seen": domains_seen, "domains_inserted": 0, "by_tld": {}}

    # 2. Ensure partitions exist for all TLDs in this batch
    tlds_in_batch = {tld for _, tld, _ in normalized}
    for tld in tlds_in_batch:
        ensure_partition(db, tld)

    # 3. Bulk upsert across multiple TLDs
    repo = DomainRepository(db)
    by_tld = repo.bulk_upsert_multi_tld(normalized, now)

    total_inserted = sum(by_tld.values())

    # 4. Update ingestion run metrics if provided
    if run_id:
        run_repo = IngestionRunRepository(db)
        run = run_repo.get_run(run_id)
        if run:
            run.domains_seen = (run.domains_seen or 0) + domains_seen
            run.domains_inserted = (run.domains_inserted or 0) + total_inserted
            db.flush()

    # Caller owns transaction — do NOT commit here.
    # CertStream flush loop commits per-flush; sync_crtsh commits per-cycle.

    logger.info(
        "CT batch ingested: source=%s raw=%d normalized=%d upserted=%d tlds=%s",
        source, domains_seen, domains_normalized, total_inserted, dict(by_tld),
    )

    return {
        "domains_seen": domains_seen,
        "domains_inserted": total_inserted,
        "by_tld": dict(by_tld),
    }
