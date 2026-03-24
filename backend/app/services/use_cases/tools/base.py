"""Base service for all free tools — cache check, record lifecycle, timeout."""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.repositories.tool_execution_repository import ToolExecutionRepository
from app.schemas.tools import ToolResponse

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Raised when a tool execution fails."""


class RateLimitExceeded(Exception):
    """Raised when the per-tool or global rate limit is exceeded."""


class BaseToolService(ABC):
    """Template for every free-tool service.

    Subclasses must set ``tool_type``, ``cache_ttl_seconds``, ``timeout_seconds``
    and implement ``_execute(target) -> dict``.
    """

    tool_type: str
    cache_ttl_seconds: int = 300
    timeout_seconds: int = 30

    # Rate limits (per hour per organization)
    per_tool_limit: int = 30
    global_limit: int = 200

    def run(
        self,
        db: Session,
        organization_id: uuid.UUID,
        target: str,
        *,
        triggered_by: str = "manual",
        quick_analysis_id: uuid.UUID | None = None,
        force: bool = False,
    ) -> ToolResponse:
        repo = ToolExecutionRepository(db)

        # 1. Rate limiting
        self._check_rate_limit(repo, organization_id)

        # 2. Cache check
        if not force:
            cached = repo.find_cached(
                organization_id=organization_id,
                tool_type=self.tool_type,
                target=target,
                ttl_seconds=self.cache_ttl_seconds,
            )
            if cached:
                return ToolResponse(
                    execution_id=cached.id,
                    tool_type=self.tool_type,
                    target=cached.target,
                    status=cached.status,
                    duration_ms=cached.duration_ms,
                    cached=True,
                    result=cached.result_data,
                    executed_at=cached.created_at,
                )

        # 3. Create running record
        record = repo.create(
            organization_id=organization_id,
            tool_type=self.tool_type,
            target=target,
            triggered_by=triggered_by,
            quick_analysis_id=quick_analysis_id,
        )

        # 4. Execute with timing
        start = time.monotonic()
        try:
            result_data = self._execute(target)
            duration_ms = int((time.monotonic() - start) * 1000)
            repo.mark_completed(record, result_data=result_data, duration_ms=duration_ms)

            return ToolResponse(
                execution_id=record.id,
                tool_type=self.tool_type,
                target=target,
                status="completed",
                duration_ms=duration_ms,
                cached=False,
                result=result_data,
                executed_at=record.created_at,
            )

        except Exception as exc:
            duration_ms = int((time.monotonic() - start) * 1000)
            error_msg = str(exc)
            status = "timeout" if duration_ms > self.timeout_seconds * 1000 else "failed"
            repo.mark_failed(record, error_message=error_msg, duration_ms=duration_ms, status=status)
            logger.warning(
                "Tool %s failed for %s: %s (%d ms)",
                self.tool_type, target, error_msg, duration_ms,
            )

            return ToolResponse(
                execution_id=record.id,
                tool_type=self.tool_type,
                target=target,
                status=status,
                duration_ms=duration_ms,
                cached=False,
                error=error_msg,
                executed_at=record.created_at,
            )

    def _check_rate_limit(
        self,
        repo: ToolExecutionRepository,
        organization_id: uuid.UUID,
    ) -> None:
        # Per-tool limit
        tool_count = repo.count_recent(
            organization_id, tool_type=self.tool_type, window_seconds=3600,
        )
        if tool_count >= self.per_tool_limit:
            raise RateLimitExceeded(
                f"Rate limit exceeded: {self.tool_type} ({tool_count}/{self.per_tool_limit} per hour)"
            )

        # Global limit
        global_count = repo.count_recent(organization_id, window_seconds=3600)
        if global_count >= self.global_limit:
            raise RateLimitExceeded(
                f"Global rate limit exceeded ({global_count}/{self.global_limit} per hour)"
            )

    @abstractmethod
    def _execute(self, target: str) -> dict:
        """Run the actual tool logic. Must return a dict serializable to JSONB."""
        ...
