"""Ingestion scheduler — runs daily at 1 AM UTC-3 (04:00 UTC).

Execution order:
  1. OpenINTEL cycle (all enabled TLDs)
  2. CZDS cycle (all authorized TLDs — .com always last via Databricks)

Health check: HTTP GET /health on port 8080 returns 200 OK.
"""

from __future__ import annotations

import json
import logging
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
            _json_response(self, 200, {
                "status": "ok",
                "run_in_progress": _run_in_progress,
                "last_run": _last_run,
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
    global _run_in_progress
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

    try:
        # 1. OpenINTEL first
        try:
            oi_results = run_cycle("openintel", cfg)
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

        # 2. CZDS next (.com always last inside run_cycle)
        try:
            czds_results = run_cycle("czds", cfg)
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

        summary["finished_at"] = datetime.now(timezone.utc).isoformat()
        _last_run.update(summary)
        log.info("=== daily ingestion cycle complete === %s", summary)
    finally:
        _run_in_progress = False
        _run_lock.release()


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    cfg = get_settings()
    setup_logging(level=cfg.log_level, fmt=cfg.log_format)

    _start_health_server()

    scheduler = BlockingScheduler(timezone="UTC")
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
