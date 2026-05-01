# backend/app/repositories/monitoring_event_repository.py
"""Repository for monitoring events — create and query immutable event records."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.monitoring_event import MonitoringEvent


class MonitoringEventRepository:
    """Write-once, read-many access to monitoring_event records."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        organization_id: UUID,
        brand_id: UUID,
        event_type: str,
        event_source: str,
        result_data: dict,
        match_id: UUID | None = None,
        brand_domain_id: UUID | None = None,
        cycle_id: UUID | None = None,
        tool_name: str | None = None,
        tool_version: str | None = None,
        signals: list[dict] | None = None,
        score_snapshot: dict | None = None,
        ttl_expires_at: datetime | None = None,
    ) -> MonitoringEvent:
        """Persist one immutable event. Caller must commit or flush the session."""
        evt = MonitoringEvent(
            id=uuid.uuid4(),
            organization_id=organization_id,
            brand_id=brand_id,
            event_type=event_type,
            event_source=event_source,
            result_data=result_data,
            match_id=match_id,
            brand_domain_id=brand_domain_id,
            cycle_id=cycle_id,
            tool_name=tool_name,
            tool_version=tool_version,
            signals=signals,
            score_snapshot=score_snapshot,
            ttl_expires_at=ttl_expires_at,
        )
        self.db.add(evt)
        self.db.flush()
        return evt

    def fetch_latest_for_match_tool(
        self,
        *,
        match_id: UUID,
        tool_name: str,
    ) -> MonitoringEvent | None:
        """Return the most recent event for a given match + tool combination."""
        return (
            self.db.query(MonitoringEvent)
            .filter(
                MonitoringEvent.match_id == match_id,
                MonitoringEvent.tool_name == tool_name,
            )
            .order_by(MonitoringEvent.created_at.desc())
            .first()
        )

    def fetch_latest_for_domain_tool(
        self,
        *,
        brand_domain_id: UUID,
        tool_name: str,
    ) -> MonitoringEvent | None:
        """Return the most recent event for a given brand_domain + tool combination."""
        return (
            self.db.query(MonitoringEvent)
            .filter(
                MonitoringEvent.brand_domain_id == brand_domain_id,
                MonitoringEvent.tool_name == tool_name,
            )
            .order_by(MonitoringEvent.created_at.desc())
            .first()
        )

    def list_for_match(
        self,
        *,
        match_id: UUID,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MonitoringEvent]:
        """Return all events for a match, newest first. Used by timeline API."""
        return (
            self.db.query(MonitoringEvent)
            .filter(MonitoringEvent.match_id == match_id)
            .order_by(MonitoringEvent.created_at.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def event_exists_for_cycle(
        self,
        *,
        cycle_id: UUID,
        tool_name: str,
        match_id: UUID | None = None,
        brand_domain_id: UUID | None = None,
    ) -> bool:
        """Idempotency check: has this tool already run for this target in this cycle?"""
        q = self.db.query(MonitoringEvent.id).filter(
            MonitoringEvent.cycle_id == cycle_id,
            MonitoringEvent.tool_name == tool_name,
        )
        if match_id:
            q = q.filter(MonitoringEvent.match_id == match_id)
        if brand_domain_id:
            q = q.filter(MonitoringEvent.brand_domain_id == brand_domain_id)
        return q.first() is not None
