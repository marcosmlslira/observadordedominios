"""CZDS runner — orchestrates the full CZDS pipeline for a list of TLDs.

Flow per TLD:
1. Check idempotency marker in R2 — skip if already done.
2. Authenticate with CZDS API.
3. Download zone file (gzip).
4. If TLD has >= SHARD_THRESHOLD entries → sharded path.
   Else → in-memory diff path.
5. Write delta + delta_removed Parquet to R2.
6. Overwrite current-state Parquet in R2.
7. Write success marker.
8. Write run log JSON.
"""

from __future__ import annotations

import logging
import traceback
from datetime import date
from time import perf_counter

import polars as pl

from ingestion.config.constants import SHARD_THRESHOLD, SHARD_COUNT
from ingestion.config.settings import Settings
from ingestion.core.diff_engine import simple_diff
from ingestion.core.idempotency import build_marker_payload
from ingestion.core.types import RunKey, RunStats, Source
from ingestion.observability.run_log import build_run_log_payload, now_utc
from ingestion.sources.czds.client import CZDSClient
from ingestion.sources.czds.sharded_stager import run_sharded_czds_diff
from ingestion.storage.layout import Layout
from ingestion.storage.r2 import R2Storage

log = logging.getLogger(__name__)

_SNAP_COLS = ["name", "tld", "label"]


def run_czds_from_env(
    tld: str,
    snapshot_date: str | None = None,
    dry_run: bool = False,
) -> list[RunStats]:
    """Convenience entry point for Databricks notebooks — reads all config from env vars.

    Creates fresh Settings/storage/layout instances (does not use the module-level cache)
    so that credentials injected via os.environ after import are always picked up.
    """
    cfg = Settings()  # always fresh — do NOT call get_settings() here
    storage = R2Storage(cfg)
    layout = Layout(cfg.r2_prefix)
    snap_date = date.fromisoformat(snapshot_date) if snapshot_date else None
    return run_czds(
        cfg=cfg,
        storage=storage,
        layout=layout,
        tlds=[tld],
        snapshot_date=snap_date,
        dry_run=dry_run,
    )


def run_czds(
    *,
    cfg: Settings,
    storage: R2Storage,
    layout: Layout,
    tlds: list[str] | None = None,
    snapshot_date: date | None = None,
    max_tlds: int = 0,
    dry_run: bool = False,
) -> list[RunStats]:
    """Run the CZDS ingestion pipeline and return per-TLD stats."""
    from ingestion.observability.logger import get_logger
    log = get_logger("czds_runner")

    today = snapshot_date or date.today()
    client = CZDSClient(cfg)

    log.info("czds_runner authenticating user=%s", cfg.czds_username)
    auth_started_at = perf_counter()
    token = client.authenticate()
    auth_seconds = perf_counter() - auth_started_at
    log.info("czds_runner auth ok")

    authorized_started_at = perf_counter()
    authorized = client.authorized_tlds(token)
    authorized_seconds = perf_counter() - authorized_started_at
    log.info("czds_runner authorized_tlds count=%d", len(authorized))

    resolved = client.resolve_tlds(
        authorized,
        requested=tlds,
        max_tlds=max_tlds or cfg.czds_max_tlds,
    )
    log.info("czds_runner resolved_tlds count=%d tlds=%s", len(resolved), resolved[:10])

    results: list[RunStats] = []
    for tld in resolved:
        stats = _process_tld(
            tld=tld,
            token=token,
            client=client,
            storage=storage,
            layout=layout,
            snapshot_date=today,
            dry_run=dry_run,
        )
        stats.metadata["auth_seconds"] = round(auth_seconds, 3)
        stats.metadata["authorized_tlds_seconds"] = round(authorized_seconds, 3)
        stats.metadata["authorized_tlds_count"] = len(authorized)
        results.append(stats)
        # Re-authenticate every 50 TLDs (token validity ~24h but be safe)
        if results and len(results) % 50 == 0:
            try:
                token = client.authenticate()
                log.info("czds_runner re-authenticated after %d tlds", len(results))
            except Exception as exc:
                log.warning("czds_runner re-auth failed: %s", exc)

    return results


