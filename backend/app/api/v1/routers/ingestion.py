"""Generic ingestion API — runs, health summary, and checkpoints for ALL sources."""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_admin
from app.infra.db.session import get_db
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.schemas.czds_ingestion import (
    CheckpointResponse,
    ErrorResponse,
    RunStatusResponse,
    SourceSummaryResponse,
)

router = APIRouter(
    prefix="/v1/ingestion",
    tags=["Ingestion"],
    dependencies=[Depends(get_current_admin)],
)

SUMMARY_SOURCE_ORDER = ("czds", "certstream", "crtsh", "crtsh-bulk")


def _next_cron_hint(cron_expr: str) -> str | None:
    try:
        from apscheduler.triggers.cron import CronTrigger

        trigger = CronTrigger.from_crontab(cron_expr, timezone=timezone.utc)
        now = datetime.now(timezone.utc)
        next_fire = trigger.get_next_fire_time(None, now)
        if not next_fire:
            return None
        local_dt = next_fire.astimezone(ZoneInfo("America/Sao_Paulo"))
        return local_dt.isoformat()
    except Exception:
        parts = cron_expr.split()
        if len(parts) != 5:
            return None
        minute, hour, day, month, weekday = parts
        if any(part == "*" for part in (day, month, weekday)):
            if minute.isdigit() and hour.isdigit():
                now = datetime.now(timezone.utc)
                candidate = now.replace(
                    hour=int(hour),
                    minute=int(minute),
                    second=0,
                    microsecond=0,
                )
                if candidate <= now:
                    from datetime import timedelta

                    candidate = candidate + timedelta(days=1)
                return candidate.astimezone(ZoneInfo("America/Sao_Paulo")).isoformat()
        return None


def _build_source_summary_rows(run_repo: IngestionRunRepository) -> list[dict]:
    indexed = {row["source"]: row for row in run_repo.get_source_summary()}
    rows: list[dict] = []

    for source in SUMMARY_SOURCE_ORDER:
        row = {
            "source": source,
            "total_runs": 0,
            "successful_runs": 0,
            "failed_runs": 0,
            "running_now": 0,
            "last_run_at": None,
            "last_success_at": None,
            "last_status": None,
            "total_domains_seen": 0,
            "total_domains_inserted": 0,
            "mode": None,
            "status_hint": None,
            "next_expected_run_hint": None,
        }
        row.update(indexed.get(source, {}))

        if source == "certstream":
            row["mode"] = "Realtime stream"
            if row["running_now"] > 0:
                row["status_hint"] = "Streaming continuously from CertStream."
            elif row["last_success_at"]:
                row["status_hint"] = "Last CertStream session finished cleanly."
            else:
                row["status_hint"] = "No CertStream session completed yet."
        elif source == "crtsh":
            row["mode"] = "Daily cron"
            row["next_expected_run_hint"] = _next_cron_hint(settings.CT_CRTSH_SYNC_CRON)
            if row["running_now"] > 0:
                row["status_hint"] = "crt.sh batch is running now."
            elif row["last_run_at"]:
                row["status_hint"] = "crt.sh runs only on its daily cron."
            else:
                row["status_hint"] = "crt.sh is scheduled and waiting for the next daily cron."
        elif source == "crtsh-bulk":
            row["mode"] = "Manual backfill"
            row["status_hint"] = "Manual historical backfill. No automatic scheduler."
        elif source == "czds":
            row["mode"] = "Serial worker"
            row["status_hint"] = "Processes enabled TLDs one by one in priority order."

        rows.append(row)

    return rows


@router.get(
    "/runs",
    response_model=list[RunStatusResponse],
    summary="List ingestion runs from all sources",
)
def list_runs(
    limit: int = 50,
    offset: int = 0,
    source: str | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
):
    """Return ingestion runs, optionally filtered by source and/or status."""
    run_repo = IngestionRunRepository(db)
    runs = run_repo.list_runs(limit=limit, offset=offset, source=source, status=status)

    return [
        RunStatusResponse(
            run_id=run.id,
            source=run.source,
            tld=run.tld,
            status=run.status,
            started_at=run.started_at,
            finished_at=run.finished_at,
            domains_seen=run.domains_seen or 0,
            domains_inserted=run.domains_inserted or 0,
            domains_reactivated=run.domains_reactivated or 0,
            domains_deleted=run.domains_deleted or 0,
            artifact_key=None,
            error_message=run.error_message,
        )
        for run in runs
    ]


@router.get(
    "/runs/{run_id}",
    response_model=RunStatusResponse,
    responses={404: {"model": ErrorResponse}},
    summary="Get a specific ingestion run",
)
def get_run(
    run_id: UUID,
    db: Session = Depends(get_db),
):
    run_repo = IngestionRunRepository(db)
    run = run_repo.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return RunStatusResponse(
        run_id=run.id,
        source=run.source,
        tld=run.tld,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        domains_seen=run.domains_seen or 0,
        domains_inserted=run.domains_inserted or 0,
        domains_reactivated=run.domains_reactivated or 0,
        domains_deleted=run.domains_deleted or 0,
        artifact_key=None,
        error_message=run.error_message,
    )


@router.get(
    "/summary",
    response_model=list[SourceSummaryResponse],
    summary="Aggregated health stats per ingestion source",
)
def get_summary(
    db: Session = Depends(get_db),
):
    """Per-source aggregation: total runs, success/fail counts, last run, totals."""
    run_repo = IngestionRunRepository(db)
    return [SourceSummaryResponse(**row) for row in _build_source_summary_rows(run_repo)]


@router.get(
    "/checkpoints",
    response_model=list[CheckpointResponse],
    summary="Last successful run per source/TLD pair",
)
def list_checkpoints(
    source: str | None = None,
    db: Session = Depends(get_db),
):
    run_repo = IngestionRunRepository(db)
    return [
        CheckpointResponse(
            source=cp.source,
            tld=cp.tld,
            last_successful_run_id=cp.last_successful_run_id,
            last_successful_run_at=cp.last_successful_run_at,
        )
        for cp in run_repo.list_checkpoints(source=source)
    ]
