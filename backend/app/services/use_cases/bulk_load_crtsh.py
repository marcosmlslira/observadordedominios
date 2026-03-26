"""Resumable crt.sh historical bulk loader with persistent chunk tracking."""

from __future__ import annotations

import json
import logging
import string
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.models.ct_bulk_chunk import CtBulkChunk
from app.models.ct_bulk_job import CtBulkJob
from app.repositories.ct_bulk_repository import CtBulkRepository
from app.services.tld_coverage import get_ct_priority_tlds, resolve_ct_fallback_tlds
from app.services.use_cases.ingest_ct_batch import ingest_ct_batch

logger = logging.getLogger(__name__)

CRTSH_URL = "https://crt.sh/"
HTTP_TIMEOUT = 300
RETRY_BACKOFF = [60, 120, 300, 600]
CHUNK_ALPHABET = list(string.ascii_lowercase) + list(string.digits)


@dataclass(slots=True)
class ChunkFetchResult:
    kind: str
    raw_domains: list[str]
    error_type: str | None = None
    error_excerpt: str | None = None


@dataclass(slots=True)
class ExecutableChunk:
    id: uuid.UUID
    target_tld: str
    chunk_key: str
    query_pattern: str
    depth: int


def create_bulk_job(
    *,
    requested_tlds: list[str] | None = None,
    dry_run: bool = False,
    initiated_by: str | None = None,
) -> CtBulkJob:
    db = SessionLocal()
    try:
        repo = CtBulkRepository(db)
        active = repo.get_active_job()
        if active:
            raise RuntimeError(f"Bulk job already active: {active.id}")

        resolved_tlds = requested_tlds or resolve_ct_fallback_tlds(db)
        if not resolved_tlds:
            raise RuntimeError("No CT fallback TLDs resolved for bulk loading.")

        priority_tlds = [tld for tld in get_ct_priority_tlds() if tld in resolved_tlds]
        priority_tlds.extend([tld for tld in resolved_tlds if tld not in priority_tlds])

        job = repo.create_job(
            requested_tlds=requested_tlds or [],
            resolved_tlds=resolved_tlds,
            priority_tlds=priority_tlds,
            dry_run=dry_run,
            initiated_by=initiated_by,
        )
        repo.create_initial_chunks(job)
        db.commit()
        db.refresh(job)
        db.expunge(job)
        return job
    finally:
        db.close()


def resume_bulk_job(job_id: uuid.UUID) -> CtBulkJob:
    db = SessionLocal()
    try:
        repo = CtBulkRepository(db)
        active = repo.get_active_job()
        if active and active.id != job_id:
            raise RuntimeError(f"Another bulk job is active: {active.id}")

        job = repo.get_job(job_id)
        if not job:
            raise RuntimeError(f"Bulk job {job_id} not found.")

        now = datetime.now(timezone.utc)
        for status in ("error", "running"):
            for chunk in repo.list_chunks(job_id, limit=100000, status=status):
                chunk.status = "retry"
                chunk.next_retry_at = now
                chunk.finished_at = None
                chunk.last_error_type = "manual_resume"
                chunk.last_error_excerpt = "Operator resumed bulk job and re-queued chunk."
                chunk.updated_at = now

        if job.status in {"success", "failed", "cancelled", "running", "cancel_requested"}:
            job.status = "pending"
            job.finished_at = None
            job.last_error = None
            job.updated_at = now

        repo.refresh_job_metrics(job)
        db.commit()
        db.refresh(job)
        db.expunge(job)
        return job
    finally:
        db.close()


def cancel_bulk_job(job_id: uuid.UUID) -> CtBulkJob:
    db = SessionLocal()
    try:
        repo = CtBulkRepository(db)
        job = repo.get_job(job_id)
        if not job:
            raise RuntimeError(f"Bulk job {job_id} not found.")
        repo.request_cancel(job)
        db.commit()
        db.refresh(job)
        db.expunge(job)
        return job
    finally:
        db.close()