def _process_tld(
    *,
    tld: str,
    token: str,
    client: CZDSClient,
    storage: R2Storage,
    layout: Layout,
    snapshot_date: date,
    dry_run: bool,
) -> RunStats:
    run_key = RunKey(source=Source.CZDS, tld=tld, snapshot_date=snapshot_date)
    stats = RunStats(run_key=run_key, started_at=now_utc())
    total_started_at = perf_counter()

    # Idempotency check
    marker = layout.marker_key(Source.CZDS.value, tld, snapshot_date)
    if storage.key_exists(marker):
        log.info("czds tld=%s already_done skipping", tld)
        stats.finished_at = now_utc()
        stats.status = "already_done"
        return stats

    try:
        log.info("czds tld=%s downloading", tld)
        download_started_at = perf_counter()
        gz_bytes = client.download_zone_gz(token, tld)
        download_seconds = perf_counter() - download_started_at
        log.info("czds tld=%s downloaded bytes=%d", tld, len(gz_bytes))
        stats.metadata["download_bytes"] = len(gz_bytes)
        stats.metadata["download_seconds"] = round(download_seconds, 3)

        if dry_run:
            stats.finished_at = now_utc()
            stats.status = "dry_run"
            stats.metadata["total_seconds"] = round(perf_counter() - total_started_at, 3)
            return stats

        # Estimate domain count from zone file size to pick sharding strategy.
        # Uncompressed zone line ≈ 50 bytes → guess ~20:1 ratio for .com.
        # Use a simple heuristic: >200MB gzip ≈ >50M domains.
        use_sharding = len(gz_bytes) > 200 * 1024 * 1024

        if use_sharding:
            log.info("czds tld=%s using sharded path", tld)
            (
                snap_count,
                added,
                removed,
                sharded_metrics,
            ) = run_sharded_czds_diff(
                gz_bytes=gz_bytes,
                tld=tld,
                snapshot_date=snapshot_date,
                storage=storage,
                layout=layout,
                num_shards=SHARD_COUNT,
            )
            stats.metadata.update(sharded_metrics)
        else:
            stats.metadata["strategy"] = "in_memory"
            parse_started_at = perf_counter()
            snap_df = client.parse_zone_gz(gz_bytes, tld)
            parse_seconds = perf_counter() - parse_started_at
            snap_count = len(snap_df)
            log.info("czds tld=%s parsed domains=%d", tld, snap_count)
            stats.metadata["parse_seconds"] = round(parse_seconds, 3)

            curr_key = layout.current_key(Source.CZDS.value, tld)
            current_read_started_at = perf_counter()
            curr_df = storage.get_parquet_df_or_empty(curr_key, _SNAP_COLS)
            current_read_seconds = perf_counter() - current_read_started_at
            stats.metadata["current_read_seconds"] = round(current_read_seconds, 3)

            diff_started_at = perf_counter()
            added_df, removed_df = simple_diff(snap_df, curr_df)
            diff_seconds = perf_counter() - diff_started_at
            added = len(added_df)
            removed = len(removed_df)
            log.info("czds tld=%s added=%d removed=%d", tld, added, removed)
            stats.metadata["diff_seconds"] = round(diff_seconds, 3)

            # Write deltas (name, tld, label) — delta_loader injects added_day from snapshot_date
            write_started_at = perf_counter()
            if added > 0:
                storage.put_parquet_df(layout.delta_key(Source.CZDS.value, tld, snapshot_date), added_df)
            if removed > 0:
                storage.put_parquet_df(layout.delta_removed_key(Source.CZDS.value, tld, snapshot_date), removed_df)

            # Overwrite current
            storage.put_parquet_df(curr_key, snap_df)
            r2_write_seconds = perf_counter() - write_started_at
            stats.metadata["r2_write_seconds"] = round(r2_write_seconds, 3)

        # Write success marker
        marker_payload = build_marker_payload(
            run_key,
            added_count=added,
            removed_count=removed,
            snapshot_count=snap_count,
            timings=stats.metadata,
        )
        marker_write_started_at = perf_counter()
        storage.put_json(marker, marker_payload)
        marker_write_seconds = perf_counter() - marker_write_started_at

        stats.snapshot_count = snap_count
        stats.added_count = added
        stats.removed_count = removed
        stats.finished_at = now_utc()
        stats.status = "ok"
        stats.metadata["marker_write_seconds"] = round(marker_write_seconds, 3)
        stats.metadata["total_seconds"] = round(perf_counter() - total_started_at, 3)

    except Exception as exc:
        stats.finished_at = now_utc()
        stats.status = "error"
        stats.error_message = str(exc)
        stats.metadata["total_seconds"] = round(perf_counter() - total_started_at, 3)
        log.error("czds tld=%s error: %s\n%s", tld, exc, traceback.format_exc())

    return stats
