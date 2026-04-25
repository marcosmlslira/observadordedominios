from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import polars as pl

from .models import CURRENT_COLUMNS, DOMAIN_EVENT_COLUMNS, RUN_COLUMNS, SNAPSHOT_COLUMNS, day_str, text_to_b64

CURRENT_COLUMN_DTYPES = {
    "source": pl.Utf8,
    "tld": pl.Utf8,
    "domain_norm": pl.Utf8,
    "domain_raw": pl.Utf8,
    "domain_raw_b64": pl.Utf8,
    "domain": pl.Utf8,
    "first_seen_date": pl.Utf8,
    "last_seen_date": pl.Utf8,
    "is_active": pl.Boolean,
    "first_seen_run_id": pl.Utf8,
    "last_seen_run_id": pl.Utf8,
    "updated_at": pl.Utf8,
}


def empty_current_df() -> pl.DataFrame:
    data = {
        c: pl.Series(name=c, values=[], dtype=CURRENT_COLUMN_DTYPES[c])
        for c in CURRENT_COLUMNS
    }
    return pl.DataFrame(data).select(CURRENT_COLUMNS)


@dataclass(frozen=True)
class Layout:
    prefix: str

    @property
    def path_raw_czds(self) -> str:
        return f"{self.prefix}/raw/czds"

    @property
    def path_new_domains(self) -> str:
        return f"{self.prefix}/new_domains"

    @property
    def path_removed_domains(self) -> str:
        return f"{self.prefix}/removed_domains"

    @property
    def path_full_snapshots(self) -> str:
        return f"{self.prefix}/full_snapshots"

    @property
    def path_domains_current(self) -> str:
        return f"{self.prefix}/domains_current"

    @property
    def path_ingestion_runs(self) -> str:
        return f"{self.prefix}/ingestion_runs"

    @property
    def path_markers(self) -> str:
        return f"{self.prefix}/markers"

    def current_key(self, source: str, tld: str) -> str:
        return f"{self.path_domains_current}/source={source}/tld={tld}/current.parquet"

    def new_domains_key(self, source: str, tld: str, snapshot_date: date, run_id: str) -> str:
        return f"{self.path_new_domains}/source={source}/snapshot_date={day_str(snapshot_date)}/tld={tld}/run_id={run_id}.parquet"

    def removed_domains_key(self, source: str, tld: str, snapshot_date: date, run_id: str) -> str:
        return f"{self.path_removed_domains}/source={source}/snapshot_date={day_str(snapshot_date)}/tld={tld}/run_id={run_id}.parquet"

    def full_snapshot_key(self, source: str, tld: str, snapshot_date: date, run_id: str) -> str:
        return f"{self.path_full_snapshots}/source={source}/snapshot_date={day_str(snapshot_date)}/tld={tld}/run_id={run_id}.parquet"

    def run_log_key(self, source: str, tld: str, snapshot_date: date, run_id: str) -> str:
        return f"{self.path_ingestion_runs}/source={source}/snapshot_date={day_str(snapshot_date)}/tld={tld}/run_id={run_id}.parquet"

    def success_marker_key(self, source: str, tld: str, snapshot_date: date) -> str:
        return f"{self.path_markers}/source={source}/tld={tld}/snapshot_date={day_str(snapshot_date)}/success.json"


def normalize_snapshot_df(snapshot_df: pl.DataFrame) -> pl.DataFrame:
    cols = set(snapshot_df.columns)
    if "domain_norm" not in cols:
        if "domain" in cols:
            snapshot_df = snapshot_df.with_columns(pl.col("domain").cast(pl.Utf8).alias("domain_norm"))
        else:
            raise RuntimeError("snapshot must contain 'domain_norm' or 'domain'")

    if "domain_raw" not in snapshot_df.columns:
        snapshot_df = snapshot_df.with_columns(pl.col("domain_norm").alias("domain_raw"))
    if "domain_raw_b64" not in snapshot_df.columns:
        snapshot_df = snapshot_df.with_columns(
            pl.col("domain_raw").map_elements(text_to_b64, return_dtype=pl.Utf8).alias("domain_raw_b64")
        )

    return (
        snapshot_df
        .select(SNAPSHOT_COLUMNS)
        .with_columns(pl.col("domain_norm").cast(pl.Utf8).str.strip_chars().str.to_lowercase())
        .filter(pl.col("domain_norm") != "")
        .unique(subset=["domain_norm"], keep="first")
    )


def _normalize_current(current_df: pl.DataFrame) -> pl.DataFrame:
    if current_df.is_empty():
        return empty_current_df()

    if "domain_norm" not in current_df.columns and "domain" in current_df.columns:
        current_df = current_df.with_columns(pl.col("domain").cast(pl.Utf8).alias("domain_norm"))
    if "domain_raw" not in current_df.columns and "domain_norm" in current_df.columns:
        current_df = current_df.with_columns(pl.col("domain_norm").alias("domain_raw"))
    if "domain_raw_b64" not in current_df.columns and "domain_raw" in current_df.columns:
        current_df = current_df.with_columns(
            pl.col("domain_raw").map_elements(text_to_b64, return_dtype=pl.Utf8).alias("domain_raw_b64")
        )
    if "domain" not in current_df.columns and "domain_norm" in current_df.columns:
        current_df = current_df.with_columns(pl.col("domain_norm").alias("domain"))

    for c in CURRENT_COLUMNS:
        if c not in current_df.columns:
            current_df = current_df.with_columns(pl.lit(None, dtype=CURRENT_COLUMN_DTYPES[c]).alias(c))
    return current_df.select(CURRENT_COLUMNS)