def run_bulk_job(job_id: uuid.UUID) -> None:
    try:
        while True:
            db = SessionLocal()
            try:
                repo = CtBulkRepository(db)
                job = repo.get_job(job_id)
                if not job:
                    logger.error("ct_bulk_job_missing job_id=%s", job_id)
                    return

                repo.refresh_job_metrics(job)
                if job.status == "cancel_requested":
                    repo.finish_job(job, status="cancelled", last_error="cancelled_by_operator")
                    db.commit()
                    logger.info("ct_bulk_job_cancelled job_id=%s", job.id)
                    return

                repo.mark_job_running(job)
                runnable = repo.list_runnable_chunks(job, limit=max(1, settings.CT_BULK_MAX_PARALLEL_CHUNKS * 4))
                if not runnable:
                    if job.pending_chunks == 0 and job.running_chunks == 0:
                        final_status = "failed" if job.error_chunks > 0 else "success"
                        repo.finish_job(job, status=final_status, last_error=job.last_error)
                        db.commit()
                        logger.info("ct_bulk_job_finished job_id=%s status=%s", job.id, final_status)
                        return

                    wait_until = repo.next_retry_at(job.id)
                    db.commit()
                    if wait_until:
                        sleep_seconds = max(5, min(60, int((wait_until - datetime.now(timezone.utc)).total_seconds())))
                        time.sleep(max(1, sleep_seconds))
                    else:
                        time.sleep(5)
                    continue

                selected = _select_chunks_for_execution(job, runnable)
                selected_tasks: list[ExecutableChunk] = []
                for chunk in selected:
                    repo.mark_chunk_running(chunk)
                    selected_tasks.append(
                        ExecutableChunk(
                            id=chunk.id,
                            target_tld=chunk.target_tld,
                            chunk_key=chunk.chunk_key,
                            query_pattern=chunk.query_pattern,
                            depth=chunk.depth,
                        )
                    )
                    logger.info(
                        "ct_bulk_chunk_started job_id=%s chunk=%s tld=%s depth=%s query=%s",
                        job.id, chunk.chunk_key, chunk.target_tld, chunk.depth, chunk.query_pattern,
                    )
                db.commit()
            finally:
                db.close()

            results = _execute_chunks(selected_tasks)
            for chunk_id, result in results.items():
                _apply_chunk_result(job_id, chunk_id, result)
    except Exception as exc:  # pragma: no cover - defensive production recovery
        logger.exception("ct_bulk_job_crashed job_id=%s", job_id)
        _recover_job_after_crash(job_id, str(exc))


def list_bulk_jobs(limit: int = 20) -> list[CtBulkJob]:
    db = SessionLocal()
    try:
        return CtBulkRepository(db).list_jobs(limit=limit)
    finally:
        db.close()


def list_bulk_chunks(job_id: uuid.UUID, *, status: str | None = None, target_tld: str | None = None) -> list[CtBulkChunk]:
    db = SessionLocal()
    try:
        return CtBulkRepository(db).list_chunks(job_id, limit=100000, status=status, target_tld=target_tld)
    finally:
        db.close()


def run_bulk_load(
    *,
    subtlds: list[str] | None = None,
    years: list[int] | None = None,  # kept for interface compatibility
    dry_run: bool = False,
) -> CtBulkJob:
    del years
    job = create_bulk_job(requested_tlds=subtlds, dry_run=dry_run, initiated_by="manual_script")
    run_bulk_job(job.id)
    db = SessionLocal()
    try:
        stored = CtBulkRepository(db).get_job(job.id)
        if not stored:
            raise RuntimeError(f"Bulk job {job.id} disappeared during execution.")
        db.refresh(stored)
        db.expunge(stored)
        return stored
    finally:
        db.close()


