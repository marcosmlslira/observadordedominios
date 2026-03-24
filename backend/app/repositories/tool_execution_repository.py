"""Repository for tool_execution CRUD and cache lookups."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models.tool_execution import ToolExecution


class ToolExecutionRepository:
    """Handles persistence for free-tool execution records."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        organization_id: uuid.UUID,
        tool_type: str,
        target: str,
        triggered_by: str = "manual",
        quick_analysis_id: uuid.UUID | None = None,
    ) -> ToolExecution:
        record = ToolExecution(
            id=uuid.uuid4(),
            organization_id=organization_id,
            tool_type=tool_type,
            target=target,
            status="running",
            triggered_by=triggered_by,
            quick_analysis_id=quick_analysis_id,
        )
        self.db.add(record)
        self.db.flush()
        return record

    def mark_completed(
        self,
        record: ToolExecution,
        *,
        result_data: dict,
        duration_ms: int,
    ) -> None:
        record.status = "completed"
        record.result_data = result_data
        record.duration_ms = duration_ms
        self.db.flush()

    def mark_failed(
        self,
        record: ToolExecution,
        *,
        error_message: str,
        duration_ms: int,
        status: str = "failed",
    ) -> None:
        record.status = status
        record.error_message = error_message
        record.duration_ms = duration_ms
        self.db.flush()

    def find_cached(
        self,
        *,
        organization_id: uuid.UUID,
        tool_type: str,
        target: str,
        ttl_seconds: int,
    ) -> ToolExecution | None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
        return (
            self.db.query(ToolExecution)
            .filter(
                ToolExecution.organization_id == organization_id,
                ToolExecution.tool_type == tool_type,
                ToolExecution.target == target,
                ToolExecution.status == "completed",
                ToolExecution.created_at > cutoff,
            )
            .order_by(ToolExecution.created_at.desc())
            .first()
        )

    def get_by_id(self, execution_id: uuid.UUID) -> ToolExecution | None:
        return self.db.get(ToolExecution, execution_id)

    def list_history(
        self,
        organization_id: uuid.UUID,
        *,
        target: str | None = None,
        tool_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ToolExecution]:
        q = self.db.query(ToolExecution).filter(
            ToolExecution.organization_id == organization_id,
        )
        if target:
            q = q.filter(ToolExecution.target == target)
        if tool_type:
            q = q.filter(ToolExecution.tool_type == tool_type)
        return (
            q.order_by(ToolExecution.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_history(
        self,
        organization_id: uuid.UUID,
        *,
        target: str | None = None,
        tool_type: str | None = None,
    ) -> int:
        q = self.db.query(ToolExecution).filter(
            ToolExecution.organization_id == organization_id,
        )
        if target:
            q = q.filter(ToolExecution.target == target)
        if tool_type:
            q = q.filter(ToolExecution.tool_type == tool_type)
        return q.count()

    def count_recent(
        self,
        organization_id: uuid.UUID,
        *,
        tool_type: str | None = None,
        window_seconds: int = 3600,
    ) -> int:
        """Count executions in the last N seconds (for rate limiting)."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        q = self.db.query(ToolExecution).filter(
            ToolExecution.organization_id == organization_id,
            ToolExecution.created_at > cutoff,
        )
        if tool_type:
            q = q.filter(ToolExecution.tool_type == tool_type)
        return q.count()
