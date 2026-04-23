"""CLI entrypoint — `python -m ingestion <subcommand> [options]`

Subcommands:
  czds        Download CZDS zone files, diff, write Parquet to R2 (local)
  openintel   Download OpenINTEL snapshots, diff, write Parquet to R2 (local)
  load        Read delta Parquet from R2, bulk-load into PostgreSQL
  submit      Submit ingestion jobs to Databricks (czds | openintel)
  orchestrate Run the full daily ingestion cycle for a source (orchestrator)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from ingestion.config.settings import get_settings
from ingestion.observability.logger import setup_logging
from ingestion.storage.layout import Layout
from ingestion.storage.r2 import R2Storage


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingestion",
        description="Domain ingestion pipeline (CZDS + OpenINTEL → R2 → PostgreSQL)",
    )
    parser.add_argument("--log-level", default=None, help="Override LOG_LEVEL env var")
    parser.add_argument("--log-format", default=None, choices=["json", "text"], help="Override LOG_FORMAT env var")

    sub = parser.add_subparsers(dest="command", required=True)

    # ── czds ──────────────────────────────────────────────────────────────────
    p_czds = sub.add_parser("czds", help="Ingest CZDS zone files")
    p_czds.add_argument("--tlds", help="Comma-separated TLD list (default: all authorized)")
    p_czds.add_argument("--max-tlds", type=int, default=0, help="Limit number of TLDs processed")
    p_czds.add_argument("--snapshot-date", help="Override snapshot date (YYYY-MM-DD, default: today)")
    p_czds.add_argument("--dry-run", action="store_true", help="Download only, skip diff+write")

    # ── openintel ─────────────────────────────────────────────────────────────
    p_oi = sub.add_parser("openintel", help="Ingest OpenINTEL snapshots")
    p_oi.add_argument("--tlds", help="Comma-separated TLD list (default: from OPENINTEL_TLDS env)")
    p_oi.add_argument("--max-tlds", type=int, default=0)
    p_oi.add_argument("--snapshot-date", help="Override snapshot date (YYYY-MM-DD)")
    p_oi.add_argument("--dry-run", action="store_true")

    # ── load ──────────────────────────────────────────────────────────────────
    p_load = sub.add_parser("load", help="Load delta Parquet files from R2 into PostgreSQL")
    p_load.add_argument("--source", required=True, choices=["czds", "openintel"])
    p_load.add_argument("--tlds", required=True, help="Comma-separated TLD list")
    p_load.add_argument("--snapshot-date", required=True, help="Snapshot date (YYYY-MM-DD)")

    # ── submit (Databricks) ───────────────────────────────────────────────────
    p_submit = sub.add_parser("submit", help="Submit ingestion jobs to Databricks")
    submit_sub = p_submit.add_subparsers(dest="source", required=True)

    for _src in ("czds", "openintel"):
        _p = submit_sub.add_parser(_src, help=f"Submit {_src.upper()} ingestion to Databricks")
        _p.add_argument("--tlds", required=True, help="Comma-separated TLD list (one Databricks run per TLD)")
        _p.add_argument("--snapshot-date", default=None, help="Override snapshot date (YYYY-MM-DD)")
        _p.add_argument("--no-wait", action="store_true", help="Return immediately after submitting all runs")
        _p.add_argument("--timeout", type=int, default=7200, help="Per-run timeout in seconds (default: 7200)")
        _p.add_argument("--no-serverless", action="store_true", help="Use a new cluster instead of serverless compute")

    # ── orchestrate ───────────────────────────────────────────────────────────
    p_orch = sub.add_parser(
        "orchestrate",
        help="Run the full daily ingestion cycle (idempotent, error-isolated per TLD)",
    )
    p_orch.add_argument("--source", required=True, choices=["czds", "openintel"])
    p_orch.add_argument("--snapshot-date", default=None, help="Override snapshot date (YYYY-MM-DD)")

    return parser


def _parse_tlds(value: str | None) -> list[str] | None:
    if not value:
        return None
    return [t.strip().lower() for t in value.split(",") if t.strip()]


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value)


def _make_storage_and_layout(cfg) -> tuple[R2Storage, Layout]:
    storage = R2Storage(cfg)
    layout = Layout(cfg.r2_prefix)
    return storage, layout


def cmd_czds(args: argparse.Namespace) -> int:
    from ingestion.databricks.submitter import LARGE_TLDS
    from ingestion.runners.czds_runner import run_czds

    tld_list = _parse_tlds(args.tlds) or []
    large = [t for t in tld_list if t in LARGE_TLDS]
    if large:
        print(
            f"ERROR: TLD(s) {large} are too large for local execution.\n"
            "Use `ingestion submit czds --tlds=<tld>` to run on Databricks.",
            file=sys.stderr,
        )
        return 1

    cfg = get_settings()
    storage, layout = _make_storage_and_layout(cfg)
    results = run_czds(
        cfg=cfg,
        storage=storage,
        layout=layout,
        tlds=tld_list or None,
        snapshot_date=_parse_date(args.snapshot_date),
        max_tlds=args.max_tlds,
        dry_run=args.dry_run,
    )
    for r in results:
        print(json.dumps({
            "tld": r.run_key.tld,
            "status": r.status,
            "snapshot": r.snapshot_count,
            "added": r.added_count,
            "removed": r.removed_count,
            "error": r.error_message,
        }, ensure_ascii=False))
    errors = sum(1 for r in results if r.status == "error")
    return 1 if errors else 0


def cmd_openintel(args: argparse.Namespace) -> int:
    from ingestion.databricks.submitter import LARGE_TLDS
    from ingestion.runners.openintel_runner import run_openintel

    tld_list = _parse_tlds(args.tlds) or []
    large = [t for t in tld_list if t in LARGE_TLDS]
    if large:
        print(
            f"ERROR: TLD(s) {large} are too large for local execution.\n"
            "Use `ingestion submit openintel --tlds=<tld>` to run on Databricks.",
            file=sys.stderr,
        )
        return 1

    cfg = get_settings()
    storage, layout = _make_storage_and_layout(cfg)
    results = run_openintel(
        cfg=cfg,
        storage=storage,
        layout=layout,
        tlds=tld_list or None,
        snapshot_date=_parse_date(args.snapshot_date),
        max_tlds=args.max_tlds,
        dry_run=args.dry_run,
    )
    for r in results:
        print(json.dumps({
            "tld": r.run_key.tld,
            "status": r.status,
            "snapshot": r.snapshot_count,
            "added": r.added_count,
            "removed": r.removed_count,
            "error": r.error_message,
        }, ensure_ascii=False))
    errors = sum(1 for r in results if r.status == "error")
    return 1 if errors else 0


def cmd_submit(args: argparse.Namespace) -> int:
    from ingestion.config.settings import get_settings as _gs
    from ingestion.databricks.submitter import DatabricksSubmitter

    cfg = _gs()
    if not cfg.databricks_host or not cfg.databricks_token:
        print(
            "ERROR: DATABRICKS_HOST and DATABRICKS_TOKEN must be set to submit jobs.",
            file=sys.stderr,
        )
        return 1

    submitter = DatabricksSubmitter(cfg)
    tlds = _parse_tlds(args.tlds) or []
    if not tlds:
        print("ERROR: --tlds is required", file=sys.stderr)
        return 1

    wait = not args.no_wait
    use_serverless = not args.no_serverless
    errors = 0
    for tld in tlds:
        print(f"Submitting {args.source.upper()} job for .{tld} …")
        try:
            result = submitter.submit(
                source=args.source,
                tld=tld,
                snapshot_date=args.snapshot_date,
                serverless=use_serverless,
                wait=wait,
                timeout_seconds=args.timeout,
            )
            print(json.dumps(result, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            print(json.dumps({"tld": tld, "status": "error", "error": str(exc)}, ensure_ascii=False))
            errors += 1
    return 1 if errors else 0


def cmd_orchestrate(args: argparse.Namespace) -> int:
    from ingestion.orchestrator.pipeline import run_cycle

    cfg = get_settings()
    snapshot_date = args.snapshot_date or None
    results = run_cycle(args.source, cfg, snapshot_date=snapshot_date)
    for r in results:
        print(json.dumps({
            "tld": r.tld,
            "phase": r.phase.value,
            "status": r.status,
            "domains_inserted": r.domains_inserted,
            "domains_deleted": r.domains_deleted,
            "domains_seen": r.domains_seen,
            "error": r.error,
        }, ensure_ascii=False))
    errors = sum(1 for r in results if r.status == "error")
    return 1 if errors else 0


def cmd_load(args: argparse.Namespace) -> int:
    from ingestion.loader.delta_loader import load_delta
    cfg = get_settings()
    if not cfg.database_url:
        print("ERROR: DATABASE_URL is not set", file=sys.stderr)
        return 1
    storage, layout = _make_storage_and_layout(cfg)
    tlds = _parse_tlds(args.tlds) or []
    for tld in tlds:
        result = load_delta(
            database_url=cfg.database_url,
            storage=storage,
            layout=layout,
            source=args.source,
            tld=tld,
            snapshot_date=args.snapshot_date,
        )
        print(json.dumps({"tld": tld, **result}, ensure_ascii=False))
    return 0


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    cfg = get_settings()
    setup_logging(
        level=args.log_level or cfg.log_level,
        fmt=args.log_format or cfg.log_format,
    )
    dispatch = {
        "czds": cmd_czds,
        "openintel": cmd_openintel,
        "load": cmd_load,
        "submit": cmd_submit,
        "orchestrate": cmd_orchestrate,
    }
    handler = dispatch.get(args.command)
    if handler is None:
        parser.print_help()
        sys.exit(1)
    sys.exit(handler(args))


if __name__ == "__main__":
    main()