def _select_chunks_for_execution(job: CtBulkJob, runnable: list[CtBulkChunk]) -> list[CtBulkChunk]:
    if not runnable:
        return []

    priority_set = set(job.priority_tlds or [])
    first_tld = runnable[0].target_tld
    parallel_limit = 2 if first_tld in priority_set else 1
    parallel_limit = max(1, min(parallel_limit, settings.CT_BULK_MAX_PARALLEL_CHUNKS))

    selected = [chunk for chunk in runnable if chunk.target_tld == first_tld][:parallel_limit]
    return selected or runnable[:1]


def _execute_chunks(chunks: list[ExecutableChunk]) -> dict[uuid.UUID, ChunkFetchResult]:
    results: dict[uuid.UUID, ChunkFetchResult] = {}
    max_workers = max(1, min(len(chunks), settings.CT_BULK_MAX_PARALLEL_CHUNKS))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_map = {pool.submit(_fetch_chunk_payload, chunk.query_pattern): chunk.id for chunk in chunks}
        for future in as_completed(future_map):
            chunk_id = future_map[future]
            try:
                results[chunk_id] = future.result()
            except Exception as exc:  # pragma: no cover - defensive
                results[chunk_id] = ChunkFetchResult(
                    kind="retry",
                    raw_domains=[],
                    error_type="unexpected_exception",
                    error_excerpt=str(exc),
                )
    return results


def _apply_chunk_result(job_id: uuid.UUID, chunk_id: uuid.UUID, result: ChunkFetchResult) -> None:
    db = SessionLocal()
    try:
        repo = CtBulkRepository(db)
        job = repo.get_job(job_id)
        chunk = repo.get_chunk(chunk_id)
        if not job or not chunk:
            return

        if result.kind == "success":
            inserted = 0
            if not job.dry_run and result.raw_domains:
                inserted = ingest_ct_batch(db, result.raw_domains, source="crtsh-bulk", run_id=None).get("domains_inserted", 0)
            repo.complete_chunk(chunk, raw_domains=len(result.raw_domains), inserted_domains=inserted)
            logger.info(
                "ct_bulk_chunk_completed job_id=%s chunk=%s raw=%s inserted=%s",
                job.id, chunk.chunk_key, len(result.raw_domains), inserted,
            )
        elif result.kind == "split_required":
            if chunk.depth >= settings.CT_BULK_SPLIT_MAX_DEPTH:
                repo.mark_chunk_failed(
                    chunk,
                    error_type=result.error_type or "split_required",
                    error_excerpt=result.error_excerpt or "Reached max split depth",
                )
            else:
                next_prefixes = [f"{chunk.prefix}{char}" for char in CHUNK_ALPHABET]
                created = repo.create_split_children(chunk, prefixes=next_prefixes)
                logger.info(
                    "ct_bulk_chunk_split job_id=%s chunk=%s created=%s reason=%s",
                    job.id, chunk.chunk_key, len(created), result.error_type,
                )
        elif result.kind == "retry":
            wait_seconds = RETRY_BACKOFF[min(max(chunk.attempt_count - 1, 0), len(RETRY_BACKOFF) - 1)]
            repo.mark_chunk_retry(
                chunk,
                error_type=result.error_type or "retry",
                error_excerpt=result.error_excerpt or "retry requested",
                next_retry_at=datetime.now(timezone.utc) + timedelta(seconds=wait_seconds),
            )
            logger.info(
                "ct_bulk_chunk_retry job_id=%s chunk=%s wait=%ss reason=%s",
                job.id, chunk.chunk_key, wait_seconds, result.error_type,
            )
        else:
            repo.mark_chunk_failed(
                chunk,
                error_type=result.error_type or "fatal_error",
                error_excerpt=result.error_excerpt or "fatal bulk error",
            )
            logger.info(
                "ct_bulk_chunk_failed job_id=%s chunk=%s reason=%s",
                job.id, chunk.chunk_key, result.error_type,
            )

        repo.refresh_job_metrics(job)
        if job.error_chunks > 0 and job.done_chunks == 0:
            job.last_error = result.error_excerpt or result.error_type
        db.commit()
    except Exception:
        logger.exception("Failed to persist ct bulk chunk result job_id=%s chunk_id=%s", job_id, chunk_id)
        db.rollback()
    finally:
        db.close()


