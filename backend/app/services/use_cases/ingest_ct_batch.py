"""Use case: ingest a batch of raw domain names from CT Log sources.

Shared pipeline for both CertStream (real-time) and crt.sh (daily batch).
Normalizes, ensures partitions, and upserts into the domain table.

CertStream path (source="certstream"):
  - Accepts all TLDs (no suffix filter)
  - Auto-discovers new TLDs, persisting them in an isolated transaction so
    they are visible in the admin UI even if the batch itself fails
  - Respects per-TLD is_enabled policy
  - Ensures partitions in isolated sessions to avoid committing the main
    ingest transaction prematurely

crt.sh path (source="crtsh"):
  - Filters to .br domains (legacy behaviour)
  - No policy check required
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.infra.db.session import SessionLocal
from app.repositories.domain_repository import (
    DomainRepository,
    ensure_partition,
)
from app.repositories.ingestion_config_repository import IngestionConfigRepository
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
        Metrics dict with counts and per-TLD breakdown.
    """
    if not raw_domains:
        return {"domains_seen": 0, "domains_inserted": 0, "by_tld": {}}

    now = datetime.now(timezone.utc)
    domains_seen = len(raw_domains)

    if source == "certstream":
        return _ingest_certstream_batch(db, raw_domains, domains_seen, now, run_id)
    else:
        return _ingest_legacy_batch(db, raw_domains, domains_seen, now, source, run_id)


# ── CertStream path ──────────────────────────────────────────────────────────

def _ingest_certstream_batch(
    db: Session,
    raw_domains: list[str],
    domains_seen: int,
    now: datetime,
    run_id,
) -> dict:
    # 1. Normalize — no suffix filter; PSL-based TLD extraction for all domains
    normalized = normalize_ct_domains(raw_domains, filter_suffix=None)
    domains_normalized = len(normalized)

    if not normalized:
        logger.debug("certstream batch: %d raw → 0 after normalization", domains_seen)
        return {"domains_seen": domains_seen, "domains_inserted": 0, "by_tld": {}}

    # 2. Policy stage — auto-discover new TLDs + filter disabled ones
    #    New TLD rows are committed in a separate session so they survive batch failure.
    enabled, tlds_all, tlds_enabled, tlds_disabled = _apply_certstream_policy(normalized)

    if not enabled:
        logger.info(
            "certstream batch: source=certstream raw=%d normalized=%d "
            "enabled=0 disabled_tlds=%s",
            domains_seen, domains_normalized, tlds_disabled,
        )
        return {"domains_seen": domains_seen, "domains_inserted": 0, "by_tld": {}}

    # 3. Partition stage — each TLD in its own isolated session
    #    Failures are non-fatal: that TLD is skipped this flush.
    failed_partition_tlds: set[str] = set()
    for tld in tlds_enabled:
        if not _ensure_partition_isolated(tld):
            failed_partition_tlds.add(tld)

    if failed_partition_tlds:
        logger.warning(
            "certstream batch: partition creation failed for tlds=%s (will retry on next flush)",
            sorted(failed_partition_tlds),
        )

    ingestable = [item for item in enabled if item[1] not in failed_partition_tlds]

    if not ingestable:
        logger.warning(
            "certstream batch: no ingestable domains after partition failures; "
            "raw=%d normalized=%d",
            domains_seen, domains_normalized,
        )
        return {"domains_seen": domains_seen, "domains_inserted": 0, "by_tld": {}}

    # 4. Bulk upsert — caller owns the transaction
    repo = DomainRepository(db)
    by_tld = repo.bulk_upsert_multi_tld(ingestable, now)
    total_inserted = sum(by_tld.values())

    # 5. Update ingestion run metrics
    if run_id:
        run_repo = IngestionRunRepository(db)
        run_repo.add_progress(
            run_id,
            domains_seen_delta=domains_seen,
            domains_inserted_delta=total_inserted,
        )

    # 6. Persist per-TLD stats (cumulative counters on ingestion_tld_policy)
    if by_tld:
        config_repo = IngestionConfigRepository(db)
        config_repo.increment_tld_stats("certstream", dict(by_tld))

    logger.info(
        "certstream batch: source=certstream raw=%d normalized=%d "
        "enabled=%d disabled_tlds=%s partition_failed_tlds=%s upserted=%d",
        domains_seen,
        domains_normalized,
        len(enabled),
        tlds_disabled,
        sorted(failed_partition_tlds),
        total_inserted,
    )

    return {
        "domains_seen": domains_seen,
        "domains_inserted": total_inserted,
        "by_tld": dict(by_tld),
    }


