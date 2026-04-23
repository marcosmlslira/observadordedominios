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

from apscheduler.schedulers.blocking import BlockingScheduler

from ingestion.config.settings import get_settings
from ingestion.observability.logger import setup_logging
from ingestion.orchestrator.pipeline import run_cycle

log = logging.getLogger(__name__)

_last_run: dict = {}


# ── HTTP health server ────────────────────────────────────────────────────────


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path in ("/health", "/"):
            body = json.dumps({
                "status": "ok",
                "last_run": _last_run,
                "now": datetime.now(timezone.utc).isoformat(),
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args) -> None:  # silence access log
        pass


def _start_health_server(port: int = 8080) -> None:
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log.info("health server listening on port %d", port)


# ── Scheduled job ─────────────────────────────────────────────────────────────


def _run_daily_cycle() -> None:
    cfg = get_settings()
    log.info("=== daily ingestion cycle starting ===")
    summary: dict = {"started_at": datetime.now(timezone.utc).isoformat()}

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
