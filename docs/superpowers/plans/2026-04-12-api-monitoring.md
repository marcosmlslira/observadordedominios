# API Monitoring Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the monitoring pipeline data (workers, snapshots, health, events) via REST endpoints so the frontend can build the brand cards, brand detail page, and match drawer.

**Architecture:** New `app/schemas/monitoring.py` schema file covers all monitoring-domain response types. A thin `MonitoringQueryService` aggregates data from 4 repositories for the `monitoring_summary` field added to brand responses. New endpoints are added to existing routers (`monitored_brands.py`, `similarity.py`). The `list_matches` endpoint is migrated to read from `match_state_snapshot` instead of `similarity_match` directly.

**Tech Stack:** FastAPI, SQLAlchemy ORM, Pydantic v2, PostgreSQL. All new code follows the existing layered pattern: router → service (query assembly only) → repository.

---

## Key API Contracts (read before implementing)

### Existing repositories used
- `MonitoringCycleRepository(db).get_latest_for_brand(brand_id)` → `MonitoringCycle | None`
- `MonitoringCycleRepository(db).list_for_brand(brand_id, *, limit, offset)` → `list[MonitoringCycle]`
- `MatchStateSnapshotRepository(db).count_by_bucket(brand_id)` → `dict[str, int]` (includes auto-dismissed)
- `MatchStateSnapshotRepository(db).count_by_bucket_active(brand_id)` → `dict[str, int]` (excludes auto-dismissed — **must be added to the repo in Task 2**)
- `MatchStateSnapshotRepository(db).list_for_brand(brand_id, *, bucket, exclude_auto_dismissed, limit, offset)` → `list[MatchStateSnapshot]`
- `MatchStateSnapshotRepository(db).get_by_match(match_id)` → `MatchStateSnapshot | None`
- `BrandDomainHealthRepository(db).list_for_brand(brand_id)` → `list[BrandDomainHealth]`
- `BrandDomainHealthRepository(db).get_by_domain(brand_domain_id)` → `BrandDomainHealth | None`
- `MonitoringEventRepository(db).list_for_match(*, match_id, limit, offset)` → `list[MonitoringEvent]`

### Model fields available in MatchStateSnapshot
`match_id`, `brand_id`, `organization_id`, `derived_score`, `derived_bucket`, `derived_risk`, `derived_disposition`, `active_signals` (JSONB list), `signal_codes` (TEXT[]), `llm_assessment` (JSONB | None), `llm_event_id`, `llm_source_fingerprint`, `state_fingerprint`, `events_hash`, `last_derived_at`, `created_at`, `updated_at`

### Model fields available in BrandDomainHealth
`brand_domain_id`, `brand_id`, `organization_id`, `overall_status`, `dns_ok`, `ssl_ok`, `ssl_days_remaining`, `email_security_ok`, `spoofing_risk`, `headers_score`, `takeover_risk`, `blacklisted`, `safe_browsing_hit`, `urlhaus_hit`, `phishtank_hit`, `suspicious_content`, `state_fingerprint`, `last_check_at`, `last_event_ids`, `created_at`, `updated_at`

### Model fields available in MonitoringCycle
`id`, `brand_id`, `organization_id`, `cycle_date`, `cycle_type`, `health_status`, `health_started_at`, `health_finished_at`, `scan_status`, `scan_started_at`, `scan_finished_at`, `scan_job_id`, `enrichment_status`, `enrichment_started_at`, `enrichment_finished_at`, `enrichment_budget`, `enrichment_total`, `new_matches_count`, `escalated_count`, `dismissed_count`, `threats_detected`, `created_at`, `updated_at`

### Model fields available in MonitoringEvent
`id`, `organization_id`, `brand_id`, `event_type`, `event_source`, `match_id`, `brand_domain_id`, `tool_name`, `tool_version`, `result_data`, `signals`, `score_snapshot`, `cycle_id`, `created_at`, `ttl_expires_at`

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `backend/app/schemas/monitoring.py` | **Create** | All new monitoring response schemas |
| `backend/app/services/monitoring_query_service.py` | **Create** | Assembles `monitoring_summary` from 3 repos |
| `backend/app/api/v1/routers/monitored_brands.py` | **Modify** | Add health, cycles endpoints; enrich brand responses |
| `backend/app/api/v1/routers/similarity.py` | **Modify** | Migrate matches to snapshots; add events endpoint |
| `backend/tests/test_api_plan3_integration.py` | **Create** | Integration tests for all new endpoints |

---

## Task 1: Monitoring schemas

**Files:**
- Create: `backend/app/schemas/monitoring.py`
- Test: `backend/tests/test_api_plan3_integration.py` (initial stub)

