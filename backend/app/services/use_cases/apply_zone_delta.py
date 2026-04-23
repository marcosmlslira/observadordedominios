"""Use case: apply zone delta — parse zone file and upsert to DB."""

from __future__ import annotations

import gzip
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.repositories.domain_repository import DomainRepository

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50_000
_STAGING_BATCH_SIZE = 100_000      # Larger batches are safe: staging has no GIN index
_LARGE_TLD_THRESHOLD = 10_000_000  # Domains; TLDs above this use the staging path

# TLDs empirically known to exceed _LARGE_TLD_THRESHOLD.  These always use the
# staging path even when pg_class.reltuples is temporarily unavailable (e.g. on
# first boot, connection-pool exhaustion, or a transient autovacuum reset).
_ALWAYS_STAGE_TLDS: frozenset[str] = frozenset({"com", "net", "org", "top"})


def _batch_size_for_tld(tld: str) -> int:
    """Return an adaptive batch size based on TLD domain count from materialized view.

    Uses its own DB session so a query failure never affects the caller's transaction.
    A 2-second lock_timeout prevents hanging if the materialized view is being refreshed.
    """
    from app.infra.db.session import SessionLocal
    db = SessionLocal()
    try:
        db.execute(text("SET LOCAL lock_timeout = '2s'"))
        count = db.execute(
            text('SELECT "count" FROM tld_domain_count_mv WHERE tld = :tld'),
            {"tld": tld},
        ).scalar()
        if count and count > 100_000_000:
            return 25_000   # Very large tables: smaller batches to limit index memory pressure
        if count and count > 10_000_000:
            return 50_000
        if count and count > 1_000_000:
            return 75_000
    except Exception as exc:
        logger.warning("Could not read tld_domain_count_mv for TLD=%s: %s", tld, exc)
    finally:
        db.close()
    return _BATCH_SIZE


def _get_tld_domain_count(tld: str) -> int | None:
    """Return estimated domain count for a TLD from pg_class.reltuples.

    Uses pg_class.reltuples which is updated by ANALYZE/autovacuum — no table
    scan, no locks, always instant.  Accuracy is sufficient for the staging
    threshold decision (we only need to know if count > LARGE_TLD_THRESHOLD).
    """
    from app.infra.db.session import SessionLocal

    table = f"domain_{tld.replace('-', '_').replace('.', '_')}"
    db = SessionLocal()
    try:
        count = db.execute(
            text("SELECT reltuples::bigint FROM pg_class WHERE relname = :t"),
            {"t": table},
        ).scalar()
        return int(count) if count and count > 0 else None
    except Exception as exc:
        logger.warning("Could not read domain count for TLD=%s: %s", tld, exc)
        return None
    finally:
        db.close()


def _should_use_staging(tld: str) -> bool:
    """True when the TLD already has enough domains to benefit from the staging path.

    The staging path skips GIN maintenance for existing domains and only pays
    that cost for net-new rows (~1-2% daily).  On first ingestion the MV is
    empty so this returns False and the direct-upsert path is used instead.
    After the first successful run the MV is refreshed and subsequent daily
    runs use staging, completing in ~30-45 min instead of ~74h for .com.
    """
    if tld in _ALWAYS_STAGE_TLDS:
        logger.info("Staging path: forced for known-large TLD=%s", tld)
        return True
    count = _get_tld_domain_count(tld)
    result = count is not None and count >= _LARGE_TLD_THRESHOLD
    if count is None:
        logger.warning(
            "Staging path: cannot determine domain count for TLD=%s — defaulting to direct upsert",
            tld,
        )
    else:
        logger.info(
            "Staging path for TLD=%s: count=%d threshold=%d → %s",
            tld, count, _LARGE_TLD_THRESHOLD, result,
        )
    return result


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


