"""Generic ingestion API — runs, health summary, and checkpoints for ALL sources."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_admin
from app.infra.db.session import get_db
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.repositories.czds_policy_repository import CzdsPolicyRepository
from app.schemas.czds_ingestion import (
    CheckpointResponse,
    CycleStatusResponse,
    HealthSummary,
    IngestionCycleStatusResponse,
    ScheduleEntry,
    TldCoverageResponse,
    ErrorResponse,
    RunStatusResponse,
    SourceSummaryResponse,
)
from app.services.tld_coverage import resolve_tld_coverages

router = APIRouter(
    prefix="/v1/ingestion",
    tags=["Ingestion"],
    dependencies=[Depends(get_current_admin)],
)

SUMMARY_SOURCE_ORDER = ("czds", "certstream", "crtsh", "openintel")


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
        elif source == "czds":
            row["mode"] = "Serial worker"
            row["status_hint"] = "Processes enabled TLDs one by one in priority order."
        elif source == "openintel":
            row["mode"] = "Daily cron"
            row["next_expected_run_hint"] = _next_cron_hint(settings.OPENINTEL_SYNC_CRON)
            if row["running_now"] > 0:
                row["status_hint"] = "OpenINTEL batch is running now."
            elif row["last_run_at"]:
                row["status_hint"] = "OpenINTEL runs only on its daily cron."
            else:
                row["status_hint"] = "OpenINTEL is scheduled and waiting for the next daily cron."

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
    tld: str | None = None,
    db: Session = Depends(get_db),
):
    """Return ingestion runs, optionally filtered by source and/or status."""
    run_repo = IngestionRunRepository(db)
    runs = run_repo.list_runs(limit=limit, offset=offset, source=source, status=status, tld=tld)

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
    "/cycle-status",
    response_model=IngestionCycleStatusResponse,
    summary="CZDS cycle progress, schedules, and health",
)
def get_cycle_status(
    db: Session = Depends(get_db),
):
    """Derive the CZDS cycle state from existing run + policy data."""
    policy_repo = CzdsPolicyRepository(db)
    run_repo = IngestionRunRepository(db)

    all_policies = policy_repo.list_all()
    enabled_policies = [p for p in all_policies if p.is_enabled]
    total_tlds = len(enabled_policies)

    # Find today's CZDS runs (since midnight UTC or earliest running)
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    czds_runs = run_repo.list_runs(limit=500, source="czds")
    today_runs = [r for r in czds_runs if r.started_at >= today_start]

    completed = [r for r in today_runs if r.status == "success"]
    failed = [r for r in today_runs if r.status == "failed"]
    running = [r for r in today_runs if r.status == "running"]

    # Skipped = suspended or in cooldown
    now = datetime.now(timezone.utc)
    suspended_tlds = [
        p for p in enabled_policies
        if p.suspended_until and p.suspended_until > now
    ]

    current_tld = running[0].tld if running else None
    is_active = len(running) > 0
    cycle_started_at = min((r.started_at for r in today_runs), default=None)

    # Average duration of completed runs today
    durations = []
    for r in completed:
        if r.finished_at and r.started_at:
            durations.append((r.finished_at - r.started_at).total_seconds())
    avg_duration = sum(durations) / len(durations) if durations else None

    # Estimate completion
    estimated_completion = None
    if is_active and avg_duration and total_tlds > 0:
        done_count = len(completed) + len(failed)
        remaining = max(0, total_tlds - done_count - len(suspended_tlds))
        if remaining > 0:
            estimated_completion = now + timedelta(seconds=avg_duration * remaining)

    # Health summary across ALL policies (not just today)
    tlds_failing = sum(1 for p in enabled_policies if (p.failure_count or 0) > 0)
    tlds_suspended_count = len(suspended_tlds)
    tlds_ok = total_tlds - tlds_failing - tlds_suspended_count

    # Schedules
    schedules = [
        ScheduleEntry(
            source="czds",
            cron_expression=settings.CZDS_SYNC_CRON,
            next_run_at=_next_cron_hint(settings.CZDS_SYNC_CRON),
            mode="cron",
        ),
        ScheduleEntry(
            source="certstream",
            cron_expression="",
            next_run_at=None,
            mode="realtime",
        ),
        ScheduleEntry(
            source="crtsh",
            cron_expression=settings.CT_CRTSH_SYNC_CRON,
            next_run_at=_next_cron_hint(settings.CT_CRTSH_SYNC_CRON),
            mode="cron",
        ),
        ScheduleEntry(
            source="openintel",
            cron_expression=settings.OPENINTEL_SYNC_CRON,
            next_run_at=_next_cron_hint(settings.OPENINTEL_SYNC_CRON),
            mode="cron",
        ),
    ]

    return IngestionCycleStatusResponse(
        czds_cycle=CycleStatusResponse(
            is_active=is_active,
            total_tlds=total_tlds,
            completed_tlds=len(completed),
            failed_tlds=len(failed),
            skipped_tlds=len(suspended_tlds),
            current_tld=current_tld,
            cycle_started_at=cycle_started_at,
            estimated_completion_at=estimated_completion,
            avg_tld_duration_seconds=avg_duration,
        ),
        schedules=schedules,
        health=HealthSummary(
            total_tlds_enabled=total_tlds,
            tlds_ok=max(0, tlds_ok),
            tlds_suspended=tlds_suspended_count,
            tlds_failing=tlds_failing,
        ),
    )


@router.get(
    "/tld-coverage",
    response_model=list[TldCoverageResponse],
    summary="Effective ingestion source per target TLD",
)
def list_tld_coverage(
    db: Session = Depends(get_db),
):
    run_repo = IngestionRunRepository(db)
    certstream_summary = next(
        (row for row in run_repo.get_source_summary() if row["source"] == "certstream"),
        None,
    )
    certstream_seen_at = None
    if certstream_summary:
        certstream_seen_at = certstream_summary.get("last_run_at") or certstream_summary.get("last_success_at")

    checkpoints = {(cp.source, cp.tld): cp for cp in run_repo.list_checkpoints()}
    resolved = resolve_tld_coverages(db)
    coverage_rows = []
    for item in resolved:
        crtsh_cp = checkpoints.get(("crtsh", item.tld))
        coverage_rows.append(
            TldCoverageResponse(
                tld=item.tld,
                effective_source=item.effective_source,
                czds_available=item.czds_available,
                ct_enabled=item.ct_enabled,
                bulk_status=item.bulk_status,
                fallback_reason=item.fallback_reason,
                priority_group=item.priority_group,
                last_ct_stream_seen_at=certstream_seen_at if item.ct_enabled else None,
                last_crtsh_success_at=crtsh_cp.last_successful_run_at if crtsh_cp else None,
            )
        )
    return coverage_rows


@router.get(
    "/domain-counts",
    summary="Domain count per TLD (from daily materialized view)",
)
def get_domain_counts(
    db: Session = Depends(get_db),
):
    """Read pre-aggregated domain counts from tld_domain_count_mv.

    The view is refreshed once per day at the end of the CZDS catchup cycle.
    Returns an empty list if the view has not been populated yet.
    """
    try:
        rows = db.execute(text(
            "SELECT tld, count FROM tld_domain_count_mv ORDER BY count DESC"
        )).fetchall()
    except Exception:
        # View may not exist yet (before first migration run)
        return []
    return [{"tld": r.tld, "count": int(r.count)} for r in rows]


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