def _recover_job_after_crash(job_id: uuid.UUID, error_message: str) -> None:
    db = SessionLocal()
    try:
        repo = CtBulkRepository(db)
        job = repo.get_job(job_id)
        if not job:
            return

        next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=RETRY_BACKOFF[0])
        for chunk in repo.list_chunks(job_id, limit=100000, status="running"):
            repo.mark_chunk_retry(
                chunk,
                error_type="worker_crash",
                error_excerpt=error_message or "Bulk worker crashed unexpectedly.",
                next_retry_at=next_retry_at,
            )

        job.status = "pending"
        job.finished_at = None
        job.last_error = (error_message or "Bulk worker crashed unexpectedly.")[:2000]
        repo.refresh_job_metrics(job)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("ct_bulk_job_recovery_failed job_id=%s", job_id)
    finally:
        db.close()


def _fetch_chunk_payload(query_pattern: str) -> ChunkFetchResult:
    params = {"q": query_pattern, "output": "json"}
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
            response = client.get(CRTSH_URL, params=params)
            response.raise_for_status()

            content = response.content
            content_type = (response.headers.get("content-type") or "").lower()
            limit_bytes = settings.CT_BULK_RESPONSE_SIZE_LIMIT_MB * 1024 * 1024
            if len(content) > limit_bytes:
                return ChunkFetchResult(
                    kind="split_required",
                    raw_domains=[],
                    error_type="oversized_response",
                    error_excerpt=f"Response larger than configured limit for {query_pattern}",
                )

            body_preview = content.lstrip()[:32].decode("utf-8", "ignore").lower()
            if "json" not in content_type and (body_preview.startswith("<html") or body_preview.startswith("<!doctype")):
                return ChunkFetchResult(
                    kind="split_required",
                    raw_domains=[],
                    error_type="html_response",
                    error_excerpt=f"crt.sh returned HTML for {query_pattern}",
                )

            try:
                data = response.json()
            except json.JSONDecodeError:
                return ChunkFetchResult(
                    kind="split_required",
                    raw_domains=[],
                    error_type="non_json_response",
                    error_excerpt=f"crt.sh returned non-JSON payload for {query_pattern}",
                )

            if not isinstance(data, list):
                return ChunkFetchResult(
                    kind="split_required",
                    raw_domains=[],
                    error_type="unexpected_payload",
                    error_excerpt=f"crt.sh returned unexpected payload type for {query_pattern}",
                )

            domains: list[str] = []
            for entry in data:
                name_value = entry.get("name_value", "")
                if not name_value:
                    continue
                for item in name_value.split("\n"):
                    domain = item.strip()
                    if domain:
                        domains.append(domain)

            return ChunkFetchResult(kind="success", raw_domains=domains)

    except httpx.TimeoutException:
        return ChunkFetchResult(kind="retry", raw_domains=[], error_type="timeout", error_excerpt=f"Timeout for {query_pattern}")
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status in {429, 500, 502, 503, 504}:
            return ChunkFetchResult(
                kind="retry",
                raw_domains=[],
                error_type=f"http_{status}",
                error_excerpt=f"Retryable HTTP {status} for {query_pattern}",
            )
        return ChunkFetchResult(
            kind="fatal",
            raw_domains=[],
            error_type=f"http_{status}",
            error_excerpt=f"Fatal HTTP {status} for {query_pattern}",
        )
    except Exception as exc:
        return ChunkFetchResult(
            kind="retry",
            raw_domains=[],
            error_type="unexpected_error",
            error_excerpt=str(exc),
        )
