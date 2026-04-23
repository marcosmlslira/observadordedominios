"""Orchestrator pipeline — coordinates the daily ingestion cycle for czds or openintel.

Idempotency phases per (source, tld, date):
  SKIP      — R2 marker exists + success run recorded today in PG → nothing to do
  LOAD_ONLY — R2 marker exists but no success run today in PG → re-load PG from R2
  FULL_RUN  — R2 marker absent → download, diff, write R2, load PG, record

Execution order within run_cycle():
  1. Small TLDs (not in LARGE_TLDS): run locally, error-isolated per TLD
  2. Large TLDs with LOAD_ONLY phase: run locally (no Databricks needed, R2 already has data)
  3. Large TLDs with FULL_RUN phase: submit to Databricks in one batch job per source
     - .com is always solo and always last (czds only)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import TYPE_CHECKING

import psycopg2

if TYPE_CHECKING:
    from ingestion.config.settings import Settings
    from ingestion.storage.layout import Layout
    from ingestion.storage.r2 import R2Storage

from ingestion.databricks.submitter import LARGE_TLDS, DatabricksSubmitter
from ingestion.loader.delta_loader import load_delta
from ingestion.observability.run_recorder import create_run, finish_run

log = logging.getLogger(__name__)


class TldPhase(str, Enum):
    SKIP = "skip"
    LOAD_ONLY = "load_only"
    FULL_RUN = "full_run"


@dataclass
class TldResult:
    tld: str
    phase: TldPhase
    status: str = "ok"      # ok | error | skipped
    domains_inserted: int = 0
    domains_deleted: int = 0
    domains_seen: int = 0
    error: str = ""


# ── Idempotency ───────────────────────────────────────────────────────────────


def check_phase(
    db_url: str,
    storage: "R2Storage",
    layout: "Layout",
    source: str,
    tld: str,
    today: date,
) -> TldPhase:
    """Determine which phase to run for (source, tld, today)."""
    today_str = today.isoformat()
    marker_key = layout.marker_key(source, tld, today_str)

    if not storage.key_exists(marker_key):
        return TldPhase.FULL_RUN

    # Marker exists — check if PG was already loaded successfully today
    if db_url:
        try:
            conn = psycopg2.connect(db_url)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT 1 FROM ingestion_run
                        WHERE source = %s AND tld = %s AND status = 'success'
                          AND started_at::date = %s
                        LIMIT 1
                        """,
                        (source, tld, today_str),
                    )
                    row = cur.fetchone()
            finally:
                conn.close()
            if row:
                return TldPhase.SKIP
        except Exception as exc:  # noqa: BLE001
            log.warning("check_phase db query failed for %s/%s: %s — assuming LOAD_ONLY", source, tld, exc)

    return TldPhase.LOAD_ONLY


# ── TLD list ──────────────────────────────────────────────────────────────────


