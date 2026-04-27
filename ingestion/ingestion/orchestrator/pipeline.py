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
import threading
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import TYPE_CHECKING

import psycopg2

if TYPE_CHECKING:
    from ingestion.config.settings import Settings
    from ingestion.storage.layout import Layout
    from ingestion.storage.r2 import R2Storage

from ingestion.databricks.submitter import LARGE_TLDS, DatabricksSubmitter
from ingestion.loader.delta_loader import load_delta
from ingestion.observability.run_recorder import (
    create_run,
    finish_run,
    recover_stale_running_runs,
    touch_run,
)

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

_MARKER_LOOKBACK_DAYS = 7  # OpenINTEL lags up to ~4 days; 7 gives a safe margin


def _find_latest_marker_date(
    storage: "R2Storage",
    layout: "Layout",
    source: str,
    tld: str,
    today: date,
    lookback_days: int = _MARKER_LOOKBACK_DAYS,
) -> str | None:
    """Scan back from today to find the most recent R2 marker for (source, tld).

    OpenINTEL data typically lags 2-5 days behind the current date, so we must
    look back instead of only checking today's date.

    Returns the ISO date string of the latest marker found, or None.
    """
    for days_back in range(lookback_days):
        check_date = (today - timedelta(days=days_back)).isoformat()
        mk = layout.marker_key(source, tld, check_date)
        if storage.key_exists(mk):
            if days_back > 0:
                log.debug("marker found at %s for %s/%s (today=%s)", check_date, source, tld, today.isoformat())
            return check_date
    return None


