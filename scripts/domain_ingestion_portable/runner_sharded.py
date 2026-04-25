from __future__ import annotations

import base64
import gzip
import hashlib
import shutil
import tempfile
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import polars as pl
import requests

from .config import PipelineConfig
from .models import SNAPSHOT_COLUMNS
from .runner import _assert_all_tlds_success, _run_openintel
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


def _stable_shard(domain_norm: str, shard_count: int) -> int:
    digest = hashlib.md5(domain_norm.encode("utf-8")).hexdigest()[:8]
    return int(digest, 16) % shard_count


def _stage_prefix(layout: Layout, source: str, tld: str, snapshot_date: date, run_id: str) -> str:
    return f"{layout.prefix}/snapshot_stage/source={source}/tld={tld}/snapshot_date={snapshot_date.isoformat()}/run_id={run_id}"


def _stage_part_key(layout: Layout, source: str, tld: str, snapshot_date: date, run_id: str, shard: int, part: int) -> str:
    return f"{_stage_prefix(layout, source, tld, snapshot_date, run_id)}/shard={shard:04d}/part={part:06d}.parquet"


def _current_shard_key(layout: Layout, source: str, tld: str, shard: int) -> str:
    return f"{layout.path_domains_current}/source={source}/tld={tld}/shard={shard:04d}/current.parquet"


def _new_shard_key(layout: Layout, source: str, tld: str, snapshot_date: date, run_id: str, shard: int) -> str:
    return (
        f"{layout.path_new_domains}/source={source}/snapshot_date={snapshot_date.isoformat()}/"
        f"tld={tld}/shard={shard:04d}/run_id={run_id}.parquet"
    )


def _removed_shard_key(layout: Layout, source: str, tld: str, snapshot_date: date, run_id: str, shard: int) -> str:
    return (
        f"{layout.path_removed_domains}/source={source}/snapshot_date={snapshot_date.isoformat()}/"
        f"tld={tld}/shard={shard:04d}/run_id={run_id}.parquet"
    )