- [ ] **Step 1: Write the failing test (schema instantiation)**

```python
# backend/tests/test_api_plan3_integration.py
def test_monitoring_schemas_instantiate():
    from app.schemas.monitoring import (
        CycleSummarySchema, ThreatCountsSchema, MonitoringSummarySchema,
        CycleResponse, CycleListResponse,
        DomainCheckDetailSchema, DomainHealthCheckSchema, BrandHealthResponse,
        SignalSchema, MatchSnapshotResponse, MatchSnapshotListResponse,
        EventResponse, EventListResponse,
    )
    from uuid import uuid4
    from datetime import datetime, timezone

    # CycleSummarySchema
    cs = CycleSummarySchema(
        cycle_date="2026-04-12",
        health_status="completed",
        scan_status="completed",
        enrichment_status="completed",
        new_matches_count=3,
        threats_detected=1,
        dismissed_count=5,
    )
    assert cs.health_status == "completed"

    # MonitoringSummarySchema
    ms = MonitoringSummarySchema(
        latest_cycle=cs,
        threat_counts=ThreatCountsSchema(immediate_attention=1, defensive_gap=4, watchlist=20),
        overall_health="healthy",
    )
    assert ms.overall_health == "healthy"
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py::test_monitoring_schemas_instantiate -v
```
Expected: `ImportError` — `app.schemas.monitoring` doesn't exist yet.

- [ ] **Step 3: Write the schemas**

Create `backend/app/schemas/monitoring.py`:

```python
"""Pydantic schemas for monitoring pipeline API endpoints."""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field


# ── Cycle ─────────────────────────────────────────────────────

class CycleSummarySchema(BaseModel):
    cycle_date: date
    health_status: str
    scan_status: str
    enrichment_status: str
    new_matches_count: int = 0
    threats_detected: int = 0
    dismissed_count: int = 0

    model_config = {"from_attributes": True}


class ThreatCountsSchema(BaseModel):
    immediate_attention: int = 0
    defensive_gap: int = 0
    watchlist: int = 0


class MonitoringSummarySchema(BaseModel):
    latest_cycle: CycleSummarySchema | None = None
    threat_counts: ThreatCountsSchema
    overall_health: str = "unknown"  # "healthy" | "warning" | "critical" | "unknown"


class CycleResponse(BaseModel):
    id: UUID
    brand_id: UUID
    organization_id: UUID
    cycle_date: date
    cycle_type: str
    health_status: str
    health_started_at: datetime | None = None
    health_finished_at: datetime | None = None
    scan_status: str
    scan_started_at: datetime | None = None
    scan_finished_at: datetime | None = None
    scan_job_id: UUID | None = None
    enrichment_status: str
    enrichment_started_at: datetime | None = None
    enrichment_finished_at: datetime | None = None
    enrichment_budget: int = 0
    enrichment_total: int = 0
    new_matches_count: int = 0
    escalated_count: int = 0
    dismissed_count: int = 0
    threats_detected: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CycleListResponse(BaseModel):
    items: list[CycleResponse]
    total: int


# ── Health ────────────────────────────────────────────────────

class DomainCheckDetailSchema(BaseModel):
    """Per-tool boolean result + raw detail for one official domain."""
    ok: bool | None = None
    details: dict | None = None


class DomainHealthCheckSchema(BaseModel):
    domain_id: UUID
    domain_name: str
    is_primary: bool
    overall_status: str
    dns: DomainCheckDetailSchema | None = None
    ssl: DomainCheckDetailSchema | None = None
    email_security: DomainCheckDetailSchema | None = None
    headers: DomainCheckDetailSchema | None = None
    takeover: DomainCheckDetailSchema | None = None
    blacklist: DomainCheckDetailSchema | None = None
    safe_browsing: DomainCheckDetailSchema | None = None
    urlhaus: DomainCheckDetailSchema | None = None
    phishtank: DomainCheckDetailSchema | None = None
    suspicious_page: DomainCheckDetailSchema | None = None
    last_check_at: datetime | None = None


class BrandHealthResponse(BaseModel):
    domains: list[DomainHealthCheckSchema]


# ── Match snapshot ────────────────────────────────────────────

class SignalSchema(BaseModel):
    code: str
    severity: str | None = None
    score_adjustment: float | None = None
    description: str | None = None
    source_tool: str | None = None


class MatchSnapshotResponse(BaseModel):
    """Match enriched with derived state from match_state_snapshot."""
    # Core match fields
    id: UUID
    brand_id: UUID
    domain_name: str
    tld: str
    label: str
    score_final: float
    attention_bucket: str | None = None
    matched_rule: str | None = None
    auto_disposition: str | None = None
    auto_disposition_reason: str | None = None
    first_detected_at: datetime
    domain_first_seen: datetime

    # Derived (from match_state_snapshot)
    derived_score: float | None = None
    derived_bucket: str | None = None
    derived_risk: str | None = None
    derived_disposition: str | None = None
    active_signals: list[SignalSchema] = Field(default_factory=list)
    signal_codes: list[str] = Field(default_factory=list)
    llm_assessment: dict | None = None
    state_fingerprint: str | None = None
    last_derived_at: datetime | None = None

    model_config = {"from_attributes": True}


class MatchSnapshotListResponse(BaseModel):
    items: list[MatchSnapshotResponse]
    total: int


# ── Events ────────────────────────────────────────────────────

class EventResponse(BaseModel):
    id: UUID
    event_type: str
    event_source: str
    tool_name: str | None = None
    tool_version: str | None = None
    result_data: dict
    signals: list[dict] | None = None
    score_snapshot: dict | None = None
    cycle_id: UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EventListResponse(BaseModel):
    items: list[EventResponse]
    total: int
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py::test_monitoring_schemas_instantiate -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/monitoring.py backend/tests/test_api_plan3_integration.py
git commit -m "feat(api): add monitoring schemas (cycles, health, snapshots, events)"
```

