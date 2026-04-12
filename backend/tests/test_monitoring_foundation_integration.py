"""
Integration smoke test: verifies the foundation tables work end-to-end
against a real DB session (requires running DB).

Run with: pytest tests/test_monitoring_foundation_integration.py -v -m integration
"""
from __future__ import annotations
import sys, uuid, pytest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Skip if no DB available
pytestmark = pytest.mark.integration


def test_cycle_create_and_stage_transitions(db_session):
    from app.repositories.monitoring_cycle_repository import MonitoringCycleRepository
    from app.services.monitoring_cycle_service import MonitoringCycleService
    from app.models.monitored_brand import MonitoredBrand

    org_id = uuid.uuid4()

    # monitoring_cycle has a FK to monitored_brand — create a real brand row first
    brand = MonitoredBrand(
        organization_id=org_id,
        brand_name=f"smoke-test-brand-{uuid.uuid4().hex[:8]}",
        primary_brand_name="smoke",
        brand_label="smoke",
    )
    db_session.add(brand)
    db_session.flush()  # get brand.id without committing
    brand_id = brand.id

    repo = MonitoringCycleRepository(db_session)
    svc = MonitoringCycleService(db_session, cycle_repo=repo)

    cycle, created = repo.get_or_create_today(brand_id=brand_id, organization_id=org_id)
    assert created is True
    assert cycle.health_status == "pending"

    svc.begin_stage(cycle.id, stage="health")
    db_session.commit()
    db_session.refresh(cycle)
    assert cycle.health_status == "running"
    assert cycle.health_started_at is not None

    svc.finish_stage(cycle.id, stage="health", success=True)
    db_session.commit()
    db_session.refresh(cycle)
    assert cycle.health_status == "completed"
    assert cycle.health_finished_at is not None

    # Second call returns existing cycle
    cycle2, created2 = repo.get_or_create_today(brand_id=brand_id, organization_id=org_id)
    assert created2 is False
    assert cycle2.id == cycle.id