def check_phase(
    db_url: str,
    storage: "R2Storage",
    layout: "Layout",
    source: str,
    tld: str,
    today: date,
) -> TldPhase:
    """Determine which phase to run for (source, tld, today)."""
    # Look back up to MARKER_LOOKBACK_DAYS — OpenINTEL lags behind current date
    marker_date = _find_latest_marker_date(storage, layout, source, tld, today)

    if marker_date is None:
        return TldPhase.FULL_RUN

    # Marker exists — check if PG was already loaded for this exact snapshot_date
    if db_url:
        try:
            conn = psycopg2.connect(db_url)
            try:
                with conn.cursor() as cur:
                    # Precise check: match by snapshot_date (added in migration 033).
                    # Fall back to a time-window check for older rows that predate the column.
                    cur.execute(
                        """
                        SELECT 1 FROM ingestion_run
                        WHERE source = %s AND tld = %s AND status = 'success'
                          AND (
                            snapshot_date = %s::date
                            OR (snapshot_date IS NULL AND started_at::date = %s::date)
                          )
                        LIMIT 1
                        """,
                        (source, tld, marker_date, marker_date),
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


def _log_mem(tld: str, source: str, phase: str, label: str, rss_start_kb: int | None = None) -> int | None:
    """Log current RSS memory and return current rss_kb (Linux/macOS only; no-op on Windows)."""
    try:
        import resource  # noqa: PLC0415
        rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if rss_start_kb is not None:
            log.debug(
                "mem[%s] tld=%s source=%s phase=%s rss_kb=%d delta_kb=%+d",
                label, tld, source, phase, rss_kb, rss_kb - rss_start_kb,
            )
        else:
            log.debug("mem[%s] tld=%s source=%s phase=%s rss_kb=%d", label, tld, source, phase, rss_kb)
        return rss_kb
    except Exception:  # noqa: BLE001
        return None


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
    _mem_start = _log_mem(tld, source, phase.value, "start")

    try:
        if db_url:
            run_id = create_run(db_url, source, tld)
            touch_run(db_url, run_id)

        domains_seen = domains_inserted = domains_deleted = 0

        # snap_str tracks the actual snapshot date to use for load_delta.
        # For FULL_RUN, the runner discovers the real snapshot date (which may lag
        # several days behind today for OpenINTEL). For LOAD_ONLY, we look back in R2.
        snap_str = today_str

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
            if stats and stats.status == "no_snapshot":
                if run_id and db_url:
                    finish_run(
                        db_url,
                        run_id,
                        status="failed",
                        reason_code="no_snapshot",
                        error_message="No snapshot available for this TLD/date",
                    )
                return TldResult(
                    tld=tld,
                    phase=phase,
                    status="skipped",
                )
            if stats:
                domains_seen = stats.snapshot_count
                domains_inserted = stats.added_count
                domains_deleted = stats.removed_count
                # Use the actual snapshot date the runner resolved (may differ from today)
                snap_str = stats.run_key.snapshot_date.isoformat()
            if run_id and db_url:
                touch_run(db_url, run_id)

        elif phase == TldPhase.LOAD_ONLY:
            # Find the latest marker to know which snapshot date to load from R2
            actual_date = _find_latest_marker_date(storage, layout, source, tld, snapshot_date)
            if actual_date is not None:
                snap_str = actual_date
            else:
                log.warning("LOAD_ONLY tld=%s but no marker found — will attempt today_str", tld)
            if run_id and db_url:
                touch_run(db_url, run_id)

        # Load PG for both FULL_RUN (after writing R2) and LOAD_ONLY
        if db_url:
            load_result = load_delta(
                database_url=db_url,
                storage=storage,
                layout=layout,
                source=source,
                tld=tld,
                snapshot_date=snap_str,
            )
            # Loader counts are authoritative — override runner estimates
            domains_inserted = load_result.get("added_loaded", domains_inserted)
            domains_deleted = load_result.get("removed_loaded", domains_deleted)

            # ── D2: Map loader status to reason_code ─────────────────────
            _load_status = load_result.get("status", "ok")
            if _load_status == "partial":
                _run_status, _run_reason = "success", "partial_load_added_only"
                log.warning(
                    "partial load tld=%s source=%s added=%d removed=0 (%s)",
                    tld, source, domains_inserted, load_result.get("removed_error", ""),
                )
            elif _load_status == "recovered":
                _run_status, _run_reason = "success", "partial_load_recovered"
            else:
                _run_status, _run_reason = "success", "success"

            if run_id:
                finish_run(
                    db_url,
                    run_id,
                    status=_run_status,
                    reason_code=_run_reason,
                    domains_seen=domains_seen,
                    domains_inserted=domains_inserted,
                    domains_deleted=domains_deleted,
                    snapshot_date=snap_str,
                )

            # ── A3: Reconcile openintel_tld_status after successful load ──
            if source == "openintel":
                _reconcile_openintel_status(db_url, tld, snap_str)

        _log_mem(tld, source, phase.value, "end", _mem_start)
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
        _log_mem(tld, source, phase.value, "error", _mem_start)
        if run_id and db_url:
            try:
                finish_run(
                    db_url,
                    run_id,
                    status="failed",
                    reason_code="unexpected_error",
                    error_message=err,
                )
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
    existing_run_id: str | None = None,
) -> TldResult:
    """Load one TLD from R2 into PG (post-Databricks step). Returns TldResult."""
    db_url = cfg.database_url
    run_id: str | None = existing_run_id
    try:
        # Find the actual snapshot date from R2 markers (OpenINTEL lags 2-5 days)
        snap_str = today_str
        if check_marker:
            today = date.fromisoformat(today_str)
            actual_date = _find_latest_marker_date(storage, layout, source, tld, today)
            if actual_date is None:
                raise RuntimeError("R2 marker missing after Databricks run — TLD likely failed in notebook")
            if actual_date != today_str:
                log.info("_load_tld_from_r2 tld=%s using marker_date=%s (requested %s)", tld, actual_date, today_str)
            snap_str = actual_date

            # ── B3: Validate Databricks artefact contract ─────────────────
            # Marker present but no parquets = notebook wrote partial results.
            # Fail fast with a clear reason_code so the caller can distinguish
            # "Databricks job reported success but nothing was written" from
            # regular PG load failures.
            delta_prefix = layout.delta_tld_date_prefix("delta", source, tld, snap_str)
            delta_key = layout.delta_key(source, tld, snap_str)
            from ingestion.loader.delta_loader import _list_parquet_keys  # noqa: PLC0415
            parquet_keys = _list_parquet_keys(storage, delta_prefix, delta_key)
            if not parquet_keys:
                raise RuntimeError(
                    f"R2 marker present (snapshot={snap_str}) but no delta parquets found"
                    f" — Databricks notebook completed without writing data (databricks_contract_violation)"
                )
            log.debug("B3 artefact check: tld=%s snapshot=%s parquets=%d", tld, snap_str, len(parquet_keys))

        if db_url:
            if run_id is None:
                run_id = create_run(db_url, source, tld)
            touch_run(db_url, run_id)
            load_result = load_delta(
                database_url=db_url,
                storage=storage,
                layout=layout,
                source=source,
                tld=tld,
                snapshot_date=snap_str,
            )
            added = load_result.get("added_loaded", 0)
            removed = load_result.get("removed_loaded", 0)

            # ── D2: Map loader status to reason_code ─────────────────────
            load_status = load_result.get("status", "ok")
            if load_status == "partial":
                run_reason = "partial_load_added_only"
                log.warning(
                    "partial load tld=%s source=%s: added=%d removed=0 (%s)",
                    tld, source, added, load_result.get("removed_error", ""),
                )
            elif load_status == "recovered":
                run_reason = "partial_load_recovered"
            else:
                run_reason = "success"

            finish_run(
                db_url,
                run_id,
                status="success",
                reason_code=run_reason,
                domains_inserted=added,
                domains_deleted=removed,
                snapshot_date=snap_str,
            )
            # ── A3: Reconcile openintel_tld_status after successful load ──
            if source == "openintel":
                _reconcile_openintel_status(db_url, tld, snap_str)
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
                if "databricks_contract_violation" in err:
                    reason_code = "databricks_contract_violation"
                elif "marker missing" in err.lower():
                    reason_code = "r2_marker_missing"
                else:
                    reason_code = "pg_load_error"
                finish_run(
                    db_url,
                    run_id,
                    status="failed",
                    reason_code=reason_code,
                    error_message=err,
                )
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
    run_ids: dict[str, str] = {}
    if cfg.database_url:
        for tld in tlds:
            try:
                run_id = create_run(cfg.database_url, source, tld)
                run_ids[tld] = run_id
                touch_run(cfg.database_url, run_id)
            except Exception as exc:  # noqa: BLE001
                log.warning("failed to create tracking run for %s/%s: %s", source, tld, exc)

    def _heartbeat() -> None:
        if not cfg.database_url:
            return
        for run_id in run_ids.values():
            try:
                touch_run(cfg.database_url, run_id)
            except Exception:
                pass

    try:
        result = submitter.submit_batch(
            source,
            tlds,
            snapshot_date=today_str,
            wait=True,
            on_poll=_heartbeat,
        )
        if result.get("status") != "ok":
            err = f"Databricks batch failed (result_state={result.get('result_state', 'UNKNOWN')})"
            log.error(err)
            for tld in tlds:
                run_id = run_ids.get(tld)
                if run_id and cfg.database_url:
                    try:
                        finish_run(
                            cfg.database_url,
                            run_id,
                            status="failed",
                            reason_code="databricks_run_error",
                            error_message=err,
                        )
                    except Exception:
                        pass
                results.append(TldResult(tld=tld, phase=TldPhase.FULL_RUN, status="error", error=err))
            return results
    except Exception as exc:  # noqa: BLE001
        err = str(exc)
        log.error("databricks batch submission error: %s", err, exc_info=True)
        for tld in tlds:
            run_id = run_ids.get(tld)
            if run_id and cfg.database_url:
                try:
                    finish_run(
                        cfg.database_url,
                        run_id,
                        status="failed",
                        reason_code="databricks_submit_error",
                        error_message=err,
                    )
                except Exception:
                    pass
            results.append(TldResult(tld=tld, phase=TldPhase.FULL_RUN, status="error", error=err))
        return results

    # Databricks job succeeded — load PG per TLD, checking R2 markers for safety
    for tld in tlds:
        r = _load_tld_from_r2(
            source,
            tld,
            today_str,
            cfg,
            storage,
            layout,
            check_marker=True,
            existing_run_id=run_ids.get(tld),
        )
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
        # ── B1: chunk batches to avoid OOM and rate-limit ─────────────
        batch_size = cfg.databricks_batch_size_for_source(source)
        for chunk_start in range(0, len(batch_tlds), batch_size):
            chunk = batch_tlds[chunk_start : chunk_start + batch_size]
            log.info(
                "databricks large chunk %d/%d source=%s tlds=%d",
                chunk_start // batch_size + 1,
                (len(batch_tlds) + batch_size - 1) // batch_size,
                source,
                len(chunk),
            )
            batch_results = _submit_databricks_batch(
                source, chunk, submitter, cfg, storage, layout, today_str
            )
            results.extend(batch_results)

    # .com: always solo, always last
    for tld in com_tlds:
        log.info("databricks solo: source=%s tld=%s (always last)", source, tld)
        run_id: str | None = None
        try:
            if cfg.database_url:
                run_id = create_run(cfg.database_url, source, tld)
                touch_run(cfg.database_url, run_id)
            result = submitter.submit(
                source,
                tld,
                snapshot_date=today_str,
                wait=True,
                on_poll=(lambda: run_id and cfg.database_url and touch_run(cfg.database_url, run_id)),
            )
            if result.get("status") == "ok":
                r = _load_tld_from_r2(
                    source,
                    tld,
                    today_str,
                    cfg,
                    storage,
                    layout,
                    check_marker=True,
                    existing_run_id=run_id,
                )
            else:
                err = f"Databricks run failed (result_state={result.get('result_state', 'UNKNOWN')})"
                if run_id and cfg.database_url:
                    finish_run(
                        cfg.database_url,
                        run_id,
                        status="failed",
                        reason_code="databricks_run_error",
                        error_message=err,
                    )
                r = TldResult(tld=tld, phase=TldPhase.FULL_RUN, status="error", error=err)
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            log.error("databricks solo tld=%s error: %s", tld, err, exc_info=True)
            if run_id and cfg.database_url:
                finish_run(
                    cfg.database_url,
                    run_id,
                    status="failed",
                    reason_code="databricks_submit_error",
                    error_message=err,
                )
            r = TldResult(tld=tld, phase=TldPhase.FULL_RUN, status="error", error=err)
        results.append(r)

    return results