---

## Task 2: MonitoringQueryService

**Files:**
- Create: `backend/app/services/monitoring_query_service.py`
- Test: `backend/tests/test_api_plan3_integration.py` (append)

This service assembles `monitoring_summary` from 3 repos in one call, avoiding fat route handlers. It also provides helpers used by the health and cycles endpoints.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_api_plan3_integration.py`:

```python
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
    """Service returns cycle + threat counts + derives overall_health from brand_domain_health."""
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

    # One match with a snapshot in immediate_attention
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
    db_session.commit()

    svc = MonitoringQueryService(db_session)
    summary = svc.get_monitoring_summary(brand.id)

    assert summary["latest_cycle"]["health_status"] == "completed"
    assert summary["threat_counts"]["immediate_attention"] == 1
    assert summary["overall_health"] == "healthy"
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py::test_monitoring_query_service_summary_no_data tests/test_api_plan3_integration.py::test_monitoring_query_service_with_cycle_and_health -v
```
Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3a: Add `count_by_bucket_active` to MatchStateSnapshotRepository**

In `backend/app/repositories/match_state_snapshot_repository.py`, add after `count_by_bucket`:

```python
def count_by_bucket_active(self, brand_id: UUID) -> dict[str, int]:
    """Return counts per bucket, excluding auto-dismissed matches."""
    from sqlalchemy import func
    from app.models.similarity_match import SimilarityMatch
    rows = (
        self.db.query(
            MatchStateSnapshot.derived_bucket,
            func.count(MatchStateSnapshot.id),
        )
        .join(SimilarityMatch, MatchStateSnapshot.match_id == SimilarityMatch.id)
        .filter(
            MatchStateSnapshot.brand_id == brand_id,
            SimilarityMatch.auto_disposition.is_(None),
        )
        .group_by(MatchStateSnapshot.derived_bucket)
        .all()
    )
    return {bucket: count for bucket, count in rows}
