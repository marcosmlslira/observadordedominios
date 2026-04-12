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

    now = datetime.now(timezone.utc)
    today = date.today()

    # CycleSummarySchema + MonitoringSummarySchema
    cs = CycleSummarySchema(
        cycle_date=today,
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

    # CycleResponse — includes scan_job_id
    cycle_id = uuid4()
    brand_id = uuid4()
    cr = CycleResponse(
        id=cycle_id,
        brand_id=brand_id,
        organization_id=uuid4(),
        cycle_date=today,
        cycle_type="scheduled",
        health_status="completed",
        scan_status="completed",
        scan_job_id=uuid4(),
        enrichment_status="completed",
        created_at=now,
        updated_at=now,
    )
    assert cr.scan_job_id is not None
    assert CycleListResponse(items=[cr], total=1).total == 1

    # DomainHealthCheckSchema — all 10 tool slots
    check = DomainCheckDetailSchema(ok=True, details={"days_remaining": 90})
    dh = DomainHealthCheckSchema(
        domain_id=uuid4(),
        domain_name="brand.com",
        is_primary=True,
        overall_status="healthy",
        dns=check,
        ssl=check,
        email_security=check,
        headers=check,
        takeover=check,
        blacklist=check,
        safe_browsing=check,
        urlhaus=check,
        phishtank=check,
        suspicious_page=check,
        last_check_at=now,
    )
    assert dh.overall_status == "healthy"
    assert dh.ssl.details["days_remaining"] == 90

    # MatchSnapshotResponse — derived fields + LLM
    sig = SignalSchema(code="safe_browsing_hit", severity="critical", score_adjustment=0.3)
    snap = MatchSnapshotResponse(
        id=uuid4(),
        brand_id=brand_id,
        domain_name="brand-fake.com",
        tld="com",
        label="brand-fake",
        score_final=0.8,
        first_detected_at=now,
        domain_first_seen=now,
        derived_score=0.92,
        derived_bucket="immediate_attention",
        derived_risk="critical",
        active_signals=[sig],
        signal_codes=["safe_browsing_hit"],
        llm_assessment={"parecer_resumido": "Suspicious."},
        state_fingerprint="abc123",
        last_derived_at=now,
    )
    assert snap.derived_risk == "critical"
    assert snap.llm_assessment["parecer_resumido"] == "Suspicious."
    assert MatchSnapshotListResponse(items=[snap], total=1).total == 1

    # EventResponse
    ev = EventResponse(
        id=uuid4(),
        event_type="tool_execution",
        event_source="enrichment",
        tool_name="dns_lookup",
        result_data={"records": []},
        created_at=now,
    )
    assert ev.tool_name == "dns_lookup"
    assert EventListResponse(items=[ev], total=1).total == 1


def test_monitoring_query_service_summary_no_data(db_session):
    """Service returns safe defaults when no cycle or snapshots exist for a brand."""
    from app.services.monitoring_query_service import MonitoringQueryService
    from app.models.monitored_brand import MonitoredBrand
    from uuid import uuid4

    org_id = uuid4()
    brand = MonitoredBrand(
        id=uuid4(), organization_id=org_id,
        brand_name="SvcCo", primary_brand_name="SvcCo", brand_label="svcco",
        is_active=True,
    )
    db_session.add(brand)
    db_session.commit()

    svc = MonitoringQueryService(db_session)
    summary = svc.get_monitoring_summary(brand.id)

    assert summary["latest_cycle"] is None
    assert summary["threat_counts"]["immediate_attention"] == 0
    assert summary["overall_health"] == "unknown"


def test_monitoring_query_service_with_cycle_and_health(db_session):
    """Service returns cycle + threat counts (excluding dismissed) + overall_health."""
    from app.services.monitoring_query_service import MonitoringQueryService
    from app.models.monitored_brand import MonitoredBrand
    from app.models.monitored_brand_domain import MonitoredBrandDomain
    from app.models.monitoring_cycle import MonitoringCycle
    from app.models.brand_domain_health import BrandDomainHealth
    from app.models.match_state_snapshot import MatchStateSnapshot
    from app.models.similarity_match import SimilarityMatch
    from uuid import uuid4
    from datetime import date, datetime, timezone

    org_id = uuid4()
    now = datetime.now(timezone.utc)
    brand = MonitoredBrand(
        id=uuid4(), organization_id=org_id,
        brand_name="SvcCo2", primary_brand_name="SvcCo2", brand_label="svcco2",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    domain = MonitoredBrandDomain(
        id=uuid4(), brand_id=brand.id,
        domain_name="svcco2.com", registrable_domain="svcco2.com",
        registrable_label="svcco2", public_suffix="com",
        is_active=True, created_at=now, updated_at=now,
    )
    db_session.add(domain)
    db_session.flush()

    cycle = MonitoringCycle(
        id=uuid4(), brand_id=brand.id, organization_id=org_id,
        cycle_date=date.today(), health_status="completed",
        scan_status="completed", enrichment_status="completed",
        threats_detected=2,
    )
    db_session.add(cycle)

    health = BrandDomainHealth(
        id=uuid4(), brand_domain_id=domain.id, brand_id=brand.id,
        organization_id=org_id, overall_status="healthy",
    )
    db_session.add(health)

    # Active match with snapshot in immediate_attention
    match = SimilarityMatch(
        id=uuid4(), brand_id=brand.id,
        domain_name="svcco2-fake.com", tld="com", label="svcco2-fake",
        score_final=0.9, attention_bucket="immediate_attention",
        actionability_score=0.9, reasons=[], attention_reasons=[],
        recommended_action="block", risk_level="high",
        first_detected_at=now, domain_first_seen=now,
    )
    db_session.add(match)
    db_session.flush()

    snapshot = MatchStateSnapshot(
        id=uuid4(), match_id=match.id, brand_id=brand.id,
        organization_id=org_id,
        derived_score=0.9, derived_bucket="immediate_attention",
        derived_risk="high", active_signals=[], signal_codes=[],
        state_fingerprint="fp_test",
        last_derived_at=now,
    )
    db_session.add(snapshot)

    # Auto-dismissed match (should be excluded from counts)
    dismissed_match = SimilarityMatch(
        id=uuid4(), brand_id=brand.id,
        domain_name="svcco2-dismissed.com", tld="com", label="svcco2-dismissed",
        score_final=0.5, attention_bucket="defensive_gap",
        actionability_score=0.5, reasons=[], attention_reasons=[],
        recommended_action="monitor", risk_level="low",
        first_detected_at=now, domain_first_seen=now,
        auto_disposition="auto_dismissed",
    )
    db_session.add(dismissed_match)
    db_session.flush()

    dismissed_snapshot = MatchStateSnapshot(
        id=uuid4(), match_id=dismissed_match.id, brand_id=brand.id,
        organization_id=org_id,
        derived_score=0.5, derived_bucket="defensive_gap",
        derived_risk="low", active_signals=[], signal_codes=[],
        state_fingerprint="fp_dismissed",
        last_derived_at=now,
    )
    db_session.add(dismissed_snapshot)
    db_session.commit()

    svc = MonitoringQueryService(db_session)
    summary = svc.get_monitoring_summary(brand.id)

    assert summary["latest_cycle"]["health_status"] == "completed"
    assert summary["threat_counts"]["immediate_attention"] == 1
    assert summary["threat_counts"]["defensive_gap"] == 0  # dismissed excluded
    assert summary["overall_health"] == "healthy"


def test_get_brand_includes_monitoring_summary(client, db_session):
    """GET /v1/brands/{id} response includes monitoring_summary with defaults."""
    from app.models.monitored_brand import MonitoredBrand
    from uuid import uuid4

    org_id = uuid4()
    brand = MonitoredBrand(
        id=uuid4(), organization_id=org_id,
        brand_name="SummaryBrand", primary_brand_name="SummaryBrand",
        brand_label="summarybrand", is_active=True,
    )
    db_session.add(brand)
    db_session.commit()

    resp = client.get(f"/v1/brands/{brand.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "monitoring_summary" in data
    ms = data["monitoring_summary"]
    assert "threat_counts" in ms
    assert "overall_health" in ms
    assert ms["overall_health"] == "unknown"
    assert ms["threat_counts"]["immediate_attention"] == 0


def test_get_brand_health_returns_domain_checks(client, db_session):
    """GET /v1/brands/{id}/health returns domains array with per-tool checks."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.monitored_brand_domain import MonitoredBrandDomain
    from app.models.brand_domain_health import BrandDomainHealth
    from uuid import uuid4
    from datetime import datetime, timezone

    org_id = uuid4()
    now = datetime.now(timezone.utc)
    brand = MonitoredBrand(
        id=uuid4(), organization_id=org_id,
        brand_name="HealthBrand", primary_brand_name="HealthBrand",
        brand_label="healthbrand", is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    domain = MonitoredBrandDomain(
        id=uuid4(), brand_id=brand.id,
        domain_name="healthbrand.com", registrable_domain="healthbrand.com",
        registrable_label="healthbrand", public_suffix="com",
        is_active=True, created_at=now, updated_at=now,
    )
    db_session.add(domain)
    db_session.flush()

    health = BrandDomainHealth(
        id=uuid4(), brand_domain_id=domain.id, brand_id=brand.id,
        organization_id=org_id, overall_status="healthy",
        dns_ok=True, ssl_ok=True, ssl_days_remaining=245,
        email_security_ok=True, safe_browsing_hit=False,
    )
    db_session.add(health)
    db_session.commit()

    resp = client.get(f"/v1/brands/{brand.id}/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "domains" in data
    assert len(data["domains"]) == 1
    dom = data["domains"][0]
    assert dom["overall_status"] == "healthy"
    assert dom["dns"]["ok"] is True
    assert dom["ssl"]["details"]["days_remaining"] == 245


def test_get_brand_cycles_returns_history(client, db_session):
    """GET /v1/brands/{id}/cycles returns paginated cycle history ordered newest first."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.monitoring_cycle import MonitoringCycle
    from uuid import uuid4
    from datetime import date, timedelta

    org_id = uuid4()
    brand = MonitoredBrand(
        id=uuid4(), organization_id=org_id,
        brand_name="CycleBrand", primary_brand_name="CycleBrand",
        brand_label="cyclebrand", is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    today = date.today()
    for i in range(3):
        db_session.add(MonitoringCycle(
            id=uuid4(), brand_id=brand.id, organization_id=org_id,
            cycle_date=today - timedelta(days=i),
            health_status="completed", scan_status="completed",
            enrichment_status="completed",
        ))
    db_session.commit()

    resp = client.get(f"/v1/brands/{brand.id}/cycles")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["items"][0]["cycle_date"] == str(today)