def _download_czds_gz_resumable(czds: CZDSClient, token: str, tld: str, local_path: Path) -> int:
    url = f"{czds.base_url}/czds/downloads/{tld}.zone"
    base_headers = {"Authorization": f"Bearer {token}"}

    with requests.get(url, headers=base_headers, stream=True, timeout=(60, 600), allow_redirects=True) as resp:
        resp.raise_for_status()
        cl = resp.headers.get("Content-Length")
        if not cl or not cl.isdigit():
            raise RuntimeError(f"Missing/invalid Content-Length for .{tld}: {cl}")
        total = int(cl)

    local_path.parent.mkdir(parents=True, exist_ok=True)
    downloaded = local_path.stat().st_size if local_path.exists() else 0

    while downloaded < total:
        req_headers = {"Authorization": f"Bearer {token}", "Range": f"bytes={downloaded}-"}
        try:
            with requests.get(url, headers=req_headers, stream=True, timeout=(60, 600), allow_redirects=True) as resp:
                if resp.status_code not in (200, 206):
                    raise RuntimeError(f"Bad status while resuming .{tld}: {resp.status_code}")
                mode = "ab" if downloaded > 0 else "wb"
                with local_path.open(mode) as f:
                    for chunk in resp.iter_content(chunk_size=8 * 1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
        except Exception:
            time.sleep(3)
            downloaded = local_path.stat().st_size if local_path.exists() else 0
    return total


def _read_many_parquet_keys(storage: R2Storage, keys: list[str]) -> pl.DataFrame:
    if not keys:
        return pl.DataFrame({c: [] for c in SNAPSHOT_COLUMNS})
    dfs: list[pl.DataFrame] = []
    for key in keys:
        raw = storage.get_bytes(key)
        dfs.append(pl.read_parquet(raw))
    return pl.concat(dfs, how="vertical_relaxed") if dfs else pl.DataFrame({c: [] for c in SNAPSHOT_COLUMNS})


def _stage_snapshot_by_shard(
    *,
    storage: R2Storage,
    layout: Layout,
    czds: CZDSClient,
    token: str,
    tld: str,
    snapshot_date: date,
    run_id: str,
    shard_count: int,
    ingest_chunk_rows: int,
) -> int:
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"czds_sharded_{tld}_"))
    local_gz = tmp_dir / f"{tld}.zone.gz"
    try:
        _download_czds_gz_resumable(czds, token, tld, local_gz)

        rows: list[dict[str, str | int]] = []
        part = 0
        total_domains = 0

        def flush() -> None:
            nonlocal rows, part
            if not rows:
                return
            part += 1
            df = pl.DataFrame(rows)
            if df.is_empty():
                rows = []
                return
            grouped = df.partition_by("shard_id", as_dict=True, include_key=True)
            for key, sub in grouped.items():
                shard = int(key[0]) if isinstance(key, tuple) else int(key)
                part_df = sub.drop("shard_id").select(SNAPSHOT_COLUMNS).unique(subset=["domain_norm"], keep="first")
                if part_df.is_empty():
                    continue
                storage.put_parquet_df(
                    _stage_part_key(layout, "czds", tld, snapshot_date, run_id, shard, part),
                    part_df,
                )
            rows = []

        with gzip.open(local_gz, mode="rb") as gz:
            for line in gz:
                s = line.strip()
                if not s or s.startswith(b";"):
                    continue
                tok = s.split(None, 1)
                if not tok:
                    continue
                owner = tok[0].rstrip(b".")
                raw = owner.decode("latin-1")
                norm = raw.lower().strip()
                if norm and norm != tld and norm.endswith("." + tld):
                    rows.append(
                        {
                            "shard_id": _stable_shard(norm, shard_count),
                            "domain_norm": norm,
                            "domain_raw": raw,
                            "domain_raw_b64": base64.b64encode(owner).decode("ascii"),
                        }
                    )
                    total_domains += 1
                if len(rows) >= ingest_chunk_rows:
                    flush()
        flush()
        return total_domains
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _run_czds_sharded(
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
    print(f"CZDS target TLDs={len(tlds)} (sharded mode)")

    for idx, tld in enumerate(tlds, start=1):
        run_id = str(uuid.uuid4())
        started_at = datetime.now(timezone.utc)
        print(f"[CZDS-sharded {idx}/{len(tlds)}] tld={tld} run_id={run_id}")

        if _success_exists(storage, layout, "czds", tld, snapshot_date):
            print("  - skipped (already success)")
            continue

        try:
            snapshot_count = _stage_snapshot_by_shard(
                storage=storage,
                layout=layout,
                czds=czds,
                token=token,
                tld=tld,
                snapshot_date=snapshot_date,
                run_id=run_id,
                shard_count=cfg.runtime.shard_count,
                ingest_chunk_rows=cfg.runtime.ingest_chunk_rows,
            )
            print(f"  - staged domains={snapshot_count:,}")

            total_added = 0
            total_removed = 0
            stage_base = _stage_prefix(layout, "czds", tld, snapshot_date, run_id)

            for shard in range(cfg.runtime.shard_count):
                shard_prefix = f"{stage_base}/shard={shard:04d}/"
                snapshot_keys = storage.list_keys(shard_prefix)
                if not snapshot_keys:
                    continue

                snapshot_df = (
                    _read_many_parquet_keys(storage, snapshot_keys)
                    .select(SNAPSHOT_COLUMNS)
                    .unique(subset=["domain_norm"], keep="first")
                )
                current_df = storage.get_parquet_df_or_empty(
                    _current_shard_key(layout, "czds", tld, shard),
                    columns=[
                        "source",
                        "tld",
                        "domain_norm",
                        "domain_raw",
                        "domain_raw_b64",
                        "domain",
                        "first_seen_date",
                        "last_seen_date",
                        "is_active",
                        "first_seen_run_id",
                        "last_seen_run_id",
                        "updated_at",
                    ],
                )

                result = compute_diff_and_next_current(
                    source="czds",
                    tld=tld,
                    snapshot_date=snapshot_date,
                    run_id=run_id,
                    snapshot_df=snapshot_df,
                    current_df=current_df,
                    max_domains_safety_limit=cfg.runtime.max_domains_safety_limit,
                )

                storage.put_parquet_df(_current_shard_key(layout, "czds", tld, shard), result.next_current_df)
                if result.added_events_df.height > 0:
                    storage.put_parquet_df(
                        _new_shard_key(layout, "czds", tld, snapshot_date, run_id, shard),
                        result.added_events_df,
                    )
                if result.removed_events_df.height > 0:
                    storage.put_parquet_df(
                        _removed_shard_key(layout, "czds", tld, snapshot_date, run_id, shard),
                        result.removed_events_df,
                    )

                total_added += result.added_count
                total_removed += result.removed_count

            run_log_df = build_run_log_df(
                run_id=run_id,
                source="czds",
                tld=tld,
                snapshot_date=snapshot_date,
                started_at=started_at,
                status="success",
                total_snapshot_count=snapshot_count,
                added_count=total_added,
                removed_count=total_removed,
                raw_object_key=None,
                error_message=None,
            )
            storage.put_parquet_df(layout.run_log_key("czds", tld, snapshot_date, run_id), run_log_df)
            _write_success_marker(storage, layout, "czds", tld, snapshot_date, run_id)
            print(f"  - success added={total_added:,} removed={total_removed:,}")

            if cfg.runtime.cleanup_stage_after_success:
                keys = storage.list_keys(stage_base)
                deleted = storage.delete_keys(keys)
                print(f"  - stage cleanup deleted={deleted}")

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
                raw_object_key=None,
                error_message=str(exc),
            )
            storage.put_parquet_df(layout.run_log_key("czds", tld, snapshot_date, run_id), run_log_df)
            print(f"  - error {exc}")


def run_pipeline_sharded(cfg: PipelineConfig) -> None:
    storage = R2Storage(cfg.r2)
    layout = Layout(prefix=cfg.r2.prefix.strip("/"))
    czds = CZDSClient(cfg.czds)
    oi = OpenIntelClient(cfg.openintel)

    print("Testing R2 connectivity...")
    storage.probe_tls()
    storage.probe_api()
    print("R2 probe OK")

    token: str | None = None
    authorized: set[str] = set()
    if cfg.runtime.run_czds:
        print("Testing CZDS connectivity...")
        token = czds.authenticate()
        authorized = czds.authorized_tlds(token)
        print(f"CZDS probe OK. Authorized TLDs={len(authorized)}")

    if cfg.runtime.run_openintel:
        print("Testing OpenINTEL connectivity...")
        oi.probe()
        print("OpenINTEL probe OK")

    if cfg.runtime.run_czds and token is not None:
        _run_czds_sharded(cfg, storage, layout, czds, token, authorized)

    # OpenINTEL stays modular and can run with existing incremental logic.
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