```

- [ ] **Step 3: Write the service**

Create `backend/app/services/monitoring_query_service.py`:

```python
"""MonitoringQueryService — assembles monitoring dashboard data from multiple repositories."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.monitoring_cycle_repository import MonitoringCycleRepository
from app.repositories.match_state_snapshot_repository import MatchStateSnapshotRepository
from app.repositories.brand_domain_health_repository import BrandDomainHealthRepository


class MonitoringQueryService:
    """
    Read-only aggregation service for the monitoring API layer.
    Composes data from cycle, snapshot, and health repositories.
    Route handlers call this instead of 3 separate repos.
    """

    def __init__(self, db: Session) -> None:
        self.cycle_repo = MonitoringCycleRepository(db)
        self.snapshot_repo = MatchStateSnapshotRepository(db)
        self.health_repo = BrandDomainHealthRepository(db)

    def get_monitoring_summary(self, brand_id: UUID) -> dict:
        """
        Return dict with:
          latest_cycle: dict | None
          threat_counts: dict
          overall_health: str
        """
        # Latest cycle
        cycle = self.cycle_repo.get_latest_for_brand(brand_id)
        latest_cycle = None
        if cycle:
            latest_cycle = {
                "cycle_date": cycle.cycle_date,
                "health_status": cycle.health_status,
                "scan_status": cycle.scan_status,
                "enrichment_status": cycle.enrichment_status,
                "new_matches_count": cycle.new_matches_count or 0,
                "threats_detected": cycle.threats_detected or 0,
                "dismissed_count": cycle.dismissed_count or 0,
            }

        # Threat counts by bucket (from snapshots, excluding auto-dismissed)
        # count_by_bucket does not filter auto-disposed matches, so we use a JOIN-filtered query
        bucket_counts = self.snapshot_repo.count_by_bucket_active(brand_id)
        threat_counts = {
            "immediate_attention": bucket_counts.get("immediate_attention", 0),
            "defensive_gap": bucket_counts.get("defensive_gap", 0),
            "watchlist": bucket_counts.get("watchlist", 0),
        }

        # Overall health from domain health records
        health_records = self.health_repo.list_for_brand(brand_id)
        overall_health = _derive_overall_health(health_records)

        return {
            "latest_cycle": latest_cycle,
            "threat_counts": threat_counts,
            "overall_health": overall_health,
        }


def _derive_overall_health(health_records: list) -> str:
    """
    Aggregate overall_status from all brand domain health records.
    Worst-case wins: critical > warning > healthy > unknown.
    """
    if not health_records:
        return "unknown"
    STATUS_ORDER = {"critical": 3, "warning": 2, "healthy": 1, "unknown": 0}
    worst = max(
        (STATUS_ORDER.get(h.overall_status, 0) for h in health_records),
        default=0
    )
    return {3: "critical", 2: "warning", 1: "healthy", 0: "unknown"}[worst]
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py::test_monitoring_query_service_summary_no_data tests/test_api_plan3_integration.py::test_monitoring_query_service_with_cycle_and_health -v
```
Expected: both PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/monitoring_query_service.py backend/tests/test_api_plan3_integration.py
git commit -m "feat(api): add MonitoringQueryService for dashboard data assembly"
```

---

## Task 3: GET /v1/brands and GET /v1/brands/{id} — add monitoring_summary

**Files:**
- Modify: `backend/app/schemas/monitored_brand.py` — add `monitoring_summary` to `BrandResponse`
- Modify: `backend/app/api/v1/routers/monitored_brands.py` — inject service + populate field
- Test: `backend/tests/test_api_plan3_integration.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_api_plan3_integration.py`:

```python
def test_get_brand_includes_monitoring_summary(client, db_session):
    """GET /v1/brands/{id} response includes monitoring_summary field."""
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
    assert "threat_counts" in data["monitoring_summary"]
    assert "overall_health" in data["monitoring_summary"]
```

Note: `client` fixture needs to be defined. Add this to the test file (or use conftest.py if already available):

```python
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(db_session):
    from app.main import app
    from app.infra.db.session import get_db

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, headers={"x-admin-token": "test"}) as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py::test_get_brand_includes_monitoring_summary -v
```
Expected: FAIL with `AssertionError` — `monitoring_summary` not in response.

- [ ] **Step 3: Modify schemas — add monitoring_summary to BrandResponse**

In `backend/app/schemas/monitored_brand.py`, add to the import:

```python
from app.schemas.monitoring import MonitoringSummarySchema
```

Add field to `BrandResponse`:

```python
class BrandResponse(BaseModel):
    # ... existing fields ...
    monitoring_summary: MonitoringSummarySchema | None = None
```

- [ ] **Step 4: Modify monitored_brands.py — inject service and populate field**

In `monitored_brands.py`:

1. Add import at top:
```python
from app.services.monitoring_query_service import MonitoringQueryService
from app.schemas.monitoring import (
    CycleSummarySchema, ThreatCountsSchema, MonitoringSummarySchema,
)
```

2. Update `_to_brand_response` to accept optional `monitoring_summary` param:
```python
def _to_brand_response(brand, monitoring_summary: MonitoringSummarySchema | None = None) -> BrandResponse:
    return BrandResponse(
        # ... existing fields ...
        monitoring_summary=monitoring_summary,
    )
```

3. Update `list_brands` to build summaries:
```python
@router.get("", response_model=BrandListResponse)
def list_brands(active_only: bool = Query(True), db: Session = Depends(get_db)):
    repo = MonitoredBrandRepository(db)
    brands = repo.list_by_org(PLACEHOLDER_ORG_ID, active_only=active_only)
    svc = MonitoringQueryService(db)
    hydrated = []
    for brand in brands:
        ensure_monitoring_profile_integrity(repo, brand)
        raw = svc.get_monitoring_summary(brand.id)
        summary = _build_monitoring_summary_schema(raw)
        hydrated.append(_to_brand_response(brand, summary))
    db.commit()
    return BrandListResponse(items=hydrated, total=len(hydrated))
```

4. Update `get_brand` similarly:
```python
@router.get("/{brand_id}", response_model=BrandResponse)
def get_brand(brand_id: UUID, db: Session = Depends(get_db)):
    repo = MonitoredBrandRepository(db)
    brand = repo.get(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")
    ensure_monitoring_profile_integrity(repo, brand)
    db.commit()
    svc = MonitoringQueryService(db)
    raw = svc.get_monitoring_summary(brand.id)
    summary = _build_monitoring_summary_schema(raw)
    return _to_brand_response(brand, summary)
```

5. Add helper function:
```python
def _build_monitoring_summary_schema(raw: dict) -> MonitoringSummarySchema:
    latest_cycle = None
    if raw["latest_cycle"]:
        latest_cycle = CycleSummarySchema(**raw["latest_cycle"])
    counts = raw["threat_counts"]
    return MonitoringSummarySchema(
        latest_cycle=latest_cycle,
        threat_counts=ThreatCountsSchema(**counts),
        overall_health=raw["overall_health"],
    )
```

- [ ] **Step 5: Run test to verify it passes**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py::test_get_brand_includes_monitoring_summary -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/monitored_brand.py backend/app/api/v1/routers/monitored_brands.py backend/tests/test_api_plan3_integration.py
git commit -m "feat(api): add monitoring_summary to GET /v1/brands and GET /v1/brands/{id}"
```

---

## Task 4: GET /v1/brands/{id}/health

**Files:**
- Modify: `backend/app/api/v1/routers/monitored_brands.py` — add `/health` endpoint
- Test: `backend/tests/test_api_plan3_integration.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_api_plan3_integration.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py::test_get_brand_health_returns_domain_checks -v
```
Expected: FAIL with 404 — endpoint doesn't exist.

- [ ] **Step 3: Add the /health endpoint to monitored_brands.py**

Add imports:
```python
from app.schemas.monitoring import (
    BrandHealthResponse, DomainHealthCheckSchema, DomainCheckDetailSchema,
    # plus existing monitoring imports ...
)
```

Add the route after the existing `/{brand_id}` GET:
```python
@router.get(
    "/{brand_id}/health",
    response_model=BrandHealthResponse,
    summary="Get health check results for all official domains of a brand",
)
def get_brand_health(brand_id: UUID, db: Session = Depends(get_db)):
    repo = MonitoredBrandRepository(db)
    brand = repo.get(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    health_repo = BrandDomainHealthRepository(db)
    domains_with_health = []

    for dom in brand.domains:
        if not dom.is_active:
            continue
        health = health_repo.get_by_domain(dom.id)
        domains_with_health.append(_build_domain_health_schema(dom, health))

    return BrandHealthResponse(domains=domains_with_health)


def _build_domain_health_schema(domain, health) -> DomainHealthCheckSchema:
    """Map a MonitoredBrandDomain + BrandDomainHealth ORM pair to schema."""
    if health is None:
        return DomainHealthCheckSchema(
            domain_id=domain.id,
            domain_name=domain.domain_name,
            is_primary=domain.is_primary,
            overall_status="unknown",
        )
    return DomainHealthCheckSchema(
        domain_id=domain.id,
        domain_name=domain.domain_name,
        is_primary=domain.is_primary,
        overall_status=health.overall_status,
        dns=DomainCheckDetailSchema(ok=health.dns_ok) if health.dns_ok is not None else None,
        ssl=DomainCheckDetailSchema(
            ok=health.ssl_ok,
            details={"days_remaining": health.ssl_days_remaining} if health.ssl_days_remaining is not None else None,
        ) if health.ssl_ok is not None else None,
        email_security=DomainCheckDetailSchema(
            ok=health.email_security_ok,
            details={"spoofing_risk": health.spoofing_risk} if health.spoofing_risk else None,
        ) if health.email_security_ok is not None else None,
        headers=DomainCheckDetailSchema(
            ok=health.headers_score == "good",
            details={"score": health.headers_score} if health.headers_score else None,
        ) if health.headers_score is not None else None,
        takeover=DomainCheckDetailSchema(ok=not health.takeover_risk) if health.takeover_risk is not None else None,
        blacklist=DomainCheckDetailSchema(ok=not health.blacklisted) if health.blacklisted is not None else None,
        safe_browsing=DomainCheckDetailSchema(ok=not health.safe_browsing_hit) if health.safe_browsing_hit is not None else None,
        urlhaus=DomainCheckDetailSchema(ok=not health.urlhaus_hit) if health.urlhaus_hit is not None else None,
        phishtank=DomainCheckDetailSchema(ok=not health.phishtank_hit) if health.phishtank_hit is not None else None,
        suspicious_page=DomainCheckDetailSchema(ok=not health.suspicious_content) if health.suspicious_content is not None else None,
        last_check_at=health.last_check_at,
    )
```

Also add import at top:
```python
from app.repositories.brand_domain_health_repository import BrandDomainHealthRepository
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py::test_get_brand_health_returns_domain_checks -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/routers/monitored_brands.py backend/tests/test_api_plan3_integration.py
git commit -m "feat(api): add GET /v1/brands/{id}/health endpoint"
```

---

## Task 5: GET /v1/brands/{id}/cycles

**Files:**
- Modify: `backend/app/api/v1/routers/monitored_brands.py` — add `/cycles` endpoint
- Test: `backend/tests/test_api_plan3_integration.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_api_plan3_integration.py`:

```python
def test_get_brand_cycles_returns_history(client, db_session):
    """GET /v1/brands/{id}/cycles returns paginated cycle history."""
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
    # Most recent first
    assert data["items"][0]["cycle_date"] == str(today)
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py::test_get_brand_cycles_returns_history -v
```
Expected: FAIL 404 — endpoint doesn't exist.

- [ ] **Step 3: Add the /cycles endpoint to monitored_brands.py**

```python
@router.get(
    "/{brand_id}/cycles",
    response_model=CycleListResponse,
    summary="Get monitoring cycle history for a brand",
)
def get_brand_cycles(
    brand_id: UUID,
    limit: int = Query(30, ge=1, le=90),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    repo = MonitoredBrandRepository(db)
    brand = repo.get(brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand not found")

    cycle_repo = MonitoringCycleRepository(db)
    cycles = cycle_repo.list_for_brand(brand_id, limit=limit, offset=offset)
    total = db.query(MonitoringCycle).filter(
        MonitoringCycle.brand_id == brand_id
    ).count()
    return CycleListResponse(
        items=[CycleResponse.model_validate(c) for c in cycles],
        total=total,
    )
```

Add missing imports:
```python
from app.repositories.monitoring_cycle_repository import MonitoringCycleRepository
from app.models.monitoring_cycle import MonitoringCycle
from app.schemas.monitoring import CycleListResponse, CycleResponse
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py::test_get_brand_cycles_returns_history -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/routers/monitored_brands.py backend/tests/test_api_plan3_integration.py
git commit -m "feat(api): add GET /v1/brands/{id}/cycles endpoint"
```

---

## Task 6: GET /v1/brands/{id}/matches — migrate to match_state_snapshot

**Files:**
- Modify: `backend/app/api/v1/routers/similarity.py` — rewrite `list_matches` to join snapshots
- Test: `backend/tests/test_api_plan3_integration.py` (append)

The existing endpoint queries `SimilarityRepository.list_matches()` which reads from `similarity_match` directly. The new version reads from `match_state_snapshot` (via `MatchStateSnapshotRepository.list_for_brand`) and joins in the base match data.

**Important:** The existing `MatchResponse` schema is kept for backward compatibility. A new `MatchSnapshotResponse` (from Task 1) is used when `include_llm=true`. The existing `list_matches` filter params (`status`, `risk_level`, `attention_bucket`) are preserved but a new `bucket` filter is added to route to `list_for_brand` by `derived_bucket`.

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_api_plan3_integration.py`:

```python
def test_list_matches_with_snapshot_data(client, db_session):
    """GET /v1/brands/{id}/matches?include_llm=true returns derived fields."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.similarity_match import SimilarityMatch
    from app.models.match_state_snapshot import MatchStateSnapshot
    from uuid import uuid4
    from datetime import datetime, timezone

    org_id = uuid4()
    now = datetime.now(timezone.utc)
    brand = MonitoredBrand(
        id=uuid4(), organization_id=org_id,
        brand_name="MatchBrand", primary_brand_name="MatchBrand",
        brand_label="matchbrand", is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    match = SimilarityMatch(
        id=uuid4(), brand_id=brand.id,
        domain_name="matchbrand-fake.com", tld="com", label="matchbrand-fake",
        score_final=0.8, attention_bucket="immediate_attention",
        actionability_score=0.8, reasons=[], attention_reasons=[],
        recommended_action="block", risk_level="high",
        first_detected_at=now, domain_first_seen=now,
    )
    db_session.add(match)
    db_session.flush()

    snapshot = MatchStateSnapshot(
        id=uuid4(), match_id=match.id, brand_id=brand.id,
        organization_id=org_id,
        derived_score=0.87, derived_bucket="immediate_attention",
        derived_risk="critical", active_signals=[{"code": "safe_browsing_hit", "severity": "critical"}],
        signal_codes=["safe_browsing_hit"],
        state_fingerprint="fp_match", last_derived_at=now,
        llm_assessment={"parecer_resumido": "Suspicious domain."},
    )
    db_session.add(snapshot)
    db_session.commit()

    resp = client.get(f"/v1/brands/{brand.id}/matches?include_llm=true")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    item = next(i for i in data["items"] if i["id"] == str(match.id))
    assert item["derived_score"] == pytest.approx(0.87, abs=0.01)
    assert item["derived_risk"] == "critical"
    assert item["llm_assessment"]["parecer_resumido"] == "Suspicious domain."
    assert "safe_browsing_hit" in item["signal_codes"]
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py::test_list_matches_with_snapshot_data -v
```
Expected: FAIL — `include_llm` param not accepted, derived fields not present.

- [ ] **Step 3: Update similarity.py list_matches**

Replace the `list_matches` function in `similarity.py`:

```python
from app.repositories.match_state_snapshot_repository import MatchStateSnapshotRepository
from app.models.similarity_match import SimilarityMatch as SimilarityMatchModel
from app.schemas.monitoring import MatchSnapshotResponse, MatchSnapshotListResponse, SignalSchema

@router.get(
    "/brands/{brand_id}/matches",
    summary="List similarity matches for a brand",
)
def list_matches(
    brand_id: UUID,
    status: str | None = Query(None),
    risk_level: str | None = Query(None),
    attention_bucket: str | None = Query(None),
    bucket: str | None = Query(None, description="Filter by derived_bucket from snapshot"),
    exclude_auto_dismissed: bool = Query(True),
    include_llm: bool = Query(False, description="Include derived snapshot fields and LLM assessment"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    repo = SimilarityRepository(db)
    snapshot_repo = MatchStateSnapshotRepository(db)

    if include_llm:
        # Read from match_state_snapshot for derived data
        effective_bucket = bucket or attention_bucket
        snapshots = snapshot_repo.list_for_brand(
            brand_id,
            bucket=effective_bucket,
            exclude_auto_dismissed=exclude_auto_dismissed,
            limit=limit,
            offset=offset,
        )
        # Load base match data for each snapshot
        match_ids = [s.match_id for s in snapshots]
        matches_by_id = {}
        if match_ids:
            rows = db.query(SimilarityMatchModel).filter(
                SimilarityMatchModel.id.in_(match_ids)
            ).all()
            matches_by_id = {m.id: m for m in rows}

        items = []
        for snap in snapshots:
            m = matches_by_id.get(snap.match_id)
            if m is None:
                continue
            items.append(MatchSnapshotResponse(
                id=m.id,
                brand_id=m.brand_id,
                domain_name=m.domain_name,
                tld=m.tld,
                label=m.label,
                score_final=m.score_final,
                attention_bucket=m.attention_bucket,
                matched_rule=m.matched_rule,
                auto_disposition=m.auto_disposition,
                auto_disposition_reason=m.auto_disposition_reason,
                first_detected_at=m.first_detected_at,
                domain_first_seen=m.domain_first_seen,
                derived_score=snap.derived_score,
                derived_bucket=snap.derived_bucket,
                derived_risk=snap.derived_risk,
                derived_disposition=snap.derived_disposition,
                active_signals=[SignalSchema(**s) for s in (snap.active_signals or [])],
                signal_codes=list(snap.signal_codes or []),
                llm_assessment=snap.llm_assessment,
                state_fingerprint=snap.state_fingerprint,
                last_derived_at=snap.last_derived_at,
            ))

        # Count mirrors the same filters used by list_for_brand to avoid total/items mismatch
        count_q = db.query(MatchStateSnapshot).filter(
            MatchStateSnapshot.brand_id == brand_id
        )
        if effective_bucket:
            count_q = count_q.filter(MatchStateSnapshot.derived_bucket == effective_bucket)
        if exclude_auto_dismissed:
            count_q = count_q.join(
                SimilarityMatchModel,
                MatchStateSnapshot.match_id == SimilarityMatchModel.id,
            ).filter(SimilarityMatchModel.auto_disposition.is_(None))
        total = count_q.count()

        return MatchSnapshotListResponse(items=items, total=total)

    # Legacy path: no snapshot data requested
    matches = repo.list_matches(
        brand_id,
        status=status,
        risk_level=risk_level,
        attention_bucket=attention_bucket,
        limit=limit,
        offset=offset,
    )
    total = repo.count_matches(
        brand_id,
        status=status,
        risk_level=risk_level,
        attention_bucket=attention_bucket,
    )
    active_job = repo.get_active_scan_job_for_brand(brand_id)
    latest_job = repo.get_latest_scan_job_for_brand(brand_id)
    return MatchListResponse(
        items=matches,
        total=total,
        active_scan=serialize_scan_job(active_job) if active_job else None,
        last_scan=serialize_scan_job(latest_job) if latest_job else None,
    )
```

Add missing import:
```python
from app.models.match_state_snapshot import MatchStateSnapshot
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py::test_list_matches_with_snapshot_data -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/routers/similarity.py backend/tests/test_api_plan3_integration.py
git commit -m "feat(api): add include_llm param to GET /v1/brands/{id}/matches"
```

---

## Task 7: GET /v1/matches/{id}/events

**Files:**
- Modify: `backend/app/api/v1/routers/similarity.py` — add events endpoint
- Test: `backend/tests/test_api_plan3_integration.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_api_plan3_integration.py`:

```python
def test_get_match_events_timeline(client, db_session):
    """GET /v1/matches/{id}/events returns all events for a match ordered newest first."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.similarity_match import SimilarityMatch
    from app.models.monitoring_event import MonitoringEvent
    from uuid import uuid4
    from datetime import datetime, timezone, timedelta

    org_id = uuid4()
    now = datetime.now(timezone.utc)
    brand = MonitoredBrand(
        id=uuid4(), organization_id=org_id,
        brand_name="EventsBrand", primary_brand_name="EventsBrand",
        brand_label="eventsbrand", is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    match = SimilarityMatch(
        id=uuid4(), brand_id=brand.id,
        domain_name="eventsbrand-fake.com", tld="com", label="eventsbrand-fake",
        score_final=0.75, attention_bucket="defensive_gap",
        actionability_score=0.75, reasons=[], attention_reasons=[],
        recommended_action="monitor", risk_level="medium",
        first_detected_at=now, domain_first_seen=now,
    )
    db_session.add(match)
    db_session.flush()

    for i, tool in enumerate(["dns_lookup", "whois", "ssl_check"]):
        db_session.add(MonitoringEvent(
            id=uuid4(), organization_id=org_id, brand_id=brand.id,
            match_id=match.id,
            event_type="tool_execution", event_source="enrichment",
            tool_name=tool,
            result_data={"tool": tool, "ok": True},
            created_at=now + timedelta(seconds=i),
        ))
    db_session.commit()

    resp = client.get(f"/v1/matches/{match.id}/events")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    # Newest first
    assert data["items"][0]["tool_name"] == "ssl_check"
```

- [ ] **Step 2: Run test to verify it fails**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py::test_get_match_events_timeline -v
```
Expected: FAIL 404 — endpoint doesn't exist.

- [ ] **Step 3: Add the events endpoint to similarity.py**

```python
from app.repositories.monitoring_event_repository import MonitoringEventRepository
from app.models.monitoring_event import MonitoringEvent
from app.schemas.monitoring import EventResponse, EventListResponse

@router.get(
    "/matches/{match_id}/events",
    response_model=EventListResponse,
    summary="Get monitoring event timeline for a match",
)
def get_match_events(
    match_id: UUID,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    repo = SimilarityRepository(db)
    match = repo.get_match(match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    event_repo = MonitoringEventRepository(db)
    events = event_repo.list_for_match(match_id=match_id, limit=limit, offset=offset)
    total = db.query(MonitoringEvent).filter(
        MonitoringEvent.match_id == match_id
    ).count()

    return EventListResponse(
        items=[EventResponse.model_validate(e) for e in events],
        total=total,
    )
```

- [ ] **Step 4: Run test to verify it passes**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py::test_get_match_events_timeline -v
```
Expected: PASS

- [ ] **Step 5: Run full test suite**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py -v
```
Expected: all Plan 3 tests pass

Also run:
```
cd backend && python -m pytest -x -q
```
Expected: 59+ tests pass (Plan 2 tests still green, pre-existing failure unchanged)

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/routers/similarity.py backend/tests/test_api_plan3_integration.py
git commit -m "feat(api): add GET /v1/matches/{id}/events timeline endpoint"
```

---

## Task 8: Register new routes in router config (if needed)

**Files:**
- Check: `backend/app/api/v1/routers/__init__.py` or `backend/app/main.py`

- [ ] **Step 1: Verify routes are auto-registered**

Check if any explicit route registration is needed by reading the router include pattern in `main.py` or `__init__.py`. If `monitored_brands.py` and `similarity.py` are already auto-included, no action needed.

- [ ] **Step 2: Run smoke test**

```
cd backend && python -m pytest tests/test_api_plan3_integration.py -v --tb=short
```
Expected: all tests pass, no import errors.

- [ ] **Step 3: Final run of all tests**

```
cd backend && python -m pytest -q
```
Expected: 65+ tests pass (7 new Plan 3 tests + 59 existing).

- [ ] **Step 4: Commit if any registration was needed**

```bash
git add .
git commit -m "feat(api): wire monitoring endpoints into router config"
```
