"""Persistence helpers for crt.sh bulk backfill jobs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.ct_bulk_chunk import CtBulkChunk
from app.models.ct_bulk_job import CtBulkJob


class CtBulkRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_job(self, job_id: uuid.UUID) -> CtBulkJob | None:
        return self.db.get(CtBulkJob, job_id)

    def get_chunk(self, chunk_id: uuid.UUID) -> CtBulkChunk | None:
        return self.db.get(CtBulkChunk, chunk_id)

    def list_jobs(self, *, limit: int = 20) -> list[CtBulkJob]:
        return (
            self.db.query(CtBulkJob)
            .order_by(CtBulkJob.created_at.desc())
            .limit(limit)
            .all()
        )

    def get_active_job(self) -> CtBulkJob | None:
        return (
            self.db.query(CtBulkJob)
            .filter(CtBulkJob.status.in_(("pending", "running", "cancel_requested")))
            .order_by(CtBulkJob.created_at.desc())
            .first()
        )

    def create_job(
        self,
        *,
        requested_tlds: list[str],
        resolved_tlds: list[str],
        priority_tlds: list[str],
        dry_run: bool,
        initiated_by: str | None,
    ) -> CtBulkJob:
        now = datetime.now(timezone.utc)
        job = CtBulkJob(
            id=uuid.uuid4(),
            status="pending",
            requested_tlds=requested_tlds,
            resolved_tlds=resolved_tlds,
            priority_tlds=priority_tlds,
            dry_run=dry_run,
            initiated_by=initiated_by,
            created_at=now,
            updated_at=now,
        )
        self.db.add(job)
        self.db.flush()
        return job

    def create_initial_chunks(self, job: CtBulkJob) -> list[CtBulkChunk]:
        now = datetime.now(timezone.utc)
        chunks: list[CtBulkChunk] = []
        for tld in job.resolved_tlds:
            chunk = CtBulkChunk(
                id=uuid.uuid4(),
                job_id=job.id,
                target_tld=tld,
                chunk_key=f"{tld}:root",
                query_pattern=f"%.{tld}",
                prefix="",
                depth=0,
                status="pending",
                created_at=now,
                updated_at=now,
            )
            self.db.add(chunk)
            chunks.append(chunk)
        self.db.flush()
        self.refresh_job_metrics(job)
        return chunks

    def list_chunks(
        self,
        job_id: uuid.UUID,
        *,
        limit: int = 500,
        status: str | None = None,
        target_tld: str | None = None,
    ) -> list[CtBulkChunk]:
        query = self.db.query(CtBulkChunk).filter(CtBulkChunk.job_id == job_id)
        if status:
            query = query.filter(CtBulkChunk.status == status)
        if target_tld:
            query = query.filter(CtBulkChunk.target_tld == target_tld)
        return (
            query.order_by(CtBulkChunk.depth.asc(), CtBulkChunk.chunk_key.asc())
            .limit(limit)
            .all()
        )

    def list_runnable_chunks(
        self,
        job: CtBulkJob,
        *,
        limit: int,
    ) -> list[CtBulkChunk]:
        now = datetime.now(timezone.utc)
        rows = (
            self.db.query(CtBulkChunk)
            .filter(CtBulkChunk.job_id == job.id)
            .filter(CtBulkChunk.status.in_(("pending", "retry")))
            .filter(or_(CtBulkChunk.next_retry_at.is_(None), CtBulkChunk.next_retry_at <= now))
            .all()
        )
        priority_index = {tld: idx for idx, tld in enumerate(job.priority_tlds or [])}
        rows.sort(key=lambda item: (priority_index.get(item.target_tld, 9999), item.depth, item.chunk_key))
        return rows[:limit]

    def mark_job_running(self, job: CtBulkJob) -> None:
        if job.status == "pending":
            job.status = "running"
            job.started_at = datetime.now(timezone.utc)
            job.updated_at = job.started_at
            self.db.flush()

    def request_cancel(self, job: CtBulkJob) -> CtBulkJob:
        job.status = "cancel_requested"
        job.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return job

    def finish_job(self, job: CtBulkJob, *, status: str, last_error: str | None = None) -> CtBulkJob:
        now = datetime.now(timezone.utc)
        job.status = status
        job.finished_at = now
        job.updated_at = now
        job.last_error = last_error
        self.db.flush()
        return job

    def mark_chunk_running(self, chunk: CtBulkChunk) -> None:
        now = datetime.now(timezone.utc)
        chunk.status = "running"
        chunk.attempt_count = (chunk.attempt_count or 0) + 1
        chunk.started_at = now
        chunk.updated_at = now
        self.db.flush()

    def complete_chunk(self, chunk: CtBulkChunk, *, raw_domains: int, inserted_domains: int) -> None:
        now = datetime.now(timezone.utc)
        chunk.status = "done"
        chunk.raw_domains = raw_domains
        chunk.inserted_domains = inserted_domains
        chunk.last_error_type = None
        chunk.last_error_excerpt = None
        chunk.next_retry_at = None
        chunk.finished_at = now
        chunk.updated_at = now
        self.db.flush()

    def mark_chunk_retry(
        self,
        chunk: CtBulkChunk,
        *,
        error_type: str,
        error_excerpt: str,
        next_retry_at: datetime,
    ) -> None:
        chunk.status = "retry"
        chunk.last_error_type = error_type
        chunk.last_error_excerpt = error_excerpt[:2000]
        chunk.next_retry_at = next_retry_at
        chunk.updated_at = datetime.now(timezone.utc)
        self.db.flush()

    def mark_chunk_failed(
        self,
        chunk: CtBulkChunk,
        *,
        error_type: str,
        error_excerpt: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        chunk.status = "error"
        chunk.last_error_type = error_type
        chunk.last_error_excerpt = error_excerpt[:2000]
        chunk.finished_at = now
        chunk.updated_at = now
        self.db.flush()

    def create_split_children(
        self,
        chunk: CtBulkChunk,
        *,
        prefixes: list[str],
    ) -> list[CtBulkChunk]:
        existing = {
            row.chunk_key
            for row in self.db.query(CtBulkChunk.chunk_key)
            .filter(CtBulkChunk.job_id == chunk.job_id)
            .filter(CtBulkChunk.parent_chunk_id == chunk.id)
            .all()
        }
        now = datetime.now(timezone.utc)
        created: list[CtBulkChunk] = []
        for prefix in prefixes:
            chunk_key = f"{chunk.target_tld}:prefix:{prefix}"
            if chunk_key in existing:
                continue
            child = CtBulkChunk(
                id=uuid.uuid4(),
                job_id=chunk.job_id,
                parent_chunk_id=chunk.id,
                target_tld=chunk.target_tld,
                chunk_key=chunk_key,
                query_pattern=f"{prefix}%.{chunk.target_tld}",
                prefix=prefix,
                depth=chunk.depth + 1,
                status="pending",
                created_at=now,
                updated_at=now,
            )
            self.db.add(child)
            created.append(child)

        chunk.status = "split"
        chunk.finished_at = now
        chunk.updated_at = now
        chunk.last_error_type = "split_required"
        self.db.flush()
        return created

    def refresh_job_metrics(self, job: CtBulkJob) -> CtBulkJob:
        rows = self.list_chunks(job.id, limit=100000)
        job.total_chunks = len(rows)
        job.pending_chunks = sum(1 for row in rows if row.status in {"pending", "retry"})
        job.running_chunks = sum(1 for row in rows if row.status == "running")
        job.done_chunks = sum(1 for row in rows if row.status == "done")
        job.error_chunks = sum(1 for row in rows if row.status == "error")
        job.total_raw_domains = sum(int(row.raw_domains or 0) for row in rows)
        job.total_inserted_domains = sum(int(row.inserted_domains or 0) for row in rows)
        job.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return job

    def next_retry_at(self, job_id: uuid.UUID) -> datetime | None:
        row = (
            self.db.query(CtBulkChunk.next_retry_at)
            .filter(CtBulkChunk.job_id == job_id)
            .filter(CtBulkChunk.status == "retry")
            .filter(CtBulkChunk.next_retry_at.is_not(None))
            .order_by(CtBulkChunk.next_retry_at.asc())
            .first()
        )
        return row[0] if row else None
