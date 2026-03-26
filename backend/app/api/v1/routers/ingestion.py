"""Generic ingestion API — runs, health summary, and checkpoints for ALL sources."""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_admin
from app.infra.db.session import get_db
from app.repositories.ct_bulk_repository import CtBulkRepository
from app.repositories.ingestion_run_repository import IngestionRunRepository
from app.schemas.czds_ingestion import CtBulkChunkResponse
from app.schemas.czds_ingestion import CtBulkJobCreateRequest
from app.schemas.czds_ingestion import CtBulkJobResponse
from app.schemas.czds_ingestion import (
    CheckpointResponse,
    TldCoverageResponse,
    ErrorResponse,
    RunStatusResponse,
    SourceSummaryResponse,
)
from app.services.tld_coverage import resolve_tld_coverages
from app.services.use_cases.bulk_load_crtsh import (
    cancel_bulk_job,
    create_bulk_job,
    list_bulk_chunks,
    list_bulk_jobs,
    resume_bulk_job,
    run_bulk_job,
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
    bulk_repo = CtBulkRepository(run_repo.db)
    active_bulk_job = bulk_repo.get_active_job()
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
            if active_bulk_job:
                row["bulk_job_status"] = active_bulk_job.status
                row["bulk_chunks_total"] = active_bulk_job.total_chunks
                row["bulk_chunks_done"] = active_bulk_job.done_chunks
                row["bulk_chunks_error"] = active_bulk_job.error_chunks
                row["bulk_chunks_pending"] = active_bulk_job.pending_chunks + active_bulk_job.running_chunks
        elif source == "czds":
            row["mode"] = "Serial worker"
            row["status_hint"] = "Processes enabled TLDs one by one in priority order."

        rows.append(row)

    return rows


def _resolve_bulk_statuses(db: Session, tlds: list[str]) -> dict[str, str]:
    repo = CtBulkRepository(db)
    statuses: dict[str, str] = {}
    jobs = repo.list_jobs(limit=20)

    for tld in tlds:
        status = "manual"
        for job in jobs:
            chunks = repo.list_chunks(job.id, limit=100000, target_tld=tld)
            if not chunks:
                continue

            chunk_states = {chunk.status for chunk in chunks}
            if "running" in chunk_states:
                status = "running"
            elif chunk_states & {"pending", "retry"}:
                status = "pending"
            elif "error" in chunk_states:
                status = "error"
            elif chunk_states <= {"done", "split"}:
                status = "complete"
            else:
                status = job.status
            break

        statuses[tld] = status

    return statuses


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
    bulk_statuses = _resolve_bulk_statuses(db, [item.tld for item in resolved])
    coverage_rows = []
    for item in resolved:
        crtsh_cp = checkpoints.get(("crtsh", item.tld))
        coverage_rows.append(
            TldCoverageResponse(
                tld=item.tld,
                effective_source=item.effective_source,
                czds_available=item.czds_available,
                ct_enabled=item.ct_enabled,
                bulk_status=bulk_statuses.get(item.tld, item.bulk_status),
                fallback_reason=item.fallback_reason,
                priority_group=item.priority_group,
                last_ct_stream_seen_at=certstream_seen_at if item.ct_enabled else None,
                last_crtsh_success_at=crtsh_cp.last_successful_run_at if crtsh_cp else None,
            )
        )
    return coverage_rows


def _serialize_bulk_job(job) -> CtBulkJobResponse:
    return CtBulkJobResponse(
        job_id=job.id,
        status=job.status,
        requested_tlds=list(job.requested_tlds or []),
        resolved_tlds=list(job.resolved_tlds or []),
        priority_tlds=list(job.priority_tlds or []),
        dry_run=bool(job.dry_run),
        initiated_by=job.initiated_by,
        started_at=job.started_at,
        finished_at=job.finished_at,
        last_error=job.last_error,
        total_chunks=job.total_chunks,
        pending_chunks=job.pending_chunks,
        running_chunks=job.running_chunks,
        done_chunks=job.done_chunks,
        error_chunks=job.error_chunks,
        total_raw_domains=int(job.total_raw_domains or 0),
        total_inserted_domains=int(job.total_inserted_domains or 0),
    )


def _start_bulk_runner(job_id: UUID) -> None:
    thread = threading.Thread(target=run_bulk_job, args=(job_id,), daemon=True, name=f"ct-bulk-{job_id}")
    thread.start()


@router.get(
    "/ct-bulk/jobs",
    response_model=list[CtBulkJobResponse],
    summary="List crt.sh bulk jobs",
)
def get_ct_bulk_jobs(
    db: Session = Depends(get_db),
):
    del db
    return [_serialize_bulk_job(job) for job in list_bulk_jobs()]


@router.get(
    "/ct-bulk/jobs/{job_id}",
    response_model=CtBulkJobResponse,
    summary="Get a crt.sh bulk job",
)
def get_ct_bulk_job(
    job_id: UUID,
    db: Session = Depends(get_db),
):
    repo = CtBulkRepository(db)
    job = repo.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Bulk job not found")
    repo.refresh_job_metrics(job)
    db.commit()
    return _serialize_bulk_job(job)


@router.get(
    "/ct-bulk/jobs/{job_id}/chunks",
    response_model=list[CtBulkChunkResponse],
    summary="List chunks for a crt.sh bulk job",
)
def get_ct_bulk_chunks(
    job_id: UUID,
    status: str | None = None,
    target_tld: str | None = None,
    db: Session = Depends(get_db),
):
    del db
    return [
        CtBulkChunkResponse(
            chunk_id=chunk.id,
            job_id=chunk.job_id,
            target_tld=chunk.target_tld,
            chunk_key=chunk.chunk_key,
            query_pattern=chunk.query_pattern,
            prefix=chunk.prefix,
            depth=chunk.depth,
            status=chunk.status,
            attempt_count=chunk.attempt_count,
            last_error_type=chunk.last_error_type,
            last_error_excerpt=chunk.last_error_excerpt,
            next_retry_at=chunk.next_retry_at,
            raw_domains=int(chunk.raw_domains or 0),
            inserted_domains=int(chunk.inserted_domains or 0),
            started_at=chunk.started_at,
            finished_at=chunk.finished_at,
        )
        for chunk in list_bulk_chunks(job_id, status=status, target_tld=target_tld)
    ]


@router.post(
    "/ct-bulk/jobs",
    response_model=CtBulkJobResponse,
    status_code=202,
    summary="Start a manual crt.sh bulk job",
)
def start_ct_bulk_job(
    body: CtBulkJobCreateRequest,
    current_admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    del db
    job = create_bulk_job(
        requested_tlds=body.tlds or None,
        dry_run=body.dry_run,
        initiated_by=current_admin,
    )
    _start_bulk_runner(job.id)
    return _serialize_bulk_job(job)


@router.post(
    "/ct-bulk/jobs/{job_id}/resume",
    response_model=CtBulkJobResponse,
    summary="Resume a crt.sh bulk job with failed chunks",
)
def resume_ct_bulk_job(
    job_id: UUID,
    db: Session = Depends(get_db),
):
    del db
    job = resume_bulk_job(job_id)
    _start_bulk_runner(job.id)
    return _serialize_bulk_job(job)


@router.post(
    "/ct-bulk/jobs/{job_id}/cancel",
    response_model=CtBulkJobResponse,
    summary="Cancel a running crt.sh bulk job",
)
def cancel_ct_bulk_job(
    job_id: UUID,
    db: Session = Depends(get_db),
):
    del db
    job = cancel_bulk_job(job_id)
    return _serialize_bulk_job(job)


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