@dataclass
class DiffResult:
    next_current_df: pl.DataFrame
    added_events_df: pl.DataFrame
    removed_events_df: pl.DataFrame
    total_snapshot_count: int
    added_count: int
    removed_count: int
    is_first_snapshot_for_tld: bool


def compute_diff_and_next_current(
    source: str,
    tld: str,
    snapshot_date: date,
    run_id: str,
    snapshot_df: pl.DataFrame,
    current_df: pl.DataFrame,
    max_domains_safety_limit: int,
) -> DiffResult:
    snapshot_df = normalize_snapshot_df(snapshot_df)
    current_df = _normalize_current(current_df)
    is_first_snapshot_for_tld = current_df.height == 0

    now_iso = datetime.now(timezone.utc).isoformat()
    snapshot_date_iso = snapshot_date.isoformat()

    current_active = current_df.filter(pl.col("is_active") == True).select(["domain_norm"])
    added_df = snapshot_df.join(current_active, on="domain_norm", how="anti")
    removed_df = current_df.filter(pl.col("is_active") == True).join(
        snapshot_df.select(["domain_norm"]), on="domain_norm", how="anti"
    )

    snapshot_with_prev = snapshot_df.join(
        current_df.select(["domain_norm", "first_seen_date", "first_seen_run_id"]),
        on="domain_norm",
        how="left",
    )

    active_rows = (
        snapshot_with_prev
        .with_columns(
            pl.lit(source).alias("source"),
            pl.lit(tld).alias("tld"),
            pl.col("domain_norm").alias("domain"),
            pl.coalesce([pl.col("first_seen_date"), pl.lit(snapshot_date_iso)]).alias("first_seen_date"),
            pl.lit(snapshot_date_iso).alias("last_seen_date"),
            pl.lit(True).alias("is_active"),
            pl.coalesce([pl.col("first_seen_run_id"), pl.lit(run_id)]).alias("first_seen_run_id"),
            pl.lit(run_id).alias("last_seen_run_id"),
            pl.lit(now_iso).alias("updated_at"),
        )
        .select(CURRENT_COLUMNS)
    )

    inactive_rows = (
        current_df
        .join(snapshot_df.select(["domain_norm"]), on="domain_norm", how="anti")
        .with_columns(
            pl.col("domain_norm").alias("domain"),
            pl.when(pl.col("is_active") == True).then(pl.lit(snapshot_date_iso)).otherwise(pl.col("last_seen_date")).alias("last_seen_date"),
            pl.when(pl.col("is_active") == True).then(pl.lit(run_id)).otherwise(pl.col("last_seen_run_id")).alias("last_seen_run_id"),
            pl.when(pl.col("is_active") == True).then(pl.lit(now_iso)).otherwise(pl.col("updated_at")).alias("updated_at"),
            pl.lit(False).alias("is_active"),
        )
        .select(CURRENT_COLUMNS)
    )

    next_current_df = pl.concat([active_rows, inactive_rows], how="vertical").unique(subset=["domain_norm"], keep="last")

    added_events = (
        added_df
        .with_columns(
            pl.lit(source).alias("source"),
            pl.lit(tld).alias("tld"),
            pl.lit(snapshot_date_iso).alias("snapshot_date"),
            pl.col("domain_norm").alias("domain"),
            pl.lit(run_id).alias("run_id"),
            pl.lit(now_iso).alias("processed_at"),
        )
        .select(DOMAIN_EVENT_COLUMNS)
    )

    removed_events = (
        removed_df
        .with_columns(
            pl.lit(source).alias("source"),
            pl.lit(tld).alias("tld"),
            pl.lit(snapshot_date_iso).alias("snapshot_date"),
            pl.col("domain_norm").alias("domain"),
            pl.lit(run_id).alias("run_id"),
            pl.lit(now_iso).alias("processed_at"),
        )
        .select(DOMAIN_EVENT_COLUMNS)
    )

    total_snapshot_count = snapshot_df.height
    if total_snapshot_count > max_domains_safety_limit:
        raise RuntimeError(
            f"snapshot too large ({total_snapshot_count:,} > {max_domains_safety_limit:,})"
        )

    return DiffResult(
        next_current_df=next_current_df,
        added_events_df=added_events,
        removed_events_df=removed_events,
        total_snapshot_count=total_snapshot_count,
        added_count=added_events.height,
        removed_count=removed_events.height,
        is_first_snapshot_for_tld=is_first_snapshot_for_tld,
    )


def build_run_log_df(
    *,
    run_id: str,
    source: str,
    tld: str,
    snapshot_date: date,
    started_at: datetime,
    status: str,
    total_snapshot_count: int | None,
    added_count: int | None,
    removed_count: int | None,
    raw_object_key: str | None,
    error_message: str | None,
) -> pl.DataFrame:
    row = {
        "run_id": run_id,
        "source": source,
        "tld": tld,
        "snapshot_date": snapshot_date.isoformat(),
        "started_at": started_at.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "total_snapshot_count": total_snapshot_count,
        "added_count": added_count,
        "removed_count": removed_count,
        "raw_object_key": raw_object_key,
        "error_message": error_message,
    }
    return pl.DataFrame([row]).select(RUN_COLUMNS)
