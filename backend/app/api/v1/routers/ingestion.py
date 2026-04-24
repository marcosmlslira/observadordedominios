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
from app.infra.db.session import SessionLocal, get_db
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.repositories.czds_policy_repository import CzdsPolicyRepository
from app.repositories.ingestion_config_repository import IngestionConfigRepository
from app.repositories.openintel_tld_status_repository import OpenintelTldStatusRepository
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
    TldRunMetricsResponse,
    TldRunMetricItem,
    TldStatusItem,
    TldStatusResponse,
    OpenintelStatusResponse,
    OpenintelTldStatusItem,
    OpenintelGlobalCounts,
    OpenintelVisualStatus,
)
from app.services.tld_coverage import get_target_tlds, resolve_tld_coverages

router = APIRouter(
    prefix="/v1/ingestion",
    tags=["Ingestion"],
    dependencies=[Depends(get_current_admin)],
)

SUMMARY_SOURCE_ORDER = ("czds", "certstream", "crtsh", "openintel")


def _build_openintel_visual_status(
    *,
    last_verification_at: datetime | None,
    last_available_snapshot_date,
    last_ingested_snapshot_date,
    last_probe_outcome: str | None,
) -> tuple[OpenintelVisualStatus, str]:
    if last_verification_at is None:
        return "no_data", "Sem dados ainda"

    if last_probe_outcome == "verification_failed":
        return "failed", "Falha na execução"

    if (
        last_available_snapshot_date is not None
        and (
            last_ingested_snapshot_date is None
            or last_ingested_snapshot_date < last_available_snapshot_date
        )
    ):
        return "delayed", "Atrasado"

    if last_probe_outcome == "ingested_new_snapshot":
        return "new_snapshot_ingested", "Novo arquivo ingerido"

    if last_probe_outcome in {"already_ingested", "no_snapshot_available"}:
        return "up_to_date_no_new_snapshot", "Em dia (sem novo arquivo)"

    if (
        last_available_snapshot_date is not None
        and last_ingested_snapshot_date is not None
        and last_ingested_snapshot_date >= last_available_snapshot_date
    ):
        return "up_to_date_no_new_snapshot", "Em dia (sem novo arquivo)"

    return "up_to_date_no_new_snapshot", "Em dia (sem novo arquivo)"


