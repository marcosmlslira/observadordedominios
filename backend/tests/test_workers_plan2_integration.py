import pytest
from unittest.mock import patch
from uuid import uuid4
from app.services.use_cases.run_health_check_domain import run_health_check_domain


def test_run_health_check_domain_creates_events(db_session):
    """Health check creates events for each tool and returns summary."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.monitored_brand_domain import MonitoredBrandDomain
    from app.models.monitoring_cycle import MonitoringCycle
    from datetime import date, datetime, timezone

    org_id = uuid4()

    brand = MonitoredBrand(
        id=uuid4(), organization_id=org_id,
        brand_name="Acme", primary_brand_name="Acme", brand_label="acme",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    now = datetime.now(timezone.utc)
    domain = MonitoredBrandDomain(
        id=uuid4(), brand_id=brand.id,
        domain_name="acme.com",
        registrable_domain="acme.com",
        registrable_label="acme",
        public_suffix="com",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(domain)

    cycle = MonitoringCycle(
        id=uuid4(), brand_id=brand.id,
        organization_id=org_id,
        cycle_date=date.today(),
    )
    db_session.add(cycle)
    db_session.commit()

    fake_result = {"records": [{"type": "A", "value": "1.2.3.4"}]}

    with patch(
        "app.services.use_cases.run_health_check_domain._run_tool",
        return_value=fake_result,
    ):
        summary = run_health_check_domain(
            db_session,
            domain,
            brand_id=brand.id,
            organization_id=org_id,
            cycle_id=cycle.id,
        )

    assert summary["tools_run"] == 10
    assert summary["tools_failed"] == 0

    from app.models.monitoring_event import MonitoringEvent
    events = db_session.query(MonitoringEvent).filter(
        MonitoringEvent.brand_domain_id == domain.id
    ).all()
    assert len(events) == 10
