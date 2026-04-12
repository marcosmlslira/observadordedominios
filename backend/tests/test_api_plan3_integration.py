"""Integration tests for Plan 3 — Monitoring Pipeline API layer."""
from __future__ import annotations

import pytest


def test_monitoring_schemas_instantiate():
    from app.schemas.monitoring import (
        CycleSummarySchema, ThreatCountsSchema, MonitoringSummarySchema,
        CycleResponse, CycleListResponse,
        DomainCheckDetailSchema, DomainHealthCheckSchema, BrandHealthResponse,
        SignalSchema, MatchSnapshotResponse, MatchSnapshotListResponse,
        EventResponse, EventListResponse,
    )
    from uuid import uuid4
    from datetime import date, datetime, timezone

    cs = CycleSummarySchema(
        cycle_date=date.today(),
        health_status="completed",
        scan_status="completed",
        enrichment_status="completed",
        new_matches_count=3,
        threats_detected=1,
        dismissed_count=5,
    )
    assert cs.health_status == "completed"

    ms = MonitoringSummarySchema(
        latest_cycle=cs,
        threat_counts=ThreatCountsSchema(immediate_attention=1, defensive_gap=4, watchlist=20),
        overall_health="healthy",
    )
    assert ms.overall_health == "healthy"