def get_ordered_tlds(db_url: str, source: str, cfg: "Settings") -> list[str]:
    """Return ordered TLD list: DB (priority column) first, settings fallback."""
    if db_url:
        try:
            conn = psycopg2.connect(db_url)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT tld FROM ingestion_tld_policy
                        WHERE source = %s AND is_enabled = true
                        ORDER BY COALESCE(priority, 999999), tld
                        """,
                        (source,),
                    )
                    rows = cur.fetchall()
            finally:
                conn.close()
            if rows:
                return [r[0] for r in rows]
        except Exception as exc:  # noqa: BLE001
            log.warning("get_ordered_tlds db query failed: %s — falling back to settings", exc)

    # Settings fallback
    if source == "czds":
        tld_list = cfg.czds_tld_list()
        if tld_list is None:
            # "all" means fetch from CZDS API
            from ingestion.sources.czds.client import CZDSClient

            client = CZDSClient(cfg.czds_username, cfg.czds_password)
            urls = client.list_authorized_tlds()
            tld_list = [u.rstrip("/").split("/")[-1].removesuffix(".zone") for u in urls]
        return sorted(tld_list)
    else:
        return cfg.openintel_tld_list()


# ── Local processing ──────────────────────────────────────────────────────────


def _process_tld_local(
    source: str,
    tld: str,
    phase: TldPhase,
    cfg: "Settings",
    storage: "R2Storage",
    layout: "Layout",
    snapshot_date: date,
) -> TldResult:
    """Execute one TLD locally (FULL_RUN or LOAD_ONLY). Isolated — never raises."""
    today_str = snapshot_date.isoformat()
    db_url = cfg.database_url
    run_id: str | None = None

    try:
        if db_url:
            run_id = create_run(db_url, source, tld)

        domains_seen = domains_inserted = domains_deleted = 0

        if phase == TldPhase.FULL_RUN:
            if source == "czds":
                from ingestion.runners.czds_runner import run_czds

                results = run_czds(
                    cfg=cfg,
                    storage=storage,
                    layout=layout,
                    tlds=[tld],
                    snapshot_date=snapshot_date,
                )
            else:
                from ingestion.runners.openintel_runner import run_openintel

                results = run_openintel(
                    cfg=cfg,
                    storage=storage,
                    layout=layout,
                    tlds=[tld],
                    snapshot_date=snapshot_date,
                )

            stats = results[0] if results else None
            if stats and stats.status == "error":
                raise RuntimeError(stats.error_message or "runner returned error status")
            if stats:
                domains_seen = stats.snapshot_count
                domains_inserted = stats.added_count
                domains_deleted = stats.removed_count

        # Load PG for both FULL_RUN (after writing R2) and LOAD_ONLY
        if db_url:
            load_result = load_delta(
                database_url=db_url,
                storage=storage,
                layout=layout,
                source=source,
                tld=tld,
                snapshot_date=today_str,
            )
            # Loader counts are authoritative — override runner estimates
            domains_inserted = load_result.get("added_loaded", domains_inserted)
            domains_deleted = load_result.get("removed_loaded", domains_deleted)

            if run_id:
                finish_run(
                    db_url,
                    run_id,
                    status="success",
                    domains_seen=domains_seen,
                    domains_inserted=domains_inserted,
                    domains_deleted=domains_deleted,
                )

        return TldResult(
            tld=tld,
            phase=phase,
            status="ok",
            domains_seen=domains_seen,
            domains_inserted=domains_inserted,
            domains_deleted=domains_deleted,
        )

    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        log.error("tld=%s source=%s phase=%s error: %s", tld, source, phase.value, err, exc_info=True)
        if run_id and db_url:
            try:
                finish_run(db_url, run_id, status="failed", error_message=err)
            except Exception:  # noqa: BLE001
                pass
        return TldResult(tld=tld, phase=phase, status="error", error=err)


# ── Databricks batch processing ───────────────────────────────────────────────


def _load_tld_from_r2(
    source: str,
    tld: str,
    today_str: str,
    cfg: "Settings",
    storage: "R2Storage",
    layout: "Layout",
    *,
    check_marker: bool = False,
) -> TldResult:
    """Load one TLD from R2 into PG (post-Databricks step). Returns TldResult."""
    db_url = cfg.database_url
    run_id: str | None = None
    try:
        # Check if R2 marker exists when requested (post-Databricks validation)
        if check_marker:
            marker_key = layout.marker_key(source, tld, today_str)
            if not storage.key_exists(marker_key):
                raise RuntimeError(f"R2 marker missing after Databricks run — TLD likely failed in notebook")

        if db_url:
            run_id = create_run(db_url, source, tld)
            load_result = load_delta(
                database_url=db_url,
                storage=storage,
                layout=layout,
                source=source,
                tld=tld,
                snapshot_date=today_str,
            )
            added = load_result.get("added_loaded", 0)
            removed = load_result.get("removed_loaded", 0)
            finish_run(db_url, run_id, status="success", domains_inserted=added, domains_deleted=removed)
            return TldResult(
                tld=tld, phase=TldPhase.FULL_RUN, status="ok",
                domains_inserted=added, domains_deleted=removed,
            )
        else:
            return TldResult(tld=tld, phase=TldPhase.FULL_RUN, status="ok")

    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        log.error("post-databricks pg load failed tld=%s: %s", tld, err, exc_info=True)
        if run_id and db_url:
            try:
                finish_run(db_url, run_id, status="failed", error_message=err)
            except Exception:  # noqa: BLE001
                pass
        return TldResult(tld=tld, phase=TldPhase.FULL_RUN, status="error", error=err)


def _submit_databricks_batch(
    source: str,
    tlds: list[str],
    submitter: DatabricksSubmitter,
    cfg: "Settings",
    storage: "R2Storage",
    layout: "Layout",
    today_str: str,
) -> list[TldResult]:
    """Submit one batch Databricks run for a list of TLDs, then load PG per-TLD."""
    log.info("databricks batch: source=%s tlds=%s", source, tlds)
    results: list[TldResult] = []
    try:
        result = submitter.submit_batch(source, tlds, snapshot_date=today_str, wait=True)
        if result.get("status") != "ok":
            err = f"Databricks batch failed (result_state={result.get('result_state', 'UNKNOWN')})"
            log.error(err)
            for tld in tlds:
                results.append(TldResult(tld=tld, phase=TldPhase.FULL_RUN, status="error", error=err))
            return results
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        log.error("databricks batch submission error: %s", err, exc_info=True)
        for tld in tlds:
            results.append(TldResult(tld=tld, phase=TldPhase.FULL_RUN, status="error", error=err))
        return results

    # Databricks job succeeded — load PG per TLD, checking R2 markers for safety
    for tld in tlds:
        r = _load_tld_from_r2(source, tld, today_str, cfg, storage, layout, check_marker=True)
        results.append(r)
    return results


def _process_large_tlds(
    source: str,
    large_tlds: list[str],
    phases: dict[str, TldPhase],
    cfg: "Settings",
    storage: "R2Storage",
    layout: "Layout",
    snapshot_date: date,
) -> list[TldResult]:
    """Handle all large TLDs: LOAD_ONLY locally, FULL_RUN via Databricks batch."""
    today_str = snapshot_date.isoformat()
    results: list[TldResult] = []

    # LOAD_ONLY: R2 exists, just need to reload PG — do locally, no Databricks
    load_only = [t for t in large_tlds if phases[t] == TldPhase.LOAD_ONLY]
    for tld in load_only:
        log.info("large tld=%s LOAD_ONLY (local)", tld)
        r = _process_tld_local(source, tld, TldPhase.LOAD_ONLY, cfg, storage, layout, snapshot_date)
        results.append(r)

    # FULL_RUN: need Databricks — group non-.com together, .com last (czds only)
    full_run = [t for t in large_tlds if phases[t] == TldPhase.FULL_RUN]
    if not full_run:
        return results

    submitter = DatabricksSubmitter(cfg)

    com_tlds = [t for t in full_run if t == "com"]
    batch_tlds = [t for t in full_run if t != "com"]

    if batch_tlds:
        batch_results = _submit_databricks_batch(
            source, batch_tlds, submitter, cfg, storage, layout, today_str
        )
        results.extend(batch_results)

    # .com: always solo, always last
    for tld in com_tlds:
        log.info("databricks solo: source=%s tld=%s (always last)", source, tld)
        try:
            result = submitter.submit(source, tld, snapshot_date=today_str, wait=True)
            if result.get("status") == "ok":
                r = _load_tld_from_r2(source, tld, today_str, cfg, storage, layout, check_marker=True)
            else:
                err = f"Databricks run failed (result_state={result.get('result_state', 'UNKNOWN')})"
                r = TldResult(tld=tld, phase=TldPhase.FULL_RUN, status="error", error=err)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            log.error("databricks solo tld=%s error: %s", tld, err, exc_info=True)
            r = TldResult(tld=tld, phase=TldPhase.FULL_RUN, status="error", error=err)
        results.append(r)

    return results


# ── Main entry point ──────────────────────────────────────────────────────────


def run_cycle(
    source: str,
    cfg: "Settings",
    *,
    snapshot_date: date | None = None,
) -> list[TldResult]:
    """Run the full ingestion cycle for one source.

    Returns one TldResult per TLD. Errors are isolated — one TLD failure never stops others.
    """
    from ingestion.storage.layout import Layout
    from ingestion.storage.r2 import R2Storage

    today = snapshot_date or date.today()
    storage = R2Storage(cfg)
    layout = Layout(cfg.r2_prefix)
    db_url = cfg.database_url

    all_tlds = get_ordered_tlds(db_url, source, cfg)
    max_tlds = cfg.czds_max_tlds if source == "czds" else cfg.openintel_max_tlds
    if max_tlds:
        all_tlds = all_tlds[:max_tlds]

    small_tlds = [t for t in all_tlds if t not in LARGE_TLDS]
    large_tlds = [t for t in all_tlds if t in LARGE_TLDS]

    log.info(
        "run_cycle source=%s date=%s total=%d small=%d large=%d",
        source, today, len(all_tlds), len(small_tlds), len(large_tlds),
    )

    results: list[TldResult] = []

    # ── Small TLDs: run locally, per-TLD isolation ────────────────────────────
    for tld in small_tlds:
        phase = check_phase(db_url, storage, layout, source, tld, today)
        if phase == TldPhase.SKIP:
            log.info("tld=%s SKIP (already done today)", tld)
            results.append(TldResult(tld=tld, phase=phase, status="skipped"))
            continue
        log.info("tld=%s phase=%s (local)", tld, phase.value)
        r = _process_tld_local(source, tld, phase, cfg, storage, layout, today)
        results.append(r)

    # ── Large TLDs: check phases first, then route appropriately ─────────────
    if large_tlds:
        phases: dict[str, TldPhase] = {}
        pending_large: list[str] = []
        for tld in large_tlds:
            phase = check_phase(db_url, storage, layout, source, tld, today)
            if phase == TldPhase.SKIP:
                log.info("tld=%s SKIP (already done today)", tld)
                results.append(TldResult(tld=tld, phase=phase, status="skipped"))
            else:
                phases[tld] = phase
                pending_large.append(tld)

        if pending_large:
            has_full_run = any(phases[t] == TldPhase.FULL_RUN for t in pending_large)
            if has_full_run and (not cfg.databricks_host or not cfg.databricks_token):
                log.error(
                    "large TLDs %s need Databricks (FULL_RUN) but credentials not set",
                    [t for t in pending_large if phases[t] == TldPhase.FULL_RUN],
                )
                for tld in pending_large:
                    if phases[tld] == TldPhase.FULL_RUN:
                        results.append(TldResult(
                            tld=tld, phase=TldPhase.FULL_RUN, status="error",
                            error="DATABRICKS_HOST/TOKEN not configured",
                        ))
                    else:
                        # LOAD_ONLY can still run locally
                        r = _process_tld_local(source, tld, TldPhase.LOAD_ONLY, cfg, storage, layout, today)
                        results.append(r)
            else:
                large_results = _process_large_tlds(
                    source, pending_large, phases, cfg, storage, layout, today
                )
                results.extend(large_results)

    ok = sum(1 for r in results if r.status == "ok")
    skipped = sum(1 for r in results if r.status == "skipped")
    errors = sum(1 for r in results if r.status == "error")
    log.info("run_cycle done source=%s ok=%d skipped=%d errors=%d", source, ok, skipped, errors)

    # ── Post-cycle: expiration sync + similarity scan trigger ─────────────────
    if db_url:
        tlds_with_new = [r.tld for r in results if r.status == "ok" and r.domains_inserted > 0]
        tlds_with_removed = [r.tld for r in results if r.status == "ok" and r.domains_deleted > 0]
        tlds_to_sync = list(dict.fromkeys(tlds_with_new + tlds_with_removed))  # deduplicated, order preserved

        for tld in tlds_to_sync:
            _sync_expiration_for_tld(db_url, source, tld, today)

        if tlds_with_new:
            _trigger_similarity_scans(db_url, source, tlds_with_new)

    # ── Post-cycle: R2 delta cleanup ──────────────────────────────────────────
    retention_days = getattr(cfg, "r2_retention_days", 7)
    _cleanup_r2_deltas(storage, layout, source, today, retention_days=retention_days)

    return results


# ── Post-cycle helpers ────────────────────────────────────────────────────────


def _sync_expiration_for_tld(db_url: str, source: str, tld: str, today: date) -> None:
    """Propagate domain expiration/reactivation for one TLD into similarity_match."""
    try:
        today_int = int(today.strftime("%Y%m%d"))
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                # Mark expired
                cur.execute(
                    """
                    UPDATE similarity_match sm
                    SET domain_expired_day = dr.removed_day
                    FROM domain_removed dr
                    WHERE sm.domain_name = dr.name
                      AND sm.tld = dr.tld
                      AND sm.tld = %s
                      AND sm.domain_expired_day IS NULL
                    """,
                    (tld,),
                )
                expired = cur.rowcount
                # Reactivate
                cur.execute(
                    """
                    UPDATE similarity_match sm
                    SET domain_expired_day = NULL
                    FROM domain d
                    WHERE sm.domain_name = d.name
                      AND sm.tld = d.tld
                      AND d.tld = %s
                      AND d.added_day = %s
                      AND sm.domain_expired_day IS NOT NULL
                    """,
                    (tld, today_int),
                )
                reactivated = cur.rowcount
                # Clean up domain_removed for reactivated entries
                cur.execute(
                    """
                    DELETE FROM domain_removed dr
                    WHERE dr.tld = %s
                      AND EXISTS (
                          SELECT 1 FROM domain d
                          WHERE d.name = dr.name AND d.tld = dr.tld
                            AND d.added_day = %s
                      )
                    """,
                    (tld, today_int),
                )
            conn.commit()
        finally:
            conn.close()
        log.info("expiration_sync tld=%s expired=%d reactivated=%d", tld, expired, reactivated)
    except Exception as exc:  # noqa: BLE001
        log.warning("expiration_sync failed tld=%s: %s", tld, exc)


def _trigger_similarity_scans(db_url: str, source: str, tlds: list[str]) -> None:
    """Insert delta similarity scan jobs for all active brands after new domains arrive."""
    if not tlds:
        return
    import json
    import uuid as _uuid

    try:
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                # Fetch all active brand IDs
                cur.execute(
                    "SELECT id FROM monitored_brand WHERE is_active = true"
                )
                brand_rows = cur.fetchall()
                if not brand_rows:
                    return

                records = []
                for (brand_id,) in brand_rows:
                    for tld in tlds:
                        records.append((
                            str(_uuid.uuid4()),
                            str(brand_id),
                            tld,
                            json.dumps([tld]),   # effective_tlds
                            json.dumps({}),      # tld_results
                            False,               # force_full
                            "queued",
                            f"ingestion_pipeline/{source}",
                        ))

                cur.executemany(
                    """
                    INSERT INTO similarity_scan_job
                        (id, brand_id, requested_tld, effective_tlds, tld_results,
                         force_full, status, initiated_by, queued_at, created_at, updated_at)
                    VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, now(), now(), now())
                    ON CONFLICT DO NOTHING
                    """,
                    records,
                )
            conn.commit()
        finally:
            conn.close()
        log.info(
            "similarity_scan_trigger source=%s tlds=%d brands=%d jobs_enqueued=%d",
            source, len(tlds), len(brand_rows), len(records),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("similarity_scan_trigger failed: %s", exc)


def _cleanup_r2_deltas(
    storage: "R2Storage",
    layout: "Layout",
    source: str,
    today: date,
    *,
    retention_days: int = 7,
) -> None:
    """Delete delta Parquet files and markers older than retention_days from R2.

    Preserves:
      - current.parquet (needed for next-day diff)
      - today and yesterday (in case of retry)
    """
    from datetime import timedelta

    try:
        cutoff = today - timedelta(days=retention_days)
        prefix = layout.prefix + "/"
        all_keys = storage.list_keys(prefix)
        to_delete = []

        for key in all_keys:
            # Never delete current state files
            if "current.parquet" in key or "/current/" in key:
                continue
            date_str = _extract_date_from_key(key)
            if date_str is None:
                continue
            try:
                file_date = date.fromisoformat(date_str)
            except ValueError:
                continue
            if file_date < cutoff:
                to_delete.append(key)

        if to_delete:
            deleted = storage.delete_keys(to_delete)
            log.info("r2_cleanup source=%s cutoff=%s deleted=%d", source, cutoff.isoformat(), deleted)
    except Exception as exc:  # noqa: BLE001
        log.warning("r2_cleanup failed: %s", exc)


def _extract_date_from_key(key: str) -> str | None:
    """Extract ISO date string from an R2 key path containing snapshot_date=YYYY-MM-DD."""
    marker = "snapshot_date="
    idx = key.find(marker)
    if idx == -1:
        return None
    start = idx + len(marker)
    # Date is 10 chars: YYYY-MM-DD
    return key[start:start + 10] if len(key) >= start + 10 else None
