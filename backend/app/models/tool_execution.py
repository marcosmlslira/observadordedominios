"""ToolExecution model — event log for free tool runs."""

from __future__ import annotations

import uuid

from sqlalchemy import Column, DateTime, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, TimestampMixin


class ToolExecution(TimestampMixin, Base):
    """Append-only record of every free-tool execution."""

    __tablename__ = "tool_execution"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    tool_type = Column(String(32), nullable=False)
    target = Column(String(253), nullable=False)
    status = Column(String(16), nullable=False, default="running")
    result_data = Column(JSONB, nullable=True)
    error_message = Column(Text, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    triggered_by = Column(String(32), nullable=False, default="manual")
    quick_analysis_id = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index("ix_tool_exec_org_created", "organization_id", "created_at"),
        Index("ix_tool_exec_org_type_created", "organization_id", "tool_type", "created_at"),
        Index("ix_tool_exec_org_target", "organization_id", "target"),
        Index(
            "ix_tool_exec_quick_analysis",
            "quick_analysis_id",
            postgresql_where="quick_analysis_id IS NOT NULL",
        ),
    )