def _build_openintel_overall(
    *, counts: OpenintelGlobalCounts, enabled_total: int
) -> tuple[str, str]:
    if counts.failed > 0:
        return "failed", "Falha na execução em um ou mais TLDs."
    if counts.delayed > 0:
        return "warning", "Existe snapshot mais novo disponível e ainda não ingerido."
    if enabled_total == 0:
        return "healthy", "Nenhum TLD habilitado para OpenINTEL."
    if counts.no_data == enabled_total:
        return "warning", "Aguardando a primeira verificação dos TLDs habilitados."
    if counts.new_snapshot_ingested > 0:
        return "healthy", "OpenINTEL executado com sucesso; snapshots mais recentes já foram ingeridos."
    return "healthy", "Sem arquivo novo no provedor. Último snapshot já ingerido."


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
            row["cron_expression"] = None
            if row["running_now"] > 0:
                row["status_hint"] = "Streaming continuously from CertStream."
            elif row["last_success_at"]:
                row["status_hint"] = "Last CertStream session finished cleanly."
            else:
                row["status_hint"] = "No CertStream session completed yet."
        elif source == "crtsh":
            row["mode"] = "Daily cron"
            row["cron_expression"] = settings.CT_CRTSH_SYNC_CRON
            row["next_expected_run_hint"] = _next_cron_hint(settings.CT_CRTSH_SYNC_CRON)
            if row["running_now"] > 0:
                row["status_hint"] = "crt.sh batch is running now."
            elif row["last_run_at"]:
                row["status_hint"] = "crt.sh runs only on its daily cron."
            else:
                row["status_hint"] = "crt.sh is scheduled and waiting for the next daily cron."
        elif source == "czds":
            row["mode"] = "Daily cron"
            row["cron_expression"] = settings.CZDS_SYNC_CRON
            row["next_expected_run_hint"] = _next_cron_hint(settings.CZDS_SYNC_CRON)
            row["status_hint"] = "Processes enabled TLDs one by one in priority order."
        elif source == "openintel":
            row["mode"] = "Daily cron"
            row["cron_expression"] = settings.OPENINTEL_SYNC_CRON
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
    started_from: datetime | None = None,
    started_to: datetime | None = None,
    db: Session = Depends(get_db),
):
    """Return ingestion runs, optionally filtered by source and/or status."""
    run_repo = IngestionRunRepository(db)
    runs = run_repo.list_runs(
        limit=limit,
        offset=offset,
        source=source,
        status=status,
        tld=tld,
        started_from=started_from,
        started_to=started_to,
    )

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
):
    authorized_czds_tlds = set(get_target_tlds())
    with SessionLocal() as db:
        policy_repo = CzdsPolicyRepository(db)
        policies = {item.tld: item for item in policy_repo.list_all()}
        resolved = resolve_tld_coverages(
            db,
            authorized_czds_tlds=authorized_czds_tlds,
            policies=policies,
    )
    coverage_rows = []
    for item in resolved:
        coverage_rows.append(
            TldCoverageResponse(
                tld=item.tld,
                effective_source=item.effective_source,
                czds_available=item.czds_available,
                ct_enabled=item.ct_enabled,
                bulk_status=item.bulk_status,
                fallback_reason=item.fallback_reason,
                priority_group=item.priority_group,
                last_ct_stream_seen_at=None,
                last_crtsh_success_at=None,
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
    "/tld-run-metrics",
    response_model=list[TldRunMetricsResponse],
    summary="Last N runs per TLD for a given source (single query, replaces per-TLD polling)",
)
def get_tld_run_metrics(
    source: str,
    runs_per_tld: int = 10,
    db: Session = Depends(get_db),
):
    """Return the last `runs_per_tld` runs for every TLD of a given source.

    Uses a single window-function query instead of one query per TLD.
    Intended for the ingestion config page sparkbars.
    """
    run_repo = IngestionRunRepository(db)
    raw = run_repo.get_tld_run_metrics(source, runs_per_tld=runs_per_tld)
    return [
        TldRunMetricsResponse(
            tld=item["tld"],
            runs=[TldRunMetricItem(**r) for r in item["runs"]],
        )
        for item in raw
    ]


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


@router.get(
    "/openintel/status",
    response_model=OpenintelStatusResponse,
    summary="OpenINTEL verification status by TLD",
)
def get_openintel_status(
    db: Session = Depends(get_db),
):
    config_repo = IngestionConfigRepository(db)
    status_repo = OpenintelTldStatusRepository(db)
    policies = config_repo.list_tld_policies("openintel")
    tlds = [policy.tld for policy in policies]
    statuses = {row.tld: row for row in status_repo.list_for_tlds(tlds)}

    items: list[OpenintelTldStatusItem] = []
    counts = OpenintelGlobalCounts()
    last_verification_at: datetime | None = None
    enabled_total = 0

    for policy in policies:
        row = statuses.get(policy.tld)
        status, status_reason = _build_openintel_visual_status(
            last_verification_at=row.last_verification_at if row else None,
            last_available_snapshot_date=row.last_available_snapshot_date if row else None,
            last_ingested_snapshot_date=row.last_ingested_snapshot_date if row else None,
            last_probe_outcome=row.last_probe_outcome if row else None,
        )

        if row and row.last_verification_at and (
            last_verification_at is None or row.last_verification_at > last_verification_at
        ):
            last_verification_at = row.last_verification_at

        if policy.is_enabled:
            enabled_total += 1
            if status == "up_to_date_no_new_snapshot":
                counts.up_to_date_no_new_snapshot += 1
            elif status == "new_snapshot_ingested":
                counts.new_snapshot_ingested += 1
            elif status == "delayed":
                counts.delayed += 1
            elif status == "failed":
                counts.failed += 1
            elif status == "no_data":
                counts.no_data += 1

        items.append(
            OpenintelTldStatusItem(
                tld=policy.tld,
                is_enabled=policy.is_enabled,
                priority=policy.priority,
                last_verification_at=row.last_verification_at if row else None,
                last_available_snapshot_date=row.last_available_snapshot_date if row else None,
                last_ingested_snapshot_date=row.last_ingested_snapshot_date if row else None,
                status=status,
                status_reason=status_reason,
                last_error_message=row.last_error_message if row else None,
            )
        )

    overall_status, overall_message = _build_openintel_overall(
        counts=counts,
        enabled_total=enabled_total,
    )

    return OpenintelStatusResponse(
        source="openintel",
        last_verification_at=last_verification_at,
        overall_status=overall_status,
        overall_message=overall_message,
        status_counts=counts,
        items=items,
    )


# ── GET /v1/ingestion/tld-status ──────────────────────────────────────────────


@router.get("/tld-status", response_model=TldStatusResponse)
def get_tld_status(
    source: str = "czds",
    db: Session = Depends(get_db),
    _admin=Depends(get_current_admin),
):
    """Unified per-TLD status: last run, domains inserted/deleted today, enabled flag."""
    valid_sources = {"czds", "openintel", "certstream"}
    if source not in valid_sources:
        raise HTTPException(status_code=400, detail=f"source must be one of {valid_sources}")

    today_utc = datetime.now(timezone.utc).date()

    rows = db.execute(
        text("""
            SELECT
                p.tld,
                p.is_enabled,
                p.priority,
                r.status        AS last_status,
                r.started_at    AS last_run_at,
                r.error_message,
                COALESCE(r.domains_inserted, 0) AS domains_inserted_today,
                COALESCE(r.domains_deleted, 0)  AS domains_deleted_today
            FROM ingestion_tld_policy p
            LEFT JOIN LATERAL (
                SELECT status, started_at, error_message, domains_inserted, domains_deleted
                FROM ingestion_run
                WHERE source = p.source
                  AND tld = p.tld
                  AND started_at::date = :today
                ORDER BY started_at DESC
                LIMIT 1
            ) r ON true
            WHERE p.source = :source
            ORDER BY p.priority ASC NULLS LAST, p.tld ASC
        """),
        {"source": source, "today": today_utc},
    ).fetchall()

    items: list[TldStatusItem] = []
    for row in rows:
        if row.last_status is None:
            status = "never_run"
        elif row.last_status == "running":
            status = "running"
        elif row.last_status in ("success", "ok"):
            status = "ok"
        else:
            status = "failed"

        items.append(TldStatusItem(
            tld=row.tld,
            source=source,
            is_enabled=row.is_enabled,
            priority=row.priority,
            status=status,
            last_run_at=row.last_run_at,
            last_status=row.last_status,
            domains_inserted_today=row.domains_inserted_today or 0,
            domains_deleted_today=row.domains_deleted_today or 0,
            error_message=row.error_message,
        ))

    return TldStatusResponse(
        source=source,
        items=items,
        total=len(items),
        ok_count=sum(1 for i in items if i.status == "ok"),
        failed_count=sum(1 for i in items if i.status == "failed"),
        running_count=sum(1 for i in items if i.status == "running"),
        never_run_count=sum(1 for i in items if i.status == "never_run"),
    )