def _apply_certstream_policy(
    normalized: list[tuple[str, str, str]],
) -> tuple[list[tuple], list[str], list[str], list[str]]:
    """Determine which normalized domains are enabled by TLD policy.

    New TLDs (never seen before) are auto-discovered and committed in an
    isolated session — independent of the caller's transaction — so they
    appear in the admin UI immediately.

    Args:
        normalized: List of (name, tld, label) tuples.

    Returns:
        (enabled, all_tlds, enabled_tlds, disabled_tlds)
    """
    tlds_in_batch: set[str] = {tld for _, tld, _ in normalized}

    # First pass: read existing policies (read-only on caller's session is fine,
    # but we use a fresh read here to avoid any session state complications)
    policy_map = _load_policy_map(tlds_in_batch)

    # Auto-discover new TLDs in an isolated, immediately-committed transaction
    new_tlds = {tld for tld in tlds_in_batch if tld not in policy_map}
    if new_tlds:
        _discover_new_tlds_isolated(new_tlds)
        # New TLDs default to enabled=True
        for tld in new_tlds:
            policy_map[tld] = True

    enabled = [item for item in normalized if policy_map.get(item[1], True)]
    all_tlds = sorted(tlds_in_batch)
    enabled_tlds = sorted(t for t in tlds_in_batch if policy_map.get(t, True))
    disabled_tlds = sorted(t for t in tlds_in_batch if not policy_map.get(t, True))

    return enabled, all_tlds, enabled_tlds, disabled_tlds


def _load_policy_map(tlds: set[str]) -> dict[str, bool]:
    """Load TLD policy states from DB in a fresh session. Returns {tld: is_enabled}."""
    db = SessionLocal()
    try:
        repo = IngestionConfigRepository(db)
        result = {}
        for tld in tlds:
            policy = repo.get_tld_policy("certstream", tld)
            if policy is not None:
                result[tld] = policy.is_enabled
        return result
    finally:
        db.close()


def _discover_new_tlds_isolated(new_tlds: set[str]) -> None:
    """Persist new certstream TLD policy rows in an isolated, committed transaction.

    Uses savepoints to handle concurrent inserts from multiple workers gracefully.
    This is called BEFORE the main ingest transaction so new TLDs are visible in
    the admin UI even if the batch fails.
    """
    db = SessionLocal()
    try:
        repo = IngestionConfigRepository(db)
        for tld in sorted(new_tlds):
            sp = db.begin_nested()
            try:
                existing = repo.get_tld_policy("certstream", tld)
                if existing is None:
                    repo.ensure_tld("certstream", tld, is_enabled=True)
                    sp.commit()
                else:
                    sp.rollback()
            except IntegrityError:
                sp.rollback()
                logger.debug(
                    "certstream TLD auto-discovery: concurrent insert for tld=%s, ignoring", tld
                )
        db.commit()
        logger.info(
            "certstream: auto-discovered %d new TLD(s): %s",
            len(new_tlds), sorted(new_tlds),
        )
    except Exception:
        logger.exception("certstream: failed to persist new TLD discoveries; will retry on next flush")
        db.rollback()
    finally:
        db.close()


def _ensure_partition_isolated(tld: str) -> bool:
    """Ensure the domain partition for *tld* exists, using an isolated session.

    Running DDL in a separate session prevents `ensure_partition`'s internal
    commit/rollback from affecting the caller's ingest transaction.

    Returns True on success, False if partition creation failed.
    """
    db = SessionLocal()
    try:
        ensure_partition(db, tld)
        return True
    except Exception:
        logger.warning(
            "certstream: partition creation failed for tld=%s; will retry on next flush", tld
        )
        return False
    finally:
        db.close()


# ── Legacy path (crt.sh and other .br-filtered sources) ─────────────────────

def _ingest_legacy_batch(
    db: Session,
    raw_domains: list[str],
    domains_seen: int,
    now: datetime,
    source: str,
    run_id,
) -> dict:
    # 1. Normalize: filter to .br only (legacy behaviour)
    normalized = normalize_ct_domains(raw_domains)
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
        run_repo.add_progress(
            run_id,
            domains_seen_delta=domains_seen,
            domains_inserted_delta=total_inserted,
        )

    # Caller owns transaction — do NOT commit here.
    logger.info(
        "CT batch ingested: source=%s raw=%d normalized=%d upserted=%d tlds=%s",
        source, domains_seen, domains_normalized, total_inserted, dict(by_tld),
    )

    return {
        "domains_seen": domains_seen,
        "domains_inserted": total_inserted,
        "by_tld": dict(by_tld),
    }
