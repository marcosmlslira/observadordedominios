from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from .config import PipelineConfig
from .state_engine import Layout, build_run_log_df, compute_diff_and_next_current
from .storage import R2Storage
from .sources.czds import CZDSClient
from .sources.openintel import OpenIntelClient


def _write_success_marker(storage: R2Storage, layout: Layout, source: str, tld: str, snapshot_date: date, run_id: str) -> None:
    storage.put_json(
        layout.success_marker_key(source, tld, snapshot_date),
        {
            "source": source,
            "tld": tld,
            "snapshot_date": snapshot_date.isoformat(),
            "run_id": run_id,
            "status": "success",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def _success_exists(storage: R2Storage, layout: Layout, source: str, tld: str, snapshot_date: date) -> bool:
    return storage.key_exists(layout.success_marker_key(source, tld, snapshot_date))


def _assert_all_tlds_success(
    *,
    storage: R2Storage,
    layout: Layout,
    source: str,
    snapshot_date: date,
    tlds: list[str],
) -> None:
    missing = [tld for tld in tlds if not _success_exists(storage, layout, source, tld, snapshot_date)]
    if missing:
        sample = ", ".join(missing[:25])
        tail = "" if len(missing) <= 25 else f" ... (+{len(missing) - 25} more)"
        raise RuntimeError(
            f"{source} completeness check failed for {snapshot_date.isoformat()}. "
            f"missing={len(missing)} tlds: {sample}{tail}"
        )
    print(f"{source} completeness check OK for {snapshot_date.isoformat()} (tlds={len(tlds)})")


def run_pipeline(cfg: PipelineConfig) -> None:
    storage = R2Storage(cfg.r2)
    layout = Layout(prefix=cfg.r2.prefix.strip("/"))
    czds = CZDSClient(cfg.czds)
    oi = OpenIntelClient(cfg.openintel)

    print("Testing R2 connectivity...")
    storage.probe_tls()
    storage.probe_api()
    print("R2 probe OK")

    if cfg.runtime.run_czds:
        print("Testing CZDS connectivity...")
        token = czds.authenticate()
        authorized = czds.authorized_tlds(token)
        print(f"CZDS probe OK. Authorized TLDs={len(authorized)}")
    else:
        token = None
        authorized = set()

    if cfg.runtime.run_openintel:
        print("Testing OpenINTEL connectivity...")
        oi.probe()
        print("OpenINTEL probe OK")

    if cfg.runtime.run_czds:
        _run_czds(cfg, storage, layout, czds, token, authorized)

    if cfg.runtime.run_openintel:
        _run_openintel(cfg, storage, layout, oi)

    if cfg.runtime.enforce_all_tlds_success:
        if cfg.runtime.run_czds:
            czds_snapshot_date = czds.choose_snapshot_date(today=date.today())
            if czds_snapshot_date is not None:
                _assert_all_tlds_success(
                    storage=storage,
                    layout=layout,
                    source="czds",
                    snapshot_date=czds_snapshot_date,
                    tlds=czds.resolve_tlds(authorized),
                )
        if cfg.runtime.run_openintel:
            _assert_all_tlds_success(
                storage=storage,
                layout=layout,
                source="openintel",
                snapshot_date=oi.target_snapshot_date(today=date.today()),
                tlds=oi.tlds,
            )

    if cfg.runtime.raw_retention_days > 0:
        deleted = storage.delete_older_than(layout.path_raw_czds, cfg.runtime.raw_retention_days)
        print(f"CZDS raw retention done. deleted={deleted}")


def _run_czds(
    cfg: PipelineConfig,
    storage: R2Storage,
    layout: Layout,
    czds: CZDSClient,
    token: str,
    authorized: set[str],
) -> None:
    today = date.today()
    snapshot_date = czds.choose_snapshot_date(today=today)
    if snapshot_date is None:
        print("CZDS skipped: snapshot_date before configured start_date")
        return

    tlds = czds.resolve_tlds(authorized)
    print(f"CZDS target TLDs={len(tlds)}")

    for idx, tld in enumerate(tlds, start=1):
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        print(f"[CZDS {idx}/{len(tlds)}] tld={tld} run_id={run_id}")

        if _success_exists(storage, layout, "czds", tld, snapshot_date):
            print("  - skipped (already success)")
            continue

        raw_key = None
        try:
            gz_bytes = czds.download_zone_gz(token, tld)
            raw_key = (
                f"{layout.path_raw_czds}/{tld}/"
                f"{snapshot_date:%Y}/{snapshot_date:%m}/{snapshot_date:%d}/{run_id}/{tld}.zone.gz"
            )
            storage.put_bytes(raw_key, gz_bytes)

            snapshot_df = czds.parse_zone_gz_to_snapshot(gz_bytes, tld)
            current_df = storage.get_parquet_df_or_empty(layout.current_key("czds", tld), columns=[
                "source", "tld", "domain_norm", "domain_raw", "domain_raw_b64", "domain",
                "first_seen_date", "last_seen_date", "is_active", "first_seen_run_id",
                "last_seen_run_id", "updated_at",
            ])

            result = compute_diff_and_next_current(
                source="czds",
                tld=tld,
                snapshot_date=snapshot_date,
                run_id=run_id,
                snapshot_df=snapshot_df,
                current_df=current_df,
                max_domains_safety_limit=cfg.runtime.max_domains_safety_limit,
            )

            storage.put_parquet_df(layout.current_key("czds", tld), result.next_current_df)
            if result.added_events_df.height > 0:
                storage.put_parquet_df(layout.new_domains_key("czds", tld, snapshot_date, run_id), result.added_events_df)
            if result.removed_events_df.height > 0:
                storage.put_parquet_df(layout.removed_domains_key("czds", tld, snapshot_date, run_id), result.removed_events_df)
            if cfg.runtime.save_full_snapshot_on_first_run and result.is_first_snapshot_for_tld:
                storage.put_parquet_df(layout.full_snapshot_key("czds", tld, snapshot_date, run_id), snapshot_df)

            run_log_df = build_run_log_df(
                run_id=run_id,
                source="czds",
                tld=tld,
                snapshot_date=snapshot_date,
                started_at=started_at,
                status="success",
                total_snapshot_count=result.total_snapshot_count,
                added_count=result.added_count,
                removed_count=result.removed_count,
                raw_object_key=raw_key,
                error_message=None,
            )
            storage.put_parquet_df(layout.run_log_key("czds", tld, snapshot_date, run_id), run_log_df)
            _write_success_marker(storage, layout, "czds", tld, snapshot_date, run_id)
            print(f"  - success total={result.total_snapshot_count} added={result.added_count} removed={result.removed_count}")

        except Exception as exc:
            run_log_df = build_run_log_df(
                run_id=run_id,
                source="czds",
                tld=tld,
                snapshot_date=snapshot_date,
                started_at=started_at,
                status="failed",
                total_snapshot_count=None,
                added_count=None,
                removed_count=None,
                raw_object_key=raw_key,
                error_message=str(exc),
            )
            storage.put_parquet_df(layout.run_log_key("czds", tld, snapshot_date, run_id), run_log_df)
            print(f"  - error {exc}")


def _run_openintel(cfg: PipelineConfig, storage: R2Storage, layout: Layout, oi: OpenIntelClient) -> None:
    today = date.today()
    print(f"OpenINTEL target TLDs={len(oi.tlds)}")

    for idx, tld in enumerate(oi.tlds, start=1):
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        source = "openintel"
        mode = oi.mode_for_tld(tld)
        print(f"[OpenINTEL {idx}/{len(oi.tlds)}] tld={tld} mode={mode} run_id={run_id}")

        current_key = layout.current_key(source, tld)
        current_exists = storage.key_exists(current_key)
        prefer_earliest = not current_exists
        start_date = cfg.openintel.start_date

        try:
            if mode == "zonefile":
                refs, snapshot_date = oi.discover_zonefile_snapshot(
                    tld=tld,
                    today=today,
                    prefer_earliest=prefer_earliest,
                    start_date=start_date,
                )
            else:
                refs, snapshot_date = oi.discover_web_snapshot(
                    tld=tld,
                    today=today,
                    prefer_earliest=prefer_earliest,
                    start_date=start_date,
                )

            if not refs or not snapshot_date:
                print("  - no snapshot found")
                run_log_df = build_run_log_df(
                    run_id=run_id,
                    source=source,
                    tld=tld,
                    snapshot_date=today,
                    started_at=started_at,
                    status="failed",
                    total_snapshot_count=None,
                    added_count=None,
                    removed_count=None,
                    raw_object_key=None,
                    error_message="No snapshot found",
                )
                storage.put_parquet_df(layout.run_log_key(source, tld, today, run_id), run_log_df)
                continue

            if _success_exists(storage, layout, source, tld, snapshot_date):
                print("  - skipped (already success)")
                continue

            if mode == "zonefile":
                snapshot_df = oi.parse_zonefile_snapshot(
                    keys=refs,
                    tld=tld,
                    max_files_per_step=cfg.runtime.max_files_per_step,
                )
            else:
                snapshot_df = oi.parse_web_snapshot(url=refs[0], tld=tld, snapshot_date=snapshot_date)

            current_df = storage.get_parquet_df_or_empty(current_key, columns=[
                "source", "tld", "domain_norm", "domain_raw", "domain_raw_b64", "domain",
                "first_seen_date", "last_seen_date", "is_active", "first_seen_run_id",
                "last_seen_run_id", "updated_at",
            ])

            result = compute_diff_and_next_current(
                source=source,
                tld=tld,
                snapshot_date=snapshot_date,
                run_id=run_id,
                snapshot_df=snapshot_df,
                current_df=current_df,
                max_domains_safety_limit=cfg.runtime.max_domains_safety_limit,
            )

            storage.put_parquet_df(current_key, result.next_current_df)
            if result.added_events_df.height > 0:
                storage.put_parquet_df(layout.new_domains_key(source, tld, snapshot_date, run_id), result.added_events_df)
            if result.removed_events_df.height > 0:
                storage.put_parquet_df(layout.removed_domains_key(source, tld, snapshot_date, run_id), result.removed_events_df)
            if cfg.runtime.save_full_snapshot_on_first_run and result.is_first_snapshot_for_tld:
                storage.put_parquet_df(layout.full_snapshot_key(source, tld, snapshot_date, run_id), snapshot_df)

            run_log_df = build_run_log_df(
                run_id=run_id,
                source=source,
                tld=tld,
                snapshot_date=snapshot_date,
                started_at=started_at,
                status="success",
                total_snapshot_count=result.total_snapshot_count,
                added_count=result.added_count,
                removed_count=result.removed_count,
                raw_object_key=None,
                error_message=None,
            )
            storage.put_parquet_df(layout.run_log_key(source, tld, snapshot_date, run_id), run_log_df)
            _write_success_marker(storage, layout, source, tld, snapshot_date, run_id)
            print(f"  - success snapshot={snapshot_date} total={result.total_snapshot_count} added={result.added_count} removed={result.removed_count}")

        except Exception as exc:
            run_log_df = build_run_log_df(
                run_id=run_id,
                source=source,
                tld=tld,
                snapshot_date=today,
                started_at=started_at,
                status="failed",
                total_snapshot_count=None,
                added_count=None,
                removed_count=None,
                raw_object_key=None,
                error_message=str(exc),
            )
            storage.put_parquet_df(layout.run_log_key(source, tld, today, run_id), run_log_df)
            print(f"  - error {exc}")
