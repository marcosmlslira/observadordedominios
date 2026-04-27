"""Ingestion scheduler — runs daily at 1 AM UTC-3 (04:00 UTC).

Execution order:
  1. OpenINTEL cycle (all enabled TLDs)
  2. CZDS cycle (all authorized TLDs — .com always last via Databricks)

Health check: HTTP GET /health on port 8080 returns 200 OK.
Manual trigger: HTTP POST /run-now with X-Ingestion-Trigger-Token header.

Graceful shutdown: SIGTERM sets _stop_event so the current TLD finishes its
transaction before exiting. No new TLD is started after the flag is set.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler

from ingestion.config.settings import get_settings
from ingestion.observability.logger import setup_logging
from ingestion.orchestrator.pipeline import run_cycle

log = logging.getLogger(__name__)

_last_run: dict = {}
_run_lock = threading.Lock()
_run_in_progress = False
_current_phase: str | None = None

_stop_event = threading.Event()
_shutting_down = False
_scheduler: Any = None  # set in main() so SIGTERM handler can stop it


def _handle_sigterm(signum: int, frame: Any) -> None:
    global _shutting_down
    _shutting_down = True
    _stop_event.set()
    log.warning("SIGTERM received — graceful shutdown initiated; finishing current TLD then exiting")
    # Unblock BlockingScheduler.start() so the process can exit cleanly
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass


# ── Stale heartbeat watchdog ──────────────────────────────────────────────────


def _start_stale_watchdog(db_url: str, interval: float = 600.0, stale_minutes: int = 60) -> None:
    """Periodic background thread: recover stale runs/cycles every *interval* seconds.

    Runs independently of the active ingestion cycle — safe to call from main().
    """

    def _check() -> None:
        try:
            from ingestion.observability.run_recorder import (  # noqa: PLC0415
                recover_stale_running_cycles,
                recover_stale_running_runs,
            )
            n_cycles = recover_stale_running_cycles(db_url, stale_after_minutes=stale_minutes)
            n_czds = recover_stale_running_runs(db_url, "czds", stale_after_minutes=stale_minutes)
            n_oi = recover_stale_running_runs(db_url, "openintel", stale_after_minutes=stale_minutes)
            if n_cycles or n_czds or n_oi:
                log.warning(
                    "stale watchdog: recovered cycles=%d czds_runs=%d openintel_runs=%d",
                    n_cycles, n_czds, n_oi,
                )
        except Exception as exc:  # noqa: BLE001
            log.warning("stale watchdog error (non-fatal): %s", exc)
        finally:
            t = threading.Timer(interval, _check)
            t.daemon = True
            t.start()

    first = threading.Timer(interval, _check)
    first.daemon = True
    first.start()
    log.info("stale heartbeat watchdog started (interval=%.0fs stale_after=%dm)", interval, stale_minutes)


def _json_response(handler: BaseHTTPRequestHandler, status_code: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload).encode()
    handler.send_response(status_code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


# ── HTTP health server ────────────────────────────────────────────────────────


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/health", "/"):
            cfg = get_settings()
            last_cycle: dict | None = None
            if cfg.database_url:
                try:
                    from ingestion.observability.run_recorder import get_last_cycle
                    last_cycle = get_last_cycle(cfg.database_url)
                except Exception:  # noqa: BLE001
                    last_cycle = _last_run or None
            else:
                last_cycle = _last_run or None

            _json_response(self, 200, {
                "status": "ok",
                "run_in_progress": _run_in_progress,
                "current_phase": _current_phase,
                "shutting_down": _shutting_down,
                "last_cycle": last_cycle,
                "now": datetime.now(timezone.utc).isoformat(),
            })
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self) -> None:
        if self.path != "/run-now":
            self.send_response(404)
            self.end_headers()
            return

        if _shutting_down:
            _json_response(self, 503, {"status": "shutting_down"})
            return

        cfg = get_settings()
        if cfg.manual_trigger_token:
            given_token = self.headers.get("X-Ingestion-Trigger-Token") or ""
            if given_token != cfg.manual_trigger_token:
                _json_response(self, 401, {"status": "unauthorized"})
                return

        if _run_in_progress:
            _json_response(self, 409, {"status": "already_running"})
            return

        threading.Thread(target=lambda: _run_daily_cycle(trigger="manual"), daemon=True).start()
        _json_response(self, 202, {"status": "accepted"})

    def log_message(self, *args) -> None:  # silence access log
        pass


def _start_health_server(port: int = 8080) -> None:
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log.info("health server listening on port %d", port)


# ── Scheduled job ─────────────────────────────────────────────────────────────


def _run_daily_cycle(trigger: str = "schedule") -> None:
    global _run_in_progress, _current_phase
    acquired = _run_lock.acquire(blocking=False)
    if not acquired:
        log.warning("cycle trigger=%s ignored: already running", trigger)
        return

    _run_in_progress = True
    cfg = get_settings()
    log.info("=== daily ingestion cycle starting (trigger=%s) ===", trigger)
    summary: dict = {
        "trigger": trigger,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

def _run_daily_cycle(trigger: str = "schedule") -> None:
    global _run_in_progress, _current_phase
    acquired = _run_lock.acquire(blocking=False)
    if not acquired:
        log.warning("cycle trigger=%s ignored: already running", trigger)
        return

    _run_in_progress = True
    cfg = get_settings()
    log.info("=== daily ingestion cycle starting (trigger=%s) ===", trigger)
    summary: dict = {
        "trigger": trigger,
        "started_at": datetime.now(timezone.utc).isoformat(),
    }

    cycle_id: str | None = None
    if cfg.database_url:
        try:
            from ingestion.observability.run_recorder import (
                close_cycle,
                heartbeat_cycle,
                open_cycle,
                recover_stale_running_cycles,
            )
            recover_stale_running_cycles(cfg.database_url, stale_after_minutes=60)
            cycle_id = open_cycle(cfg.database_url, triggered_by=trigger)
            log.info("cycle tracking started cycle_id=%s", cycle_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("cycle open failed (non-fatal): %s", exc)

    tld_success = tld_failed = tld_skipped = tld_load_only = 0

    def _count_results(results: list) -> None:
        nonlocal tld_success, tld_failed, tld_skipped, tld_load_only
        for r in results:
            if r.status == "ok":
                if getattr(r, "phase", None) and r.phase.value == "load_only":
                    tld_load_only += 1
                else:
                    tld_success += 1
            elif r.status == "skipped":
                tld_skipped += 1
            else:
                tld_failed += 1

    def _heartbeat() -> None:
        if cfg.database_url and cycle_id:
            try:
                heartbeat_cycle(cfg.database_url, cycle_id)
            except Exception:  # noqa: BLE001
                pass

    _hb_timer: threading.Timer | None = None

    def _start_heartbeat(interval: float = 30.0) -> None:
        nonlocal _hb_timer

        def _tick() -> None:
            _heartbeat()
            nonlocal _hb_timer
            _hb_timer = threading.Timer(interval, _tick)
            _hb_timer.daemon = True
            _hb_timer.start()

        _hb_timer = threading.Timer(interval, _tick)
        _hb_timer.daemon = True
        _hb_timer.start()

    def _stop_heartbeat() -> None:
        if _hb_timer:
            _hb_timer.cancel()

    try:
        _start_heartbeat()

        # 1. OpenINTEL first
        if not _stop_event.is_set():
            try:
                _current_phase = "openintel"
                oi_results = run_cycle("openintel", cfg, stop_event=_stop_event)
                _count_results(oi_results)
                summary["openintel"] = {
                    "total": len(oi_results),
                    "ok": sum(1 for r in oi_results if r.status == "ok"),
                    "skipped": sum(1 for r in oi_results if r.status == "skipped"),
                    "errors": sum(1 for r in oi_results if r.status == "error"),
                }
                log.info("openintel done: %s", summary["openintel"])
            except Exception as exc:  # noqa: BLE001
                log.exception("openintel cycle crashed: %s", exc)
                summary["openintel"] = {"error": str(exc)}
        else:
            log.info("openintel skipped (shutting down)")
            summary["openintel"] = {"skipped": "shutting_down"}

        # 2. CZDS next (.com always last inside run_cycle)
        if not _stop_event.is_set():
            try:
                _current_phase = "czds"
                czds_results = run_cycle("czds", cfg, stop_event=_stop_event)
                _count_results(czds_results)
                summary["czds"] = {
                    "total": len(czds_results),
                    "ok": sum(1 for r in czds_results if r.status == "ok"),
                    "skipped": sum(1 for r in czds_results if r.status == "skipped"),
                    "errors": sum(1 for r in czds_results if r.status == "error"),
                }
                log.info("czds done: %s", summary["czds"])
            except Exception as exc:  # noqa: BLE001
                log.exception("czds cycle crashed: %s", exc)
                summary["czds"] = {"error": str(exc)}
        else:
            log.info("czds skipped (shutting down)")
            summary["czds"] = {"skipped": "shutting_down"}

        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        final_status = "interrupted" if _shutting_down else (
            "failed" if tld_failed and not tld_success else "succeeded"
        )
        summary["status"] = final_status
        _last_run.update(summary)
        log.info("=== daily ingestion cycle complete === %s", summary)

        # ── 5.3 cycle duration metric ─────────────────────────────────────────
        try:
            _dur_s = (
                datetime.fromisoformat(summary["finished_at"])
                - datetime.fromisoformat(summary["started_at"])
            ).total_seconds()
            log.info(
                "metric ingestion_cycle_duration_seconds=%.1f status=%s trigger=%s "
                "tld_success=%d tld_failed=%d tld_skipped=%d tld_load_only=%d",
                _dur_s, final_status, trigger,
                tld_success, tld_failed, tld_skipped, tld_load_only,
            )
        except Exception:  # noqa: BLE001
            pass

        if cfg.database_url and cycle_id:
            try:
                close_cycle(
                    cfg.database_url,
                    cycle_id,
                    status=final_status,
                    tld_success=tld_success,
                    tld_failed=tld_failed,
                    tld_skipped=tld_skipped,
                    tld_load_only=tld_load_only,
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("cycle close failed (non-fatal): %s", exc)

        if _shutting_down:
            log.info("graceful shutdown completed after cycle")
            sys.exit(0)
    finally:
        _stop_heartbeat()
        _current_phase = None
        _run_in_progress = False
        _run_lock.release()


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    cfg = get_settings()
    setup_logging(level=cfg.log_level, fmt=cfg.log_format)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    # Boot-time provisioning: create partitions + staging tables for all enabled TLDs
    if cfg.database_url:
        try:
            from ingestion.provisioning.provision_tld import provision_all_tlds
            log.info("provisioning TLDs at boot ...")
            result = provision_all_tlds(cfg.database_url)
            if result.get("skipped"):
                log.info("provision: skipped (advisory lock held by another process)")
            else:
                log.info(
                    "provision: %d TLDs checked, %d tables created, %d errors",
                    result["tlds_processed"],
                    len(result["tables_created"]),
                    len(result["errors"]),
                )
                if result["errors"]:
                    for tld, err in result["errors"]:
                        log.error("provision error tld=%s: %s", tld, err)
        except Exception as exc:  # noqa: BLE001
            log.error("provision failed at boot (non-fatal): %s", exc)

    if cfg.database_url:
        _start_stale_watchdog(cfg.database_url)

    _start_health_server()

    global _scheduler
    scheduler = BlockingScheduler(timezone="UTC")
    _scheduler = scheduler
    # 1 AM UTC-3 = 04:00 UTC
    scheduler.add_job(_run_daily_cycle, "cron", hour=4, minute=0, id="daily_ingestion")
    log.info("scheduler configured — next run at 04:00 UTC (01:00 UTC-3)")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("scheduler stopped")
        sys.exit(0)


if __name__ == "__main__":
    main()

