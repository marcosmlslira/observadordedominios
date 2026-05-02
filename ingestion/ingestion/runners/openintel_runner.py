"""OpenINTEL runner — orchestrates OpenINTEL ingestion for a list of TLDs."""

from __future__ import annotations

import logging
import traceback
from datetime import date
from time import perf_counter

from ingestion.config.settings import Settings
from ingestion.core.diff_engine import simple_diff
from ingestion.core.idempotency import build_marker_payload
from ingestion.core.types import RunKey, RunStats, Source
from ingestion.observability.run_log import build_run_log_payload, now_utc
from ingestion.sources.openintel.client import OpenIntelClient
from ingestion.storage.layout import Layout
from ingestion.storage.r2 import R2Storage

log = logging.getLogger(__name__)

_SNAP_COLS = ["name", "tld", "label"]


def run_openintel_from_env(
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
    return run_openintel(
        cfg=cfg,
        storage=storage,
        layout=layout,
        tlds=[tld],
        snapshot_date=snap_date,
        dry_run=dry_run,
    )


def run_openintel(
    *,
    cfg: Settings,
    storage: R2Storage,
    layout: Layout,
    tlds: list[str] | None = None,
    snapshot_date: date | None = None,
    max_tlds: int = 0,
    dry_run: bool = False,
) -> list[RunStats]:
    """Run the OpenINTEL ingestion pipeline and return per-TLD stats."""
    today = snapshot_date or date.today()
    client = OpenIntelClient(cfg)

    resolved = tlds or cfg.openintel_tld_list()
    if max_tlds and max_tlds > 0:
        resolved = resolved[:max_tlds]
    log.info("openintel_runner tlds=%s", resolved)

    results: list[RunStats] = []
    for tld in resolved:
        stats = _process_tld(
            cfg=cfg,
            tld=tld,
            client=client,
            storage=storage,
            layout=layout,
            today=today,
            dry_run=dry_run,
        )
        results.append(stats)
    return results


def _process_tld(
    *,
    cfg: Settings,
    tld: str,
    client: OpenIntelClient,
    storage: R2Storage,
    layout: Layout,
    today: date,
    dry_run: bool,
) -> RunStats:
    mode = client.mode_for_tld(tld)
    log.info("openintel tld=%s mode=%s", tld, mode)

    snapshot_date: date | None = None
    try:
        if mode == "zonefile":
            keys, snapshot_date = client.discover_zonefile_snapshot(tld=tld, today=today)
        else:
            keys, snapshot_date = client.discover_web_snapshot(tld=tld, today=today)
    except Exception as exc:
        log.warning("openintel tld=%s discovery error: %s", tld, exc)
        keys = None

    if not keys or snapshot_date is None:
        log.info("openintel tld=%s no snapshot available", tld)
        run_key = RunKey(source=Source.OPENINTEL, tld=tld, snapshot_date=today)
        stats = RunStats(run_key=run_key, started_at=now_utc(), finished_at=now_utc())
        stats.status = "no_snapshot"
        return stats

    run_key = RunKey(source=Source.OPENINTEL, tld=tld, snapshot_date=snapshot_date)
    stats = RunStats(run_key=run_key, started_at=now_utc())

    marker = layout.marker_key(Source.OPENINTEL.value, tld, snapshot_date)
    if storage.key_exists(marker):
        log.info("openintel tld=%s already_done skipping", tld)
        stats.finished_at = now_utc()
        stats.status = "already_done"
        return stats

    total_started_at = perf_counter()
    try:
        if dry_run:
            stats.finished_at = now_utc()
            stats.status = "dry_run"
            return stats

        log.info("openintel tld=%s parsing snapshot_date=%s mode=%s", tld, snapshot_date, mode)

        if mode == "zonefile":
            total_bytes = client.total_zonefile_keys_size(keys)
            stats.metadata["snapshot_bytes"] = total_bytes
            stats.metadata["snapshot_keys"] = len(keys)
            use_sharding = total_bytes >= cfg.openintel_shard_threshold_bytes
            log.info(
                "openintel tld=%s zonefile_bytes=%d threshold=%d sharding=%s",
                tld, total_bytes, cfg.openintel_shard_threshold_bytes, use_sharding,
            )

            if use_sharding:
                snap_count, added, removed, sharded_metrics = (
                    client.parse_zonefile_snapshot_streaming(
                        keys=keys,
                        tld=tld,
                        snapshot_date=snapshot_date,
                        storage=storage,
                        layout=layout,
                    )
                )
                stats.metadata.update(sharded_metrics)
                log.info(
                    "openintel tld=%s sharded snapshot=%d added=%d removed=%d",
                    tld, snap_count, added, removed,
                )
            else:
                snap_df = client.parse_zonefile_snapshot(keys=keys, tld=tld)
                snap_count, added, removed = _in_memory_diff_and_write(
                    snap_df=snap_df,
                    tld=tld,
                    snapshot_date=snapshot_date,
                    storage=storage,
                    layout=layout,
                    stats=stats,
                )
        else:
            snap_df = client.parse_web_snapshot(
                url=keys[0], tld=tld, snapshot_date=snapshot_date
            )
            snap_count, added, removed = _in_memory_diff_and_write(
                snap_df=snap_df,
                tld=tld,
                snapshot_date=snapshot_date,
                storage=storage,
                layout=layout,
                stats=stats,
            )

        marker_payload = build_marker_payload(
            run_key,
            added_count=added,
            removed_count=removed,
            snapshot_count=snap_count,
        )
        storage.put_json(marker, marker_payload)

        stats.snapshot_count = snap_count
        stats.added_count = added
        stats.removed_count = removed
        stats.finished_at = now_utc()
        stats.status = "ok"
        stats.metadata["total_seconds"] = round(perf_counter() - total_started_at, 3)

    except Exception as exc:
        stats.finished_at = now_utc()
        stats.status = "error"
        stats.error_message = str(exc)
        stats.metadata["total_seconds"] = round(perf_counter() - total_started_at, 3)
        log.error("openintel tld=%s error: %s\n%s", tld, exc, traceback.format_exc())

    return stats


def _in_memory_diff_and_write(
    *,
    snap_df,
    tld: str,
    snapshot_date: date,
    storage: R2Storage,
    layout: Layout,
    stats: RunStats,
) -> tuple[int, int, int]:
    """Legacy in-memory path — kept for small zonefile snapshots and the cctld-web mode."""
    stats.metadata["strategy"] = "in_memory"
    snap_count = len(snap_df)
    log.info("openintel tld=%s parsed domains=%d", tld, snap_count)

    curr_key = layout.current_key(Source.OPENINTEL.value, tld)
    curr_df = storage.get_parquet_df_or_empty(curr_key, _SNAP_COLS)

    added_df, removed_df = simple_diff(snap_df, curr_df)
    added = len(added_df)
    removed = len(removed_df)
    log.info("openintel tld=%s added=%d removed=%d", tld, added, removed)

    if added > 0:
        storage.put_parquet_df(
            layout.delta_key(Source.OPENINTEL.value, tld, snapshot_date), added_df
        )
    if removed > 0:
        storage.put_parquet_df(
            layout.delta_removed_key(Source.OPENINTEL.value, tld, snapshot_date),
            removed_df,
        )

    storage.put_parquet_df(curr_key, snap_df)
    return snap_count, added, removed