def _apply_via_staging(
    db: Session,
    zone_file_path: Path,
    tld: str,
    run_id: uuid.UUID,
) -> dict[str, int]:
    """Staging path for large TLDs: load all → merge delta only.

    Phase 1 — Stage load: streams zone file into UNLOGGED domain_stage
    table (no GIN index) in large batches.  ~5-10 min for 160M domains.

    Phase 2 — Merge: inserts only rows that don't exist in domain yet.
    GIN trigram index is updated only for net-new domains (~1-2% daily).
    Subsequent runs complete in ~30-45 min for .com instead of ~74h.

    Trade-off: existing domains are not re-inserted (skip_update policy).
    Removal detection is handled via the ingestion set-diff pipeline.
    """
    ts = datetime.now(timezone.utc)
    repo = DomainRepository(db)
    run_repo = IngestionRunRepository(db)

    # ── Phase 1: Clear old staging rows and load zone file ──────────────
    logger.info("Staging path: clearing old rows for TLD=%s", tld)
    repo.clear_staging(tld)
    db.commit()

    batch: list[str] = []
    total_staged = 0

    for domain_name in _parse_zone_stream(zone_file_path, tld):
        batch.append(domain_name)

        if len(batch) >= _STAGING_BATCH_SIZE:
            repo.bulk_insert_to_staging(batch, tld, ts)
            total_staged += len(batch)
            run_repo.update_progress(run_id, domains_seen=total_staged)
            db.commit()
            batch.clear()

    if batch:
        repo.bulk_insert_to_staging(batch, tld, ts)
        total_staged += len(batch)
        db.commit()

    run_repo.update_progress(run_id, domains_seen=total_staged)
    db.commit()
    logger.info("Stage load complete: %d domains staged for TLD=%s", total_staged, tld)

    # ── Phase 2: Merge net-new rows into domain ──────────────────────────
    logger.info("Starting merge from staging into domain for TLD=%s", tld)
    inserted = repo.merge_from_staging(tld, ts)
    db.commit()
    logger.info(
        "Merge complete: %d new domains inserted for TLD=%s (%.2f%% of %d staged)",
        inserted, tld,
        (inserted / total_staged * 100) if total_staged else 0.0,
        total_staged,
    )

    # ── Phase 3: Clean up staging ────────────────────────────────────────
    repo.clear_staging(tld)
    db.commit()

    return {
        "seen": total_staged,
        "inserted": inserted,
        "reactivated": 0,
        "deleted": 0,
    }


def apply_domain_names_delta(
    db: Session,
    domain_iter,
    *,
    tld: str,
    run_id: uuid.UUID,
) -> dict[str, int]:
    """Batch upsert an iterator of pre-parsed domain names into the domain table.

    Shared by apply_zone_delta (CZDS) and sync_openintel_tld (OpenINTEL).
    The caller is responsible for providing normalised, deduplicated names.
    """
    ts = datetime.now(timezone.utc)
    repo = DomainRepository(db)
    run_repo = IngestionRunRepository(db)

    batch_size = _batch_size_for_tld(tld)
    batch: list[str] = []
    total_parsed = 0

    for domain_name in domain_iter:
        batch.append(domain_name)

        if len(batch) >= batch_size:
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


def apply_zone_delta(
    db: Session,
    *,
    zone_file_path: Path,
    tld: str,
    run_id: uuid.UUID,
) -> dict[str, int]:
    """Parse zone file and apply delta to the domain table.

    Routes to the staging path for large TLDs (>50M existing domains)
    to avoid GIN trigram maintenance on the ~98% of rows that already exist.
    Falls back to direct upsert for small/medium TLDs or on first ingestion.
    """
    if _should_use_staging(tld):
        logger.info(
            "TLD=%s exceeds %dM domains — using staging merge path",
            tld, _LARGE_TLD_THRESHOLD // 1_000_000,
        )
        return _apply_via_staging(db, zone_file_path, tld, run_id)

    return apply_domain_names_delta(
        db,
        _parse_zone_stream(zone_file_path, tld),
        tld=tld,
        run_id=run_id,
    )