# ── Main entry point ──────────────────────────────────────────────────────────


def run_cycle(
    source: str,
    cfg: "Settings",
    *,
    snapshot_date: date | None = None,
    stop_event: threading.Event | None = None,
) -> list[TldResult]:
    """Run the full ingestion cycle for one source.

    Returns one TldResult per TLD. Errors are isolated — one TLD failure never stops others.
    If *stop_event* is set (SIGTERM received), no new TLD is started after the current one finishes.
    """
    from ingestion.storage.layout import Layout
    from ingestion.storage.r2 import R2Storage

    today = snapshot_date or date.today()
    storage = R2Storage(cfg)
    layout = Layout(cfg.r2_prefix)
    db_url = cfg.database_url
    execution_mode = cfg.execution_mode_for_source(source)

    if db_url:
        try:
            recovered = recover_stale_running_runs(
                db_url,
                source,
                stale_after_minutes=cfg.ingestion_stale_timeout_minutes,
            )
            if recovered:
                log.warning(
                    "stale recovery source=%s recovered=%d timeout=%dm",
                    source,
                    recovered,
                    cfg.ingestion_stale_timeout_minutes,
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("stale recovery failed source=%s: %s", source, exc)

    all_tlds = get_ordered_tlds(db_url, source, cfg)
    max_tlds = cfg.czds_max_tlds if source == "czds" else cfg.openintel_max_tlds
    if max_tlds:
        all_tlds = all_tlds[:max_tlds]

    small_tlds = [t for t in all_tlds if t not in LARGE_TLDS]
    large_tlds = [t for t in all_tlds if t in LARGE_TLDS]

    log.info(
        "run_cycle source=%s mode=%s date=%s total=%d small=%d large=%d",
        source, execution_mode, today, len(all_tlds), len(small_tlds), len(large_tlds),
    )

    results: list[TldResult] = []

    if execution_mode == "databricks_only":
        if not cfg.databricks_host or not cfg.databricks_token:
            err = "DATABRICKS_HOST/TOKEN not configured for databricks_only mode"
            for tld in all_tlds:
                results.append(TldResult(tld=tld, phase=TldPhase.FULL_RUN, status="error", error=err))
            return results

        submitter = DatabricksSubmitter(cfg)
        today_str = today.isoformat()
        databricks_targets: list[str] = []
        for tld in all_tlds:
            phase = check_phase(db_url, storage, layout, source, tld, today)
            if phase == TldPhase.SKIP:
                results.append(TldResult(tld=tld, phase=phase, status="skipped"))
                continue
            databricks_targets.append(tld)

        if databricks_targets:
            com_tlds = [t for t in databricks_targets if source == "czds" and t == "com"]
            batch_tlds = [t for t in databricks_targets if t not in com_tlds]
            if batch_tlds:
                # ── B1: chunk batches to avoid OOM and rate-limit ─────────
                batch_size = cfg.databricks_batch_size_for_source(source)
                for chunk_start in range(0, len(batch_tlds), batch_size):
                    chunk = batch_tlds[chunk_start : chunk_start + batch_size]
                    log.info(
                        "databricks chunk %d/%d source=%s tlds=%d",
                        chunk_start // batch_size + 1,
                        (len(batch_tlds) + batch_size - 1) // batch_size,
                        source,
                        len(chunk),
                    )
                    results.extend(
                        _submit_databricks_batch(
                            source,
                            chunk,
                            submitter,
                            cfg,
                            storage,
                            layout,
                            today_str,
                        )
                    )
            for tld in com_tlds:
                run_id: str | None = None
                try:
                    if db_url:
                        run_id = create_run(db_url, source, tld)
                        touch_run(db_url, run_id)
                    result = submitter.submit(
                        source,
                        tld,
                        snapshot_date=today_str,
                        wait=True,
                        on_poll=(lambda: run_id and db_url and touch_run(db_url, run_id)),
                    )
                    if result.get("status") != "ok":
                        err = f"Databricks run failed (result_state={result.get('result_state', 'UNKNOWN')})"
                        if run_id and db_url:
                            finish_run(
                                db_url,
                                run_id,
                                status="failed",
                                reason_code="databricks_run_error",
                                error_message=err,
                            )
                        results.append(TldResult(tld=tld, phase=TldPhase.FULL_RUN, status="error", error=err))
                        continue
                    results.append(
                        _load_tld_from_r2(
                            source,
                            tld,
                            today_str,
                            cfg,
                            storage,
                            layout,
                            check_marker=True,
                            existing_run_id=run_id,
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    err = str(exc)
                    if run_id and db_url:
                        finish_run(
                            db_url,
                            run_id,
                            status="failed",
                            reason_code="databricks_submit_error",
                            error_message=err,
                        )
                    results.append(TldResult(tld=tld, phase=TldPhase.FULL_RUN, status="error", error=err))

        ok = sum(1 for r in results if r.status == "ok")
        skipped = sum(1 for r in results if r.status == "skipped")
        errors = sum(1 for r in results if r.status == "error")
        log.info(
            "run_cycle done source=%s mode=%s ok=%d skipped=%d errors=%d",
            source,
            execution_mode,
            ok,
            skipped,
            errors,
        )
        return results

    # ── Small TLDs: run locally, per-TLD isolation ────────────────────────────
    for tld in small_tlds:
        if stop_event and stop_event.is_set():
            log.info("stop_event set — aborting small TLDs at tld=%s", tld)
            break
        phase = check_phase(db_url, storage, layout, source, tld, today)
        if phase == TldPhase.SKIP:
            log.info("tld=%s SKIP (already done today)", tld)
            results.append(TldResult(tld=tld, phase=phase, status="skipped"))
            continue
        log.info("tld=%s phase=%s (local)", tld, phase.value)
        r = _process_tld_local(source, tld, phase, cfg, storage, layout, today)
        results.append(r)

    # ── Large TLDs: check phases first, then route appropriately ─────────────
    if large_tlds and not (stop_event and stop_event.is_set()):
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


def _reconcile_openintel_status(db_url: str, tld: str, snapshot_date_str: str) -> None:
    """Update openintel_tld_status after a successful canonical pipeline load.

    The legacy ``sync_openintel_tld`` use-case was the only writer of this table,
    but the canonical pipeline never updated it — leaving the ``/admin/ingestion``
    UI stale even after successful loads.  This reconciles the derived status so
    the UI correctly reflects the latest ingestion outcome.
    """
    try:
        snap_date = date.fromisoformat(snapshot_date_str) if isinstance(snapshot_date_str, str) else snapshot_date_str
        conn = psycopg2.connect(db_url)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO openintel_tld_status (
                        tld, last_probe_outcome, last_verification_at,
                        last_available_snapshot_date, last_ingested_snapshot_date,
                        last_error_message, updated_at
                    ) VALUES (
                        %s, 'ingested_new_snapshot', now(),
                        %s, %s,
                        NULL, now()
                    )
                    ON CONFLICT (tld) DO UPDATE SET
                        last_probe_outcome = 'ingested_new_snapshot',
                        last_verification_at = now(),
                        last_available_snapshot_date = EXCLUDED.last_available_snapshot_date,
                        last_ingested_snapshot_date = EXCLUDED.last_ingested_snapshot_date,
                        last_error_message = NULL,
                        updated_at = now()
                    """,
                    (tld, snap_date, snap_date),
                )
            conn.commit()
        finally:
            conn.close()
        log.info("reconciled openintel_tld_status tld=%s snapshot=%s", tld, snapshot_date_str)
    except Exception as exc:  # noqa: BLE001
        log.warning("openintel_tld_status reconciliation failed tld=%s: %s", tld, exc)


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
