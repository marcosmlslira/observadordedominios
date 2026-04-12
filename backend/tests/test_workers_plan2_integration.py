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


def test_health_worker_run_cycle_updates_cycle_status(db_session):
    """health_worker run_health_cycle updates monitoring_cycle.health_status."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.monitored_brand_domain import MonitoredBrandDomain
    from app.worker.health_worker import run_health_cycle
    from unittest.mock import patch
    from uuid import uuid4
    from datetime import datetime, timezone

    org_id = uuid4()
    now = datetime.now(timezone.utc)

    brand = MonitoredBrand(
        id=uuid4(), organization_id=org_id,
        brand_name="HealthCo", primary_brand_name="HealthCo", brand_label="healthco",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    domain = MonitoredBrandDomain(
        id=uuid4(), brand_id=brand.id,
        domain_name="healthco.com",
        registrable_domain="healthco.com",
        registrable_label="healthco",
        public_suffix="com",
        is_active=True,
        created_at=now, updated_at=now,
    )
    db_session.add(domain)
    db_session.commit()

    with patch(
        "app.worker.health_worker.run_health_check_domain",
        return_value={"tools_run": 10, "tools_failed": 0, "overall_status": "healthy"},
    ):
        run_health_cycle(db_session)

    from app.models.monitoring_cycle import MonitoringCycle
    from datetime import date
    cycle = db_session.query(MonitoringCycle).filter(
        MonitoringCycle.brand_id == brand.id,
        MonitoringCycle.cycle_date == date.today(),
    ).first()
    assert cycle is not None
    assert cycle.health_status == "completed"


def test_compute_enrichment_budget_rank_top_50(db_session):
    """compute_enrichment_budget_rank assigns rank 1..N to top-50 matches."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.similarity_match import SimilarityMatch
    from app.repositories.similarity_repository import SimilarityRepository
    from uuid import uuid4
    from datetime import datetime, timezone

    org_id = uuid4()
    now = datetime.now(timezone.utc)
    brand = MonitoredBrand(
        id=uuid4(), organization_id=org_id,
        brand_name="RankCo", primary_brand_name="RankCo", brand_label="rankco",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    for i, bucket in enumerate(["immediate_attention", "defensive_gap", "watchlist",
                                 "defensive_gap", "watchlist"]):
        m = SimilarityMatch(
            id=uuid4(), brand_id=brand.id,
            domain_name=f"rank{i}-brand.com", tld="com", label=f"rank{i}",
            score_final=0.7 - i * 0.05,
            attention_bucket=bucket,
            actionability_score=0.7 - i * 0.05,
            reasons=[],
            attention_reasons=[],
            recommended_action="monitor",
            risk_level="medium",
            first_detected_at=now,
            domain_first_seen=now,
        )
        db_session.add(m)
    db_session.commit()

    repo = SimilarityRepository(db_session)
    count = repo.compute_enrichment_budget_rank(brand.id, limit=50)

    assert count == 5

    top = db_session.query(SimilarityMatch).filter(
        SimilarityMatch.brand_id == brand.id,
        SimilarityMatch.enrichment_budget_rank == 1,
    ).one()
    assert top.attention_bucket == "immediate_attention"


def test_scan_worker_creates_cycle_and_ranks(db_session):
    """scan_worker run_scan_cycle creates monitoring_cycle and calls rank after scan."""
    from app.models.monitored_brand import MonitoredBrand
    from app.worker.scan_worker import run_scan_cycle
    from unittest.mock import patch, MagicMock
    from uuid import uuid4
    from datetime import date

    org_id = uuid4()
    brand = MonitoredBrand(
        id=uuid4(), organization_id=org_id,
        brand_name="ScanCo", primary_brand_name="ScanCo", brand_label="scanco",
        is_active=True,
    )
    db_session.add(brand)
    db_session.commit()

    with patch("app.worker.scan_worker.run_similarity_scan_all", return_value={}), \
         patch("app.worker.scan_worker.SimilarityRepository") as mock_repo_cls:
        mock_repo = MagicMock()
        mock_repo.compute_enrichment_budget_rank.return_value = 0
        mock_repo_cls.return_value = mock_repo
        run_scan_cycle(db_session)

    from app.models.monitoring_cycle import MonitoringCycle
    cycle = db_session.query(MonitoringCycle).filter(
        MonitoringCycle.brand_id == brand.id,
        MonitoringCycle.cycle_date == date.today(),
    ).first()
    assert cycle is not None
    assert cycle.scan_status == "completed"
    mock_repo.compute_enrichment_budget_rank.assert_any_call(brand.id, limit=50)


def test_run_enrichment_cycle_match_creates_events_and_snapshot(db_session):
    """Enrichment creates tool events and upserts match_state_snapshot."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.similarity_match import SimilarityMatch
    from app.models.monitoring_cycle import MonitoringCycle
    from app.services.use_cases.run_enrichment_cycle_match import run_enrichment_cycle_match
    from unittest.mock import patch
    from uuid import uuid4
    from datetime import date, datetime, timezone

    org_id = uuid4()
    now = datetime.now(timezone.utc)
    brand = MonitoredBrand(
        id=uuid4(), organization_id=org_id,
        brand_name="EnrichCo", primary_brand_name="EnrichCo", brand_label="enrichco",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    match = SimilarityMatch(
        id=uuid4(), brand_id=brand.id,
        domain_name="enrichco-fake.com", tld="com", label="enrichco-fake",
        score_final=0.65, attention_bucket="defensive_gap", actionability_score=0.65,
        matched_rule="typo_candidate",
        reasons=[], attention_reasons=[], recommended_action="monitor",
        risk_level="medium", first_detected_at=now, domain_first_seen=now,
    )
    db_session.add(match)

    cycle = MonitoringCycle(
        id=uuid4(), brand_id=brand.id,
        organization_id=org_id,
        cycle_date=date.today(),
    )
    db_session.add(cycle)
    db_session.commit()

    fake_dns = {"records": [{"type": "A", "value": "1.2.3.4"}]}

    with patch(
        "app.services.use_cases.run_enrichment_cycle_match._run_tool",
        return_value=fake_dns,
    ):
        result = run_enrichment_cycle_match(
            db_session,
            match,
            brand=brand,
            cycle_id=cycle.id,
        )

    assert result["auto_dismissed"] is False
    assert result["tools_run"] > 0

    from app.models.match_state_snapshot import MatchStateSnapshot
    snapshot = db_session.query(MatchStateSnapshot).filter(
        MatchStateSnapshot.match_id == match.id
    ).first()
    assert snapshot is not None
    assert snapshot.derived_score is not None


def test_enrichment_worker_processes_ranked_matches(db_session):
    """enrichment_worker processes matches with enrichment_budget_rank set."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.similarity_match import SimilarityMatch
    from app.worker.enrichment_worker import run_enrichment_cycle
    from unittest.mock import patch, MagicMock
    from uuid import uuid4
    from datetime import date, datetime, timezone

    org_id = uuid4()
    now = datetime.now(timezone.utc)
    brand = MonitoredBrand(
        id=uuid4(), organization_id=org_id,
        brand_name="EnrichWorkerCo", primary_brand_name="EnrichWorkerCo",
        brand_label="enrichworkerco", is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    match = SimilarityMatch(
        id=uuid4(), brand_id=brand.id,
        domain_name="enrichworkerco-fake.com", tld="com", label="fake",
        score_final=0.7, attention_bucket="defensive_gap",
        actionability_score=0.7, enrichment_budget_rank=1,
        reasons=[], attention_reasons=[], recommended_action="monitor",
        risk_level="medium", first_detected_at=now, domain_first_seen=now,
    )
    db_session.add(match)
    db_session.commit()

    enrich_result = {
        "tools_run": 12, "tools_failed": 0,
        "auto_dismissed": False, "dismiss_rule": None, "derived_bucket": "defensive_gap",
    }

    with patch(
        "app.worker.enrichment_worker.run_enrichment_cycle_match",
        return_value=enrich_result,
    ) as mock_enrich:
        run_enrichment_cycle(db_session)

    mock_enrich.assert_called_once()
    from app.models.monitoring_cycle import MonitoringCycle
    cycle = db_session.query(MonitoringCycle).filter(
        MonitoringCycle.brand_id == brand.id,
        MonitoringCycle.cycle_date == date.today(),
    ).first()
    assert cycle is not None
    assert cycle.enrichment_status == "completed"


def test_assessment_worker_processes_snapshots_needing_llm(db_session):
    """assessment_worker finds snapshots needing LLM and calls generate_llm_assessment."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.similarity_match import SimilarityMatch
    from app.models.match_state_snapshot import MatchStateSnapshot
    from app.worker.assessment_worker import run_assessment_cycle
    from unittest.mock import patch
    from uuid import uuid4
    from datetime import datetime, timezone

    org_id = uuid4()
    now = datetime.now(timezone.utc)
    brand = MonitoredBrand(
        id=uuid4(), organization_id=org_id,
        brand_name="AssessCo", primary_brand_name="AssessCo", brand_label="assessco",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    match = SimilarityMatch(
        id=uuid4(), brand_id=brand.id,
        domain_name="assessco-bad.com", tld="com", label="assessco-bad",
        score_final=0.75, attention_bucket="immediate_attention",
        actionability_score=0.75,
        reasons=[], attention_reasons=[], recommended_action="block",
        risk_level="high", first_detected_at=now, domain_first_seen=now,
    )
    db_session.add(match)
    db_session.flush()

    snapshot = MatchStateSnapshot(
        id=uuid4(), match_id=match.id, brand_id=brand.id,
        organization_id=org_id,
        derived_score=0.75, derived_bucket="immediate_attention",
        derived_risk="high", active_signals=[], signal_codes=[],
        state_fingerprint="fp_new",
        llm_source_fingerprint=None,
        last_derived_at=datetime.now(timezone.utc),
    )
    db_session.add(snapshot)
    db_session.commit()

    fake_llm_result = {"parecer_resumido": "Domain suspicious.", "risco_score": 85}

    with patch(
        "app.worker.assessment_worker.generate_llm_assessment",
        return_value=fake_llm_result,
    ):
        run_assessment_cycle(db_session)

    db_session.refresh(snapshot)
    assert snapshot.llm_assessment == fake_llm_result
    assert snapshot.llm_source_fingerprint == "fp_new"
