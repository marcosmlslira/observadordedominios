# Workers Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the 4-worker monitoring pipeline — `health_worker`, `scan_worker`, `enrichment_worker`, `assessment_worker` — connecting the Plan 1 data layer to real scheduled execution.

**Architecture:** Workers are independent Python processes (APScheduler). Each worker creates `monitoring_event` records for every tool result, then calls `StateAggregator` to recalculate materialized state. Workers never read their own events — they only write events and delegate aggregation. `scan_worker` replaces the inline enrichment in `similarity_worker` with a deferred ranking system; `enrichment_worker` processes the top-50 ranked matches in a dedicated 12:00 cycle.

**Tech Stack:** APScheduler (already used), SQLAlchemy ORM, existing tool services (`DnsLookupService`, etc.), `StateAggregator` + all repositories from Plan 1, OpenRouter (via `generate_llm_assessment`).

---

## Key API Contracts (from Plan 1)

These are exact signatures that all workers must use:

```python
# MonitoringCycleRepository — get_or_create cycle first, then begin_stage
cycle, created = MonitoringCycleRepository(db).get_or_create_today(
    brand_id=brand.id, organization_id=brand.organization_id
)
if created:
    db.commit()
# begin_stage takes cycle_id (UUID), not brand_id. Returns None.
MonitoringCycleService(db).begin_stage(cycle.id, stage="health")
MonitoringCycleService(db).finish_stage(cycle.id, stage="health", success=True)

# MatchStateSnapshotRepository — method is get_by_match, not get_by_match_id
MatchStateSnapshotRepository(db).get_by_match(match_id)

# MonitoringCycleService — use service methods for counters, not repo directly
svc.record_dismissed(cycle.id)   # increments dismissed_count
svc.record_escalated(cycle.id)   # increments escalated_count

# StateAggregator — commits internally; do NOT commit immediately after
StateAggregator(db).recalculate_match_snapshot(...)
StateAggregator(db).recalculate_domain_health(...)
```

---

## Event Classification Values

Spec §3.2 defines these values (no DB CHECK constraint — comment only):
- `event_type`: `"tool_execution"` | `"llm_assessment"` | `"state_change"` | `"auto_disposition"`
- `event_source`: `"health_check"` | `"enrichment"` | `"manual"` | `"scan"` | `"assessment"` *(assessment added by this plan)*

---

## Deferred Features (§4.6 Resiliency)

The following spec §4.6 features are intentionally deferred to a later plan:
- **Dead letter**: marking matches with 3 consecutive failed enrichments for manual review
- **Heartbeat-to-DB**: workers updating `monitoring_cycle.updated_at` periodically
- **Alert**: ≥2 days consecutive incomplete cycles → admin alert

Workers do implement heartbeat logging (`emit_heartbeat`) but do not write to DB on each heartbeat.

---

## File Structure

**Create:**
- `backend/app/services/use_cases/run_health_check_domain.py` — Health check for one official brand domain (10 tools → events → health recalculation)
- `backend/app/services/use_cases/run_enrichment_cycle_match.py` — Enrich one match (tools → events → snapshot recalculation → auto-dismiss)
- `backend/app/worker/health_worker.py` — Orchestrates health_worker cycle per brand
- `backend/app/worker/scan_worker.py` — Refactored scan worker with cycle tracking + enrichment budget ranking
- `backend/app/worker/enrichment_worker.py` — Processes top-50 ranked matches per brand
- `backend/app/worker/assessment_worker.py` — LLM assessment loop (every 15 min)

**Modify:**
- `backend/app/repositories/similarity_repository.py` — Add `compute_enrichment_budget_rank(brand_id)` method
- `backend/app/services/use_cases/run_similarity_scan.py` — Remove inline `enrich_similarity_match` calls (deferred to enrichment_worker)
- `infra/stack.dev.yml` — Replace `similarity_worker` with 4 dedicated worker service entries

**Tests:**
- `backend/tests/test_workers_plan2_integration.py` — Integration tests for key worker behaviors

---

## Task 1: `run_health_check_domain` use case

**Files:**
- Create: `backend/app/services/use_cases/run_health_check_domain.py`
- Test: `backend/tests/test_workers_plan2_integration.py`

### Context

`StateAggregator.recalculate_domain_health()` already reads the latest tool events and derives `overall_status`. This use case just runs the tools, creates events, and calls the aggregator.

Existing tools are at `backend/app/services/use_cases/tools/`. The idempotency guard `MonitoringEventRepository.event_exists_for_cycle(cycle_id, tool_name, brand_domain_id=...)` already exists.

- [ ] **Step 1.1: Write the failing test**

```python
# backend/tests/test_workers_plan2_integration.py
import pytest
from unittest.mock import patch
from uuid import uuid4
from app.services.use_cases.run_health_check_domain import run_health_check_domain


def test_run_health_check_domain_creates_events(db_session):
    """Health check creates events for each tool and returns summary."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.monitored_brand_domain import MonitoredBrandDomain
    from app.models.monitoring_cycle import MonitoringCycle
    from datetime import date

    brand = MonitoredBrand(
        id=uuid4(), organization_id=uuid4(),
        brand_name="Acme", brand_label="acme",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    domain = MonitoredBrandDomain(
        id=uuid4(), brand_id=brand.id,
        organization_id=brand.organization_id,
        domain_name="acme.com", is_active=True,
    )
    db_session.add(domain)

    cycle = MonitoringCycle(
        id=uuid4(), brand_id=brand.id,
        organization_id=brand.organization_id,
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
            organization_id=brand.organization_id,
            cycle_id=cycle.id,
        )

    assert summary["tools_run"] == 10
    assert summary["tools_failed"] == 0

    from app.models.monitoring_event import MonitoringEvent
    events = db_session.query(MonitoringEvent).filter(
        MonitoringEvent.brand_domain_id == domain.id
    ).all()
    assert len(events) == 10
```

- [ ] **Step 1.2: Run test to verify it fails**

```
docker exec -it <backend_container> pytest backend/tests/test_workers_plan2_integration.py::test_run_health_check_domain_creates_events -v
```
Expected: ImportError — `run_health_check_domain` not found

- [ ] **Step 1.3: Implement `run_health_check_domain`**

```python
# backend/app/services/use_cases/run_health_check_domain.py
"""Health check use case for one official brand domain.

Runs 10 monitoring tools, creates a monitoring_event per tool result,
then calls StateAggregator to recalculate brand_domain_health.
"""
from __future__ import annotations

import importlib
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.monitored_brand_domain import MonitoredBrandDomain
from app.repositories.monitoring_event_repository import MonitoringEventRepository
from app.services.state_aggregator import StateAggregator

logger = logging.getLogger(__name__)

# Tools run during health check, in order
_HEALTH_TOOLS: list[tuple[str, str]] = [
    ("dns_lookup",          "app.services.use_cases.tools.dns_lookup.DnsLookupService"),
    ("ssl_check",           "app.services.use_cases.tools.ssl_check.SslCheckService"),
    ("http_headers",        "app.services.use_cases.tools.http_headers.HttpHeadersService"),
    ("email_security",      "app.services.use_cases.tools.email_security.EmailSecurityService"),
    ("subdomain_takeover",  "app.services.use_cases.tools.subdomain_takeover_check.SubdomainTakeoverCheckService"),
    ("blacklist_check",     "app.services.use_cases.tools.blacklist_check.BlacklistCheckService"),
    ("safe_browsing",       "app.services.use_cases.tools.safe_browsing_check.SafeBrowsingCheckService"),
    ("urlhaus",             "app.services.use_cases.tools.urlhaus_check.UrlhausCheckService"),
    ("phishtank",           "app.services.use_cases.tools.phishtank_check.PhishTankCheckService"),
    ("suspicious_page",     "app.services.use_cases.tools.suspicious_page.SuspiciousPageService"),
]


def _run_tool(tool_class_path: str, domain: str) -> dict:
    """Import and instantiate a tool service, then call run(domain)."""
    module_path, class_name = tool_class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    service = getattr(module, class_name)()
    result = service.run(domain)
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if hasattr(result, "dict"):
        return result.dict()
    return result if isinstance(result, dict) else {}


def run_health_check_domain(
    db: Session,
    brand_domain: MonitoredBrandDomain,
    *,
    brand_id: UUID,
    organization_id: UUID,
    cycle_id: UUID,
) -> dict:
    """Run 10 health tools for one official brand domain.

    Creates one monitoring_event per tool. Skips tools already run
    for this cycle (idempotency). Calls StateAggregator after all tools.

    Returns:
        {"tools_run": int, "tools_failed": int, "overall_status": str}
    """
    domain_name = brand_domain.domain_name
    event_repo = MonitoringEventRepository(db)
    tools_run = 0
    tools_failed = 0

    for tool_name, tool_class_path in _HEALTH_TOOLS:
        # Idempotency: skip if already ran for this cycle + target
        if event_repo.event_exists_for_cycle(
            cycle_id=cycle_id,
            tool_name=tool_name,
            brand_domain_id=brand_domain.id,
        ):
            logger.debug(
                "Skipping %s for domain=%s (already in cycle)", tool_name, domain_name
            )
            tools_run += 1
            continue

        try:
            result_data = _run_tool(tool_class_path, domain_name)
            event_repo.create(
                organization_id=organization_id,
                brand_id=brand_id,
                brand_domain_id=brand_domain.id,
                cycle_id=cycle_id,
                event_type="tool_execution",
                event_source="health_check",
                tool_name=tool_name,
                result_data=result_data,
            )
            tools_run += 1
            logger.debug("health_check tool=%s domain=%s OK", tool_name, domain_name)
        except Exception:
            tools_failed += 1
            logger.exception(
                "health_check tool=%s domain=%s FAILED", tool_name, domain_name
            )
            # Record failure event so the aggregator knows the tool ran
            event_repo.create(
                organization_id=organization_id,
                brand_id=brand_id,
                brand_domain_id=brand_domain.id,
                cycle_id=cycle_id,
                event_type="tool_execution",
                event_source="health_check",
                tool_name=tool_name,
                result_data={"error": "tool_failed"},
            )

    db.commit()

    # Recalculate brand_domain_health from all recorded events
    aggregator = StateAggregator(db)
    aggregator.recalculate_domain_health(
        brand_domain_id=brand_domain.id,
        brand_id=brand_id,
        organization_id=organization_id,
    )
    # StateAggregator commits internally — no additional commit needed here

    from app.repositories.brand_domain_health_repository import BrandDomainHealthRepository
    health = BrandDomainHealthRepository(db).get_by_domain(brand_domain.id)
    overall_status = health.overall_status if health else "unknown"

    return {
        "tools_run": tools_run,
        "tools_failed": tools_failed,
        "overall_status": overall_status,
    }
```

- [ ] **Step 1.4: Run test to verify it passes**

```
docker exec -it <backend_container> pytest backend/tests/test_workers_plan2_integration.py::test_run_health_check_domain_creates_events -v
```
Expected: PASS

- [ ] **Step 1.5: Commit**

```bash
git add backend/app/services/use_cases/run_health_check_domain.py \
        backend/tests/test_workers_plan2_integration.py
git commit -m "feat(workers): add run_health_check_domain use case"
```

---

## Task 2: `health_worker.py`

**Files:**
- Create: `backend/app/worker/health_worker.py`
- Test: append to `backend/tests/test_workers_plan2_integration.py`

### Context

Pattern mirrors `similarity_worker.py`. Cycle lifecycle per brand:

1. `MonitoringCycleRepository.get_or_create_today(brand_id, org_id)` → cycle object
2. If `cycle.health_status == "completed"` → skip (idempotent)
3. `MonitoringCycleService.begin_stage(cycle.id, stage="health")` → marks running
4. For each `brand_domain`: call `run_health_check_domain`
5. `MonitoringCycleService.finish_stage(cycle.id, stage="health", success=True)`
6. `db.commit()`

`begin_stage` takes `cycle.id` (UUID), not brand_id. Returns `None`. The cycle object comes from `get_or_create_today`.

- [ ] **Step 2.1: Write the failing test**

```python
# append to backend/tests/test_workers_plan2_integration.py

def test_health_worker_run_cycle_updates_cycle_status(db_session):
    """health_worker run_health_cycle updates monitoring_cycle.health_status."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.monitored_brand_domain import MonitoredBrandDomain
    from app.worker.health_worker import run_health_cycle
    from unittest.mock import patch
    from uuid import uuid4

    brand = MonitoredBrand(
        id=uuid4(), organization_id=uuid4(),
        brand_name="HealthCo", brand_label="healthco",
        is_active=True,
    )
    db_session.add(brand)
    domain = MonitoredBrandDomain(
        id=uuid4(), brand_id=brand.id,
        organization_id=brand.organization_id,
        domain_name="healthco.com", is_active=True,
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
```

- [ ] **Step 2.2: Run test to verify it fails**

```
docker exec -it <backend_container> pytest backend/tests/test_workers_plan2_integration.py::test_health_worker_run_cycle_updates_cycle_status -v
```
Expected: ImportError — `health_worker` not found

- [ ] **Step 2.3: Implement `health_worker.py`**

```python
# backend/app/worker/health_worker.py
"""Health Worker — daily health check of official brand domains.

Scheduled at 06:00 UTC. Runs 10 monitoring tools per domain,
creates monitoring_event records, recalculates brand_domain_health.
"""
from __future__ import annotations

import logging
import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.repositories.monitored_brand_repository import MonitoredBrandRepository
from app.repositories.monitoring_cycle_repository import MonitoringCycleRepository
from app.services.monitoring_cycle_service import MonitoringCycleService
from app.services.use_cases.run_health_check_domain import run_health_check_domain

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("health_worker")

HEALTH_CRON = getattr(settings, "HEALTH_CHECK_CRON", "0 6 * * *")

_consecutive_cycle_failures = 0
_last_cycle_completed_at: datetime | None = None


def run_health_cycle(db: Session | None = None) -> None:
    """Run health checks for all active brands. Accepts optional db for testing."""
    global _consecutive_cycle_failures, _last_cycle_completed_at

    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    try:
        brand_repo = MonitoredBrandRepository(db)
        brands = brand_repo.list_active()

        if not brands:
            logger.info("No active brands for health check.")
            return

        logger.info("Starting health check cycle for %d brands", len(brands))

        for brand in brands:
            try:
                # Step 1: Get or create today's cycle for this brand
                cycle_repo = MonitoringCycleRepository(db)
                cycle, created = cycle_repo.get_or_create_today(
                    brand_id=brand.id,
                    organization_id=brand.organization_id,
                )
                if created:
                    db.commit()

                # Step 2: Idempotency — skip if health stage already completed today
                if cycle.health_status == "completed":
                    logger.info(
                        "Health check already completed for brand=%s today",
                        brand.brand_name,
                    )
                    continue

                # Step 3: Mark stage as running
                svc = MonitoringCycleService(db, cycle_repo=cycle_repo)
                svc.begin_stage(cycle.id, stage="health")
                db.commit()

                domains = [
                    d for d in (brand.domains or [])
                    if getattr(d, "is_active", True)
                ]
                domains_ok = 0
                domains_failed = 0

                for domain in domains:
                    try:
                        summary = run_health_check_domain(
                            db,
                            domain,
                            brand_id=brand.id,
                            organization_id=brand.organization_id,
                            cycle_id=cycle.id,
                        )
                        domains_ok += 1
                        logger.info(
                            "health_check brand=%s domain=%s status=%s tools_failed=%d",
                            brand.brand_name, domain.domain_name,
                            summary["overall_status"], summary["tools_failed"],
                        )
                    except Exception:
                        domains_failed += 1
                        logger.exception(
                            "health_check FAILED brand=%s domain=%s",
                            brand.brand_name, domain.domain_name,
                        )

                # Step 4: Mark stage complete (partial domain failures do not fail the cycle)
                svc.finish_stage(cycle.id, stage="health", success=True)
                db.commit()
                logger.info(
                    "Health cycle complete: brand=%s domains_ok=%d domains_failed=%d",
                    brand.brand_name, domains_ok, domains_failed,
                )

            except Exception:
                db.rollback()
                logger.exception("Health cycle failed for brand=%s", brand.brand_name)

        _last_cycle_completed_at = datetime.now(timezone.utc)
        _consecutive_cycle_failures = 0

    except Exception:
        _consecutive_cycle_failures += 1
        logger.exception(
            "Health worker cycle failed (consecutive=%d)", _consecutive_cycle_failures
        )
    finally:
        if owns_session:
            db.close()


def emit_heartbeat() -> None:
    last_ok = _last_cycle_completed_at.isoformat() if _last_cycle_completed_at else "never"
    logger.info(
        "[HEARTBEAT] health_worker alive last_cycle=%s consecutive_failures=%d",
        last_ok, _consecutive_cycle_failures,
    )


def main() -> None:
    logger.info("Health Worker starting. Cron: %s", HEALTH_CRON)
    run_health_cycle()

    scheduler = BlockingScheduler()
    cron_parts = HEALTH_CRON.split()
    scheduler.add_job(
        run_health_cycle,
        CronTrigger(
            minute=cron_parts[0], hour=cron_parts[1],
            day=cron_parts[2], month=cron_parts[3], day_of_week=cron_parts[4],
        ),
        id="health_check",
        replace_existing=True,
    )
    scheduler.add_job(
        emit_heartbeat,
        IntervalTrigger(minutes=5),
        id="health_heartbeat",
        replace_existing=True,
    )

    def _shutdown(signum, frame):
        logger.info("Shutting down health_worker...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    scheduler.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2.4: Run test to verify it passes**

```
docker exec -it <backend_container> pytest backend/tests/test_workers_plan2_integration.py::test_health_worker_run_cycle_updates_cycle_status -v
```
Expected: PASS

- [ ] **Step 2.5: Commit**

```bash
git add backend/app/worker/health_worker.py \
        backend/tests/test_workers_plan2_integration.py
git commit -m "feat(workers): add health_worker with run_health_check_domain integration"
```

---

## Task 3: `compute_enrichment_budget_rank` in SimilarityRepository

**Files:**
- Modify: `backend/app/repositories/similarity_repository.py`
- Test: append to `backend/tests/test_workers_plan2_integration.py`

### Context

After a scan, matches need to be ranked for enrichment priority. Budget = top 50 per brand. Priority tier order (lower number = higher priority, CASE evaluated top-down):
- Tier 0: `immediate_attention` (always enriched first)
- Tier 1: new matches today (`first_detected_at::date = CURRENT_DATE`)
- Tier 2: `defensive_gap` by `actionability_score DESC`
- Tier 3: `watchlist` with `score_final > 0.55`
- Tier 4: stale enrichment (`last_enriched_at` IS NULL or >7 days ago)

The method resets all ranks for the brand, then sets top-50 with `ROW_NUMBER()`.

- [ ] **Step 3.1: Write the failing test**

```python
# append to backend/tests/test_workers_plan2_integration.py

def test_compute_enrichment_budget_rank_top_50(db_session):
    """compute_enrichment_budget_rank assigns rank 1..N to top-50 matches."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.similarity_match import SimilarityMatch
    from app.repositories.similarity_repository import SimilarityRepository
    from uuid import uuid4

    brand = MonitoredBrand(
        id=uuid4(), organization_id=uuid4(),
        brand_name="RankCo", brand_label="rankco",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    for i, bucket in enumerate(["immediate_attention", "defensive_gap", "watchlist",
                                 "defensive_gap", "watchlist"]):
        m = SimilarityMatch(
            id=uuid4(), brand_id=brand.id, organization_id=brand.organization_id,
            domain_name=f"rank{i}-brand.com", tld="com", label=f"rank{i}",
            score_final=0.7 - i * 0.05,
            attention_bucket=bucket,
            actionability_score=0.7 - i * 0.05,
        )
        db_session.add(m)
    db_session.commit()

    repo = SimilarityRepository(db_session)
    count = repo.compute_enrichment_budget_rank(brand.id, limit=50)

    assert count == 5

    from app.models.similarity_match import SimilarityMatch
    top = db_session.query(SimilarityMatch).filter(
        SimilarityMatch.brand_id == brand.id,
        SimilarityMatch.enrichment_budget_rank == 1,
    ).one()
    assert top.attention_bucket == "immediate_attention"
```

- [ ] **Step 3.2: Run test to verify it fails**

```
docker exec -it <backend_container> pytest backend/tests/test_workers_plan2_integration.py::test_compute_enrichment_budget_rank_top_50 -v
```
Expected: FAIL — `compute_enrichment_budget_rank` not found

- [ ] **Step 3.3: Add method to SimilarityRepository**

Open `backend/app/repositories/similarity_repository.py` and add this method to the `SimilarityRepository` class:

```python
def compute_enrichment_budget_rank(
    self,
    brand_id: "UUID",
    *,
    limit: int = 50,
) -> int:
    """Rank top-N matches for enrichment priority and store as enrichment_budget_rank.

    Priority tiers (lower = higher priority, CASE stops at first match):
      0 — immediate_attention
      1 — new today (first_detected_at = today)
      2 — defensive_gap
      3 — watchlist with score_final > 0.55
      4 — stale enrichment (> 7 days since last_enriched_at or never enriched)

    Resets existing ranks for the brand first.
    Returns the number of matches ranked.
    """
    from sqlalchemy import text

    # Step 1: Reset all ranks for this brand
    self.db.execute(
        text(
            "UPDATE similarity_match"
            " SET enrichment_budget_rank = NULL, updated_at = NOW()"
            " WHERE brand_id = :brand_id"
        ),
        {"brand_id": brand_id},
    )

    # Step 2: Rank top-N by priority tier
    self.db.execute(
        text("""
        WITH ranked AS (
            SELECT id,
                   ROW_NUMBER() OVER (
                       ORDER BY
                         CASE
                           WHEN attention_bucket = 'immediate_attention' THEN 0
                           WHEN first_detected_at::date = CURRENT_DATE THEN 1
                           WHEN attention_bucket = 'defensive_gap' THEN 2
                           WHEN attention_bucket = 'watchlist'
                                AND score_final > 0.55 THEN 3
                           WHEN last_enriched_at IS NULL
                                OR last_enriched_at < NOW() - INTERVAL '7 days' THEN 4
                           ELSE 5
                         END ASC,
                         actionability_score DESC NULLS LAST,
                         score_final DESC
                   ) AS r
            FROM similarity_match
            WHERE brand_id = :brand_id
              AND (auto_disposition IS NULL OR auto_disposition = '')
              AND disposition NOT IN ('dismissed')
        )
        UPDATE similarity_match sm
        SET enrichment_budget_rank = ranked.r, updated_at = NOW()
        FROM ranked
        WHERE sm.id = ranked.id AND ranked.r <= :limit
        """),
        {"brand_id": brand_id, "limit": limit},
    )

    result = self.db.execute(
        text(
            "SELECT COUNT(*) FROM similarity_match"
            " WHERE brand_id = :brand_id AND enrichment_budget_rank IS NOT NULL"
        ),
        {"brand_id": brand_id},
    ).scalar()
    return int(result or 0)
```

- [ ] **Step 3.4: Run test to verify it passes**

```
docker exec -it <backend_container> pytest backend/tests/test_workers_plan2_integration.py::test_compute_enrichment_budget_rank_top_50 -v
```
Expected: PASS

- [ ] **Step 3.5: Commit**

```bash
git add backend/app/repositories/similarity_repository.py \
        backend/tests/test_workers_plan2_integration.py
git commit -m "feat(workers): add compute_enrichment_budget_rank to SimilarityRepository"
```

---

## Task 4: `scan_worker.py` — refactored scan with cycle tracking

**Files:**
- Create: `backend/app/worker/scan_worker.py`
- Modify: `backend/app/services/use_cases/run_similarity_scan.py` — remove inline enrichment
- Test: append to `backend/tests/test_workers_plan2_integration.py`

### Context

`similarity_worker.py` currently does inline enrichment via `enrich_similarity_match` (budget=8 per scan). The new `scan_worker.py`:
1. Wraps existing `run_similarity_scan_all` (unchanged behavior for finding matches)
2. Calls `MonitoringCycleRepository.get_or_create_today` then `begin_stage/finish_stage`
3. After scan: calls `SimilarityRepository.compute_enrichment_budget_rank`

The existing `similarity_worker.py` is **kept** for manual queued job processing (`run_queued_jobs_cycle`), but `scan_worker.py` absorbs that functionality too so the old service entry can be replaced.

**Remove inline enrichment from `run_similarity_scan.py`:** Replace the loop calling `should_auto_enrich_match`/`enrich_similarity_match` with simple status-setting.

- [ ] **Step 4.1: Write the failing test**

```python
# append to backend/tests/test_workers_plan2_integration.py

def test_scan_worker_creates_cycle_and_ranks(db_session):
    """scan_worker run_scan_cycle creates monitoring_cycle and calls rank after scan."""
    from app.models.monitored_brand import MonitoredBrand
    from app.worker.scan_worker import run_scan_cycle
    from unittest.mock import patch, MagicMock
    from uuid import uuid4
    from datetime import date

    brand = MonitoredBrand(
        id=uuid4(), organization_id=uuid4(),
        brand_name="ScanCo", brand_label="scanco",
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
    mock_repo.compute_enrichment_budget_rank.assert_called_once_with(brand.id, limit=50)
```

- [ ] **Step 4.2: Run test to verify it fails**

```
docker exec -it <backend_container> pytest backend/tests/test_workers_plan2_integration.py::test_scan_worker_creates_cycle_and_ranks -v
```
Expected: ImportError — `scan_worker` not found

- [ ] **Step 4.3: Remove inline enrichment from `run_similarity_scan.py`**

In `backend/app/services/use_cases/run_similarity_scan.py`, find the loop that calls `should_auto_enrich_match` / `enrich_similarity_match` (around lines 213–243) and replace it with:

```python
# Enrichment deferred to enrichment_worker — set status to pending
for match in matches_to_upsert:
    match.setdefault("enrichment_status", "pending")
    match.setdefault("enrichment_summary", None)
    match.setdefault("last_enriched_at", None)
```

Also remove the `enrichment_budget` variable and, if they are now unused, remove the imports of `enrich_similarity_match`, `should_auto_enrich_match`, and `AUTO_ENRICH_LIMIT_PER_SCAN` from the file header.

- [ ] **Step 4.4: Implement `scan_worker.py`**

```python
# backend/app/worker/scan_worker.py
"""Scan Worker — daily similarity scan with monitoring cycle integration.

Scheduled at 09:00 UTC. Wraps run_similarity_scan_all, registers progress
in monitoring_cycle, and computes enrichment_budget_rank after scanning.
Also drains manual queued scan jobs every 15 seconds.
"""
from __future__ import annotations

import logging
import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.repositories.monitored_brand_repository import MonitoredBrandRepository
from app.repositories.monitoring_cycle_repository import MonitoringCycleRepository
from app.repositories.similarity_repository import SimilarityRepository
from app.services.monitoring_cycle_service import MonitoringCycleService
from app.services.use_cases.run_similarity_scan import run_similarity_scan_all, run_similarity_scan_job

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("scan_worker")

SCAN_CRON = settings.SIMILARITY_SCAN_CRON

_consecutive_cycle_failures = 0
_last_cycle_completed_at: datetime | None = None


def run_scan_cycle(db: Session | None = None) -> None:
    """Scan all active brands and compute enrichment budget ranks."""
    global _consecutive_cycle_failures, _last_cycle_completed_at

    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    try:
        brand_repo = MonitoredBrandRepository(db)
        brands = brand_repo.list_active()

        if not brands:
            logger.info("No active brands to scan.")
            return

        logger.info("Starting scan cycle for %d brands", len(brands))

        for brand in brands:
            try:
                # Step 1: Get or create today's cycle
                cycle_repo = MonitoringCycleRepository(db)
                cycle, created = cycle_repo.get_or_create_today(
                    brand_id=brand.id,
                    organization_id=brand.organization_id,
                )
                if created:
                    db.commit()

                # Step 2: Idempotency
                if cycle.scan_status == "completed":
                    logger.info(
                        "Scan already completed for brand=%s today", brand.brand_name
                    )
                    continue

                # Step 3: Mark scan stage running
                svc = MonitoringCycleService(db, cycle_repo=cycle_repo)
                svc.begin_stage(cycle.id, stage="scan")
                db.commit()

                logger.info("Scanning brand=%s", brand.brand_name)
                results = run_similarity_scan_all(db, brand)

                total_matched = sum(r.get("matched", 0) for r in results.values())
                total_candidates = sum(r.get("candidates", 0) for r in results.values())

                # Step 4: Rank top-50 for enrichment
                sim_repo = SimilarityRepository(db)
                ranked = sim_repo.compute_enrichment_budget_rank(brand.id, limit=50)

                # Step 5: Finish stage
                svc.finish_stage(cycle.id, stage="scan", success=True)
                db.commit()

                logger.info(
                    "Scan complete: brand=%s candidates=%d matched=%d ranked=%d",
                    brand.brand_name, total_candidates, total_matched, ranked,
                )

            except Exception:
                db.rollback()
                logger.exception("Scan failed for brand=%s", brand.brand_name)

        _last_cycle_completed_at = datetime.now(timezone.utc)
        _consecutive_cycle_failures = 0

    except Exception:
        _consecutive_cycle_failures += 1
        logger.exception(
            "Scan cycle failed (consecutive=%d)", _consecutive_cycle_failures
        )
    finally:
        if owns_session:
            db.close()


def run_queued_jobs_cycle() -> None:
    """Drain queued manual scan jobs created by the API."""
    db = SessionLocal()
    try:
        repo = SimilarityRepository(db)
        processed = 0
        while processed < 5:
            job = repo.claim_next_queued_scan_job()
            if not job:
                break
            db.commit()
            logger.info("Processing queued job=%s brand=%s", job.id, job.brand_id)
            try:
                run_similarity_scan_job(db, job.id)
            except Exception:
                logger.exception("Queued job failed: %s", job.id)
            processed += 1
    finally:
        db.close()


def emit_heartbeat() -> None:
    last_ok = _last_cycle_completed_at.isoformat() if _last_cycle_completed_at else "never"
    logger.info(
        "[HEARTBEAT] scan_worker alive last_cycle=%s consecutive_failures=%d",
        last_ok, _consecutive_cycle_failures,
    )


def main() -> None:
    logger.info("Scan Worker starting. Cron: %s", SCAN_CRON)
    run_scan_cycle()

    scheduler = BlockingScheduler()
    cron_parts = SCAN_CRON.split()
    scheduler.add_job(
        run_scan_cycle,
        CronTrigger(
            minute=cron_parts[0], hour=cron_parts[1],
            day=cron_parts[2], month=cron_parts[3], day_of_week=cron_parts[4],
        ),
        id="similarity_scan",
        replace_existing=True,
    )
    scheduler.add_job(
        run_queued_jobs_cycle,
        IntervalTrigger(seconds=15),
        id="queued_jobs",
        replace_existing=True,
    )
    scheduler.add_job(
        emit_heartbeat,
        IntervalTrigger(minutes=5),
        id="scan_heartbeat",
        replace_existing=True,
    )

    def _shutdown(signum, frame):
        logger.info("Shutting down scan_worker...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    scheduler.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4.5: Run test to verify it passes**

```
docker exec -it <backend_container> pytest backend/tests/test_workers_plan2_integration.py::test_scan_worker_creates_cycle_and_ranks -v
```
Expected: PASS

- [ ] **Step 4.6: Run the full existing test suite**

```
docker exec -it <backend_container> pytest backend/tests/ -v --tb=short 2>&1 | tail -30
```
Expected: All previously passing tests still pass.

- [ ] **Step 4.7: Commit**

```bash
git add backend/app/worker/scan_worker.py \
        backend/app/services/use_cases/run_similarity_scan.py \
        backend/tests/test_workers_plan2_integration.py
git commit -m "feat(workers): add scan_worker with cycle tracking + enrichment budget ranking; remove inline enrichment from run_similarity_scan"
```

---

## Task 5: `run_enrichment_cycle_match` use case

**Files:**
- Create: `backend/app/services/use_cases/run_enrichment_cycle_match.py`
- Test: append to `backend/tests/test_workers_plan2_integration.py`

### Context

Core enrichment logic for one match:
1. Runs wave 1 + wave 2 tools (12 total); conditional clone detection for `immediate_attention`
2. Creates `monitoring_event` per tool result
3. Calls `StateAggregator.recalculate_match_snapshot()` — which commits internally
4. Reads updated snapshot via `MatchStateSnapshotRepository.get_by_match(match_id)` (NOT `get_by_match_id`)
5. Applies auto-dismiss rules 1 and 3 from spec §6.1 (rule 2 is score-based)
6. If auto-dismiss: creates `monitoring_event(event_type="auto_disposition")`

**Auto-dismiss rules:**
- Rule 1 — Dead domain: no DNS records + no MX + WHOIS age > 1 year + no critical/high signal
- Rule 2 — Low score: `derived_score < 0.35` + no critical/high signal + not `exact_label_match`
- Rule 3 — Parked/for sale: `suspicious_page` returned parked + no MX + Safe Browsing/PhishTank/URLhaus clean

- [ ] **Step 5.1: Write the failing test**

```python
# append to backend/tests/test_workers_plan2_integration.py

def test_run_enrichment_cycle_match_creates_events_and_snapshot(db_session):
    """Enrichment creates tool events and upserts match_state_snapshot."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.similarity_match import SimilarityMatch
    from app.models.monitoring_cycle import MonitoringCycle
    from app.services.use_cases.run_enrichment_cycle_match import run_enrichment_cycle_match
    from unittest.mock import patch
    from uuid import uuid4
    from datetime import date

    brand = MonitoredBrand(
        id=uuid4(), organization_id=uuid4(),
        brand_name="EnrichCo", brand_label="enrichco",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    match = SimilarityMatch(
        id=uuid4(), brand_id=brand.id, organization_id=brand.organization_id,
        domain_name="enrichco-fake.com", tld="com", label="enrichco-fake",
        score_final=0.65, attention_bucket="defensive_gap", actionability_score=0.65,
        matched_rule="typo_candidate",
    )
    db_session.add(match)

    cycle = MonitoringCycle(
        id=uuid4(), brand_id=brand.id,
        organization_id=brand.organization_id,
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
```

- [ ] **Step 5.2: Run test to verify it fails**

```
docker exec -it <backend_container> pytest backend/tests/test_workers_plan2_integration.py::test_run_enrichment_cycle_match_creates_events_and_snapshot -v
```
Expected: ImportError

- [ ] **Step 5.3: Implement `run_enrichment_cycle_match.py`**

```python
# backend/app/services/use_cases/run_enrichment_cycle_match.py
"""Enrichment use case for one similarity match.

Creates monitoring_event per tool, recalculates match_state_snapshot,
applies auto-dismiss rules (spec §6.1).
"""
from __future__ import annotations

import importlib
import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.monitored_brand import MonitoredBrand
from app.models.similarity_match import SimilarityMatch
from app.repositories.monitoring_event_repository import MonitoringEventRepository
from app.services.state_aggregator import StateAggregator

logger = logging.getLogger(__name__)

# Wave 1 — always run
_WAVE1_TOOLS = [
    ("dns_lookup",      "app.services.use_cases.tools.dns_lookup.DnsLookupService"),
    ("whois",           "app.services.use_cases.tools.whois_lookup.WhoisLookupService"),
    ("ssl_check",       "app.services.use_cases.tools.ssl_check.SslCheckService"),
    ("http_headers",    "app.services.use_cases.tools.http_headers.HttpHeadersService"),
    ("screenshot",      "app.services.use_cases.tools.screenshot_capture.ScreenshotCaptureService"),
    ("suspicious_page", "app.services.use_cases.tools.suspicious_page.SuspiciousPageService"),
]

# Wave 2 — always run
_WAVE2_TOOLS = [
    ("email_security",  "app.services.use_cases.tools.email_security.EmailSecurityService"),
    ("ip_geolocation",  "app.services.use_cases.tools.ip_geolocation.IpGeolocationService"),
    ("blacklist_check", "app.services.use_cases.tools.blacklist_check.BlacklistCheckService"),
    ("safe_browsing",   "app.services.use_cases.tools.safe_browsing_check.SafeBrowsingCheckService"),
    ("urlhaus",         "app.services.use_cases.tools.urlhaus_check.UrlhausCheckService"),
    ("phishtank",       "app.services.use_cases.tools.phishtank_check.PhishTankCheckService"),
]

# Conditional — only for immediate_attention matches with a primary domain
_CLONE_TOOL = ("website_clone", "app.services.use_cases.tools.website_clone.WebsiteCloneService")

_HIGH_RISK_SEVERITIES = {"critical", "high"}


def _run_tool(tool_class_path: str, domain: str) -> dict:
    module_path, class_name = tool_class_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    service = getattr(module, class_name)()
    result = service.run(domain)
    if hasattr(result, "model_dump"):
        return result.model_dump()
    if hasattr(result, "dict"):
        return result.dict()
    return result if isinstance(result, dict) else {}


def _check_auto_dismiss(
    *,
    derived_score: float,
    active_signals: list[dict],
    matched_rule: str | None,
    tool_results: dict[str, dict],
) -> tuple[bool, str | None]:
    """
    Check all 3 auto-dismiss rules (spec §6.1).
    Returns (should_dismiss, rule_name).
    """
    signal_severities = {s.get("severity", "low") for s in active_signals}
    has_critical_or_high = bool(signal_severities & _HIGH_RISK_SEVERITIES)

    # Rule 2 — Low score post-enrichment
    is_exact = (matched_rule or "") == "exact_label_match"
    if derived_score < 0.35 and not has_critical_or_high and not is_exact:
        return True, "low_score_post_enrichment"

    # Rule 1 — Dead domain
    dns = tool_results.get("dns_lookup", {})
    email = tool_results.get("email_security", {})
    whois = tool_results.get("whois", {})
    dns_has_records = bool(dns.get("records"))
    has_mx = bool(
        email.get("mx_records")
        or dns.get("mx_records")
        or (dns.get("records") and any(r.get("type") == "MX" for r in dns.get("records", [])))
    )
    domain_age_days = whois.get("domain_age_days") or whois.get("age_days")
    if (
        not dns_has_records
        and not has_mx
        and domain_age_days and int(domain_age_days) > 365
        and not has_critical_or_high
    ):
        return True, "dead_domain"

    # Rule 3 — Parked/for sale
    page = tool_results.get("suspicious_page", {})
    sb = tool_results.get("safe_browsing", {})
    uh = tool_results.get("urlhaus", {})
    pt = tool_results.get("phishtank", {})
    parked = page.get("page_type") in ("parked", "for_sale")
    sb_clean = not bool(sb.get("threats"))
    uh_clean = not bool(uh.get("listed"))
    pt_clean = not bool(pt.get("in_database"))
    if parked and not has_mx and sb_clean and uh_clean and pt_clean:
        return True, "parked_for_sale"

    return False, None


def run_enrichment_cycle_match(
    db: Session,
    match: SimilarityMatch,
    *,
    brand: MonitoredBrand,
    cycle_id: UUID,
) -> dict:
    """Run enrichment tools for one match, create events, recalculate snapshot.

    Returns:
        {"tools_run": int, "tools_failed": int, "auto_dismissed": bool,
         "dismiss_rule": str | None, "derived_bucket": str}
    """
    domain = match.domain_name
    if not domain.endswith(f".{match.tld}"):
        domain = f"{domain}.{match.tld}"

    event_repo = MonitoringEventRepository(db)
    tool_results: dict[str, dict] = {}
    tools_run = 0
    tools_failed = 0

    all_tools = list(_WAVE1_TOOLS) + list(_WAVE2_TOOLS)

    # Conditional clone detection
    if (
        getattr(match, "attention_bucket", "") == "immediate_attention"
        and brand.domains
    ):
        all_tools.append(_CLONE_TOOL)

    for tool_name, tool_class_path in all_tools:
        if event_repo.event_exists_for_cycle(
            cycle_id=cycle_id,
            tool_name=tool_name,
            match_id=match.id,
        ):
            logger.debug("Skipping %s for match=%s (already in cycle)", tool_name, match.id)
            tools_run += 1
            continue

        try:
            result_data = _run_tool(tool_class_path, domain)
            tool_results[tool_name] = result_data
            event_repo.create(
                organization_id=match.organization_id,
                brand_id=match.brand_id,
                match_id=match.id,
                cycle_id=cycle_id,
                event_type="tool_execution",
                event_source="enrichment",
                tool_name=tool_name,
                result_data=result_data,
            )
            tools_run += 1
        except Exception:
            tools_failed += 1
            logger.exception("enrichment tool=%s match=%s FAILED", tool_name, match.id)
            event_repo.create(
                organization_id=match.organization_id,
                brand_id=match.brand_id,
                match_id=match.id,
                cycle_id=cycle_id,
                event_type="tool_execution",
                event_source="enrichment",
                tool_name=tool_name,
                result_data={"error": "tool_failed"},
            )

    db.flush()

    # Recalculate snapshot from all events
    domain_age_days = None
    whois_result = tool_results.get("whois", {})
    if whois_result:
        domain_age_days = whois_result.get("domain_age_days") or whois_result.get("age_days")

    aggregator = StateAggregator(db)
    aggregator.recalculate_match_snapshot(
        match_id=match.id,
        brand_id=match.brand_id,
        organization_id=match.organization_id,
        base_lexical_score=float(match.score_final or 0.5),
        domain_age_days=int(domain_age_days) if domain_age_days else None,
    )
    # StateAggregator.recalculate_match_snapshot commits internally

    # Read back snapshot — method is get_by_match, not get_by_match_id
    from app.repositories.match_state_snapshot_repository import MatchStateSnapshotRepository
    snapshot = MatchStateSnapshotRepository(db).get_by_match(match.id)

    auto_dismissed = False
    dismiss_rule = None

    if snapshot:
        auto_dismissed, dismiss_rule = _check_auto_dismiss(
            derived_score=snapshot.derived_score,
            active_signals=snapshot.active_signals or [],
            matched_rule=getattr(match, "matched_rule", None),
            tool_results=tool_results,
        )

        if auto_dismissed:
            from sqlalchemy import text
            db.execute(
                text(
                    "UPDATE similarity_match"
                    " SET auto_disposition = 'auto_dismissed',"
                    "     auto_disposition_reason = :reason,"
                    "     updated_at = NOW()"
                    " WHERE id = :match_id"
                ),
                {"reason": dismiss_rule, "match_id": match.id},
            )
            event_repo.create(
                organization_id=match.organization_id,
                brand_id=match.brand_id,
                match_id=match.id,
                cycle_id=cycle_id,
                event_type="auto_disposition",
                event_source="enrichment",
                tool_name=None,
                result_data={"rule": dismiss_rule, "auto_dismissed": True},
            )
            db.commit()
            logger.info(
                "Auto-dismissed match=%s rule=%s derived_score=%.3f",
                match.id, dismiss_rule, snapshot.derived_score,
            )

    return {
        "tools_run": tools_run,
        "tools_failed": tools_failed,
        "auto_dismissed": auto_dismissed,
        "dismiss_rule": dismiss_rule,
        "derived_bucket": snapshot.derived_bucket if snapshot else "watchlist",
    }
```

- [ ] **Step 5.4: Run test to verify it passes**

```
docker exec -it <backend_container> pytest backend/tests/test_workers_plan2_integration.py::test_run_enrichment_cycle_match_creates_events_and_snapshot -v
```
Expected: PASS

- [ ] **Step 5.5: Commit**

```bash
git add backend/app/services/use_cases/run_enrichment_cycle_match.py \
        backend/tests/test_workers_plan2_integration.py
git commit -m "feat(workers): add run_enrichment_cycle_match use case with auto-dismiss (rules 1-3)"
```

---

## Task 6: `enrichment_worker.py`

**Files:**
- Create: `backend/app/worker/enrichment_worker.py`
- Test: append to `backend/tests/test_workers_plan2_integration.py`

### Context

Runs at 12:00 UTC. Per brand: fetch matches with `enrichment_budget_rank IS NOT NULL` ordered by rank, call `run_enrichment_cycle_match`, update cycle counters via service methods (not repository directly).

- [ ] **Step 6.1: Write the failing test**

```python
# append to backend/tests/test_workers_plan2_integration.py

def test_enrichment_worker_processes_ranked_matches(db_session):
    """enrichment_worker processes matches with enrichment_budget_rank set."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.similarity_match import SimilarityMatch
    from app.worker.enrichment_worker import run_enrichment_cycle
    from unittest.mock import patch, MagicMock
    from uuid import uuid4
    from datetime import date

    brand = MonitoredBrand(
        id=uuid4(), organization_id=uuid4(),
        brand_name="EnrichWorkerCo", brand_label="enrichworkerco",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    match = SimilarityMatch(
        id=uuid4(), brand_id=brand.id, organization_id=brand.organization_id,
        domain_name="enrichworkerco-fake.com", tld="com", label="fake",
        score_final=0.7, attention_bucket="defensive_gap",
        actionability_score=0.7, enrichment_budget_rank=1,
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
```

- [ ] **Step 6.2: Run test to verify it fails**

```
docker exec -it <backend_container> pytest backend/tests/test_workers_plan2_integration.py::test_enrichment_worker_processes_ranked_matches -v
```
Expected: ImportError

- [ ] **Step 6.3: Implement `enrichment_worker.py`**

```python
# backend/app/worker/enrichment_worker.py
"""Enrichment Worker — daily enrichment of top-50 ranked matches per brand.

Scheduled at 12:00 UTC. Processes matches with enrichment_budget_rank set,
runs 12 tools per match, recalculates snapshots, applies auto-dismiss.
"""
from __future__ import annotations

import logging
import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.repositories.monitored_brand_repository import MonitoredBrandRepository
from app.repositories.monitoring_cycle_repository import MonitoringCycleRepository
from app.services.monitoring_cycle_service import MonitoringCycleService
from app.services.use_cases.run_enrichment_cycle_match import run_enrichment_cycle_match

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("enrichment_worker")

ENRICHMENT_CRON = getattr(settings, "ENRICHMENT_CRON", "0 12 * * *")

_consecutive_cycle_failures = 0
_last_cycle_completed_at: datetime | None = None


def _fetch_ranked_matches(db: Session, brand_id, *, limit: int = 50):
    """Fetch matches with enrichment_budget_rank set, ordered by rank."""
    from sqlalchemy import text
    from app.models.similarity_match import SimilarityMatch

    rows = db.execute(
        text(
            "SELECT id FROM similarity_match"
            " WHERE brand_id = :brand_id"
            "   AND enrichment_budget_rank IS NOT NULL"
            " ORDER BY enrichment_budget_rank ASC"
            " LIMIT :limit"
        ),
        {"brand_id": brand_id, "limit": limit},
    ).fetchall()
    match_ids = [r[0] for r in rows]
    if not match_ids:
        return []

    return (
        db.query(SimilarityMatch)
        .filter(SimilarityMatch.id.in_(match_ids))
        .order_by(SimilarityMatch.enrichment_budget_rank.asc())
        .all()
    )


def run_enrichment_cycle(db: Session | None = None) -> None:
    """Run enrichment cycle for all active brands."""
    global _consecutive_cycle_failures, _last_cycle_completed_at

    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    try:
        brand_repo = MonitoredBrandRepository(db)
        brands = brand_repo.list_active()

        if not brands:
            logger.info("No active brands for enrichment.")
            return

        logger.info("Starting enrichment cycle for %d brands", len(brands))

        for brand in brands:
            try:
                db.refresh(brand)  # ensure relationships (domains) are loaded

                cycle_repo = MonitoringCycleRepository(db)
                cycle, created = cycle_repo.get_or_create_today(
                    brand_id=brand.id,
                    organization_id=brand.organization_id,
                )
                if created:
                    db.commit()

                if cycle.enrichment_status == "completed":
                    logger.info(
                        "Enrichment already completed for brand=%s today", brand.brand_name
                    )
                    continue

                svc = MonitoringCycleService(db, cycle_repo=cycle_repo)
                svc.begin_stage(cycle.id, stage="enrichment")
                db.commit()

                matches = _fetch_ranked_matches(db, brand.id, limit=50)
                logger.info("Enriching %d matches for brand=%s", len(matches), brand.brand_name)

                for match in matches:
                    try:
                        result = run_enrichment_cycle_match(
                            db,
                            match,
                            brand=brand,
                            cycle_id=cycle.id,
                        )
                        # Use service methods to update counters (not repo directly)
                        if result["auto_dismissed"]:
                            svc.record_dismissed(cycle.id)
                            db.commit()
                        elif result["derived_bucket"] == "immediate_attention":
                            svc.record_escalated(cycle.id)
                            db.commit()
                        logger.debug(
                            "enriched match=%s bucket=%s dismissed=%s",
                            match.id, result["derived_bucket"], result["auto_dismissed"],
                        )
                    except Exception:
                        logger.exception("Enrichment failed for match=%s", match.id)

                svc.finish_stage(cycle.id, stage="enrichment", success=True)
                db.commit()

                logger.info(
                    "Enrichment complete for brand=%s (%d matches)",
                    brand.brand_name, len(matches),
                )

            except Exception:
                db.rollback()
                logger.exception("Enrichment cycle failed for brand=%s", brand.brand_name)

        _last_cycle_completed_at = datetime.now(timezone.utc)
        _consecutive_cycle_failures = 0

    except Exception:
        _consecutive_cycle_failures += 1
        logger.exception(
            "Enrichment worker cycle failed (consecutive=%d)", _consecutive_cycle_failures
        )
    finally:
        if owns_session:
            db.close()


def emit_heartbeat() -> None:
    last_ok = _last_cycle_completed_at.isoformat() if _last_cycle_completed_at else "never"
    logger.info(
        "[HEARTBEAT] enrichment_worker alive last_cycle=%s consecutive_failures=%d",
        last_ok, _consecutive_cycle_failures,
    )


def main() -> None:
    logger.info("Enrichment Worker starting. Cron: %s", ENRICHMENT_CRON)
    run_enrichment_cycle()

    scheduler = BlockingScheduler()
    cron_parts = ENRICHMENT_CRON.split()
    scheduler.add_job(
        run_enrichment_cycle,
        CronTrigger(
            minute=cron_parts[0], hour=cron_parts[1],
            day=cron_parts[2], month=cron_parts[3], day_of_week=cron_parts[4],
        ),
        id="enrichment",
        replace_existing=True,
    )
    scheduler.add_job(
        emit_heartbeat,
        IntervalTrigger(minutes=5),
        id="enrichment_heartbeat",
        replace_existing=True,
    )

    def _shutdown(signum, frame):
        logger.info("Shutting down enrichment_worker...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    scheduler.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 6.4: Run test to verify it passes**

```
docker exec -it <backend_container> pytest backend/tests/test_workers_plan2_integration.py::test_enrichment_worker_processes_ranked_matches -v
```
Expected: PASS

- [ ] **Step 6.5: Commit**

```bash
git add backend/app/worker/enrichment_worker.py \
        backend/tests/test_workers_plan2_integration.py
git commit -m "feat(workers): add enrichment_worker with budget-ranked match processing"
```

---

## Task 7: `assessment_worker.py`

**Files:**
- Create: `backend/app/worker/assessment_worker.py`
- Test: append to `backend/tests/test_workers_plan2_integration.py`

### Context

Runs every 15 minutes. Uses `MatchStateSnapshotRepository.needs_llm_assessment()` (from Plan 1) which already filters to `immediate_attention`/`defensive_gap` buckets — `watchlist` snapshots are never returned so the spec §4.5 gate is satisfied at the repository level.

Creates one `monitoring_event(event_type="llm_assessment", cycle_id=...)` per assessed match. The `cycle_id` is populated by looking up today's `monitoring_cycle` for the brand. Updates `snapshot.llm_assessment` and `llm_source_fingerprint` via direct SQL (avoids triggering the snapshot upsert path which would reset the fingerprint).

- [ ] **Step 7.1: Write the failing test**

```python
# append to backend/tests/test_workers_plan2_integration.py

def test_assessment_worker_processes_snapshots_needing_llm(db_session):
    """assessment_worker finds snapshots needing LLM and calls generate_llm_assessment."""
    from app.models.monitored_brand import MonitoredBrand
    from app.models.similarity_match import SimilarityMatch
    from app.models.match_state_snapshot import MatchStateSnapshot
    from app.worker.assessment_worker import run_assessment_cycle
    from unittest.mock import patch
    from uuid import uuid4
    from datetime import datetime, timezone

    brand = MonitoredBrand(
        id=uuid4(), organization_id=uuid4(),
        brand_name="AssessCo", brand_label="assessco",
        is_active=True,
    )
    db_session.add(brand)
    db_session.flush()

    match = SimilarityMatch(
        id=uuid4(), brand_id=brand.id, organization_id=brand.organization_id,
        domain_name="assessco-bad.com", tld="com", label="assessco-bad",
        score_final=0.75, attention_bucket="immediate_attention",
    )
    db_session.add(match)
    db_session.flush()

    snapshot = MatchStateSnapshot(
        id=uuid4(), match_id=match.id, brand_id=brand.id,
        organization_id=brand.organization_id,
        derived_score=0.75, derived_bucket="immediate_attention",
        derived_risk="high", active_signals=[], signal_codes=[],
        state_fingerprint="fp_new",
        llm_source_fingerprint=None,  # triggers needs_llm_assessment
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
```

- [ ] **Step 7.2: Run test to verify it fails**

```
docker exec -it <backend_container> pytest backend/tests/test_workers_plan2_integration.py::test_assessment_worker_processes_snapshots_needing_llm -v
```
Expected: ImportError

- [ ] **Step 7.3: Implement `assessment_worker.py`**

```python
# backend/app/worker/assessment_worker.py
"""Assessment Worker — LLM assessment of matches whose state has changed.

Runs every 15 minutes. Processes snapshots where:
  - llm_source_fingerprint != state_fingerprint (state changed)
  - OR llm_assessment IS NULL (never assessed)
  - OR last_derived_at > 7 days (TTL)

Note: needs_llm_assessment() already filters to immediate_attention/defensive_gap
buckets. The spec gate "watchlist + low risk → no assessment" is satisfied there.
Batch: 10 snapshots per cycle.
"""
from __future__ import annotations

import logging
import signal
import sys
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session

from app.infra.db.session import SessionLocal
from app.repositories.match_state_snapshot_repository import MatchStateSnapshotRepository
from app.repositories.monitoring_event_repository import MonitoringEventRepository
from app.services.use_cases.generate_llm_assessment import generate_llm_assessment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("assessment_worker")

ASSESSMENT_INTERVAL_MINUTES = 15
LLM_BATCH_SIZE = 10

_last_cycle_completed_at: datetime | None = None


def _get_cycle_id_for_brand(db: Session, brand_id):
    """Look up today's monitoring_cycle.id for a brand (for event FK). May return None."""
    from sqlalchemy import text
    from datetime import date
    row = db.execute(
        text(
            "SELECT id FROM monitoring_cycle"
            " WHERE brand_id = :brand_id AND cycle_date = :today"
            " LIMIT 1"
        ),
        {"brand_id": brand_id, "today": date.today()},
    ).fetchone()
    return row[0] if row else None


def _gather_tool_results(db: Session, snapshot) -> dict:
    """Collect latest tool results for the snapshot's match from recent events."""
    events = MonitoringEventRepository(db).list_for_match(
        match_id=snapshot.match_id, limit=50
    )
    results = {}
    for evt in reversed(events):  # oldest first so latest wins
        if evt.tool_name and evt.result_data:
            results[evt.tool_name] = evt.result_data
    return results


def run_assessment_cycle(db: Session | None = None) -> None:
    """Run one batch of LLM assessments for snapshots that need it."""
    global _last_cycle_completed_at

    owns_session = db is None
    if owns_session:
        db = SessionLocal()

    try:
        snapshot_repo = MatchStateSnapshotRepository(db)
        event_repo = MonitoringEventRepository(db)

        snapshots = snapshot_repo.needs_llm_assessment(limit=LLM_BATCH_SIZE)

        if not snapshots:
            logger.debug("assessment_worker: no snapshots need LLM assessment.")
            return

        logger.info("assessment_worker: processing %d snapshots", len(snapshots))
        assessed = 0

        for snapshot in snapshots:
            try:
                match_dict: dict = {
                    "attention_bucket": snapshot.derived_bucket,
                    "risk_level": snapshot.derived_risk,
                    "score_final": snapshot.derived_score,
                    "domain_name": None,
                }

                from app.models.similarity_match import SimilarityMatch
                match_obj = db.get(SimilarityMatch, snapshot.match_id)
                if match_obj:
                    match_dict["domain_name"] = match_obj.domain_name

                from app.models.monitored_brand import MonitoredBrand
                brand = db.get(MonitoredBrand, snapshot.brand_id)
                brand_name = brand.brand_name if brand else "Unknown"

                tool_results = _gather_tool_results(db, snapshot)

                llm_result = generate_llm_assessment(
                    match=match_dict,
                    brand_name=str(brand_name),
                    tool_results=tool_results,
                    signals=snapshot.active_signals or [],
                )

                if llm_result is None:
                    logger.debug(
                        "LLM assessment skipped for snapshot=%s (gate/no key)", snapshot.id
                    )
                    continue

                # Look up today's cycle for this brand (for event FK — may be None)
                cycle_id = _get_cycle_id_for_brand(db, snapshot.brand_id)

                event_repo.create(
                    organization_id=snapshot.organization_id,
                    brand_id=snapshot.brand_id,
                    match_id=snapshot.match_id,
                    cycle_id=cycle_id,
                    event_type="llm_assessment",
                    event_source="assessment",
                    tool_name="llm",
                    result_data=llm_result,
                )
                db.flush()

                from sqlalchemy import text
                db.execute(
                    text(
                        "UPDATE match_state_snapshot"
                        " SET llm_assessment = :assessment,"
                        "     llm_source_fingerprint = :fingerprint,"
                        "     updated_at = NOW()"
                        " WHERE id = :snapshot_id"
                    ),
                    {
                        "assessment": llm_result,
                        "fingerprint": snapshot.state_fingerprint,
                        "snapshot_id": snapshot.id,
                    },
                )
                db.commit()
                assessed += 1
                logger.info(
                    "LLM assessed snapshot=%s bucket=%s",
                    snapshot.id, snapshot.derived_bucket,
                )

            except Exception:
                db.rollback()
                logger.exception("LLM assessment failed for snapshot=%s", snapshot.id)

        _last_cycle_completed_at = datetime.now(timezone.utc)
        logger.info("assessment_worker cycle complete: assessed=%d", assessed)

    except Exception:
        logger.exception("assessment_worker cycle failed")
    finally:
        if owns_session:
            db.close()


def emit_heartbeat() -> None:
    last_ok = _last_cycle_completed_at.isoformat() if _last_cycle_completed_at else "never"
    logger.info("[HEARTBEAT] assessment_worker alive last_cycle=%s", last_ok)


def main() -> None:
    logger.info(
        "Assessment Worker starting. Interval: every %d minutes",
        ASSESSMENT_INTERVAL_MINUTES,
    )
    run_assessment_cycle()

    scheduler = BlockingScheduler()
    scheduler.add_job(
        run_assessment_cycle,
        IntervalTrigger(minutes=ASSESSMENT_INTERVAL_MINUTES),
        id="llm_assessment",
        replace_existing=True,
    )
    scheduler.add_job(
        emit_heartbeat,
        IntervalTrigger(minutes=5),
        id="assessment_heartbeat",
        replace_existing=True,
    )

    def _shutdown(signum, frame):
        logger.info("Shutting down assessment_worker...")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    scheduler.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 7.4: Run test to verify it passes**

```
docker exec -it <backend_container> pytest backend/tests/test_workers_plan2_integration.py::test_assessment_worker_processes_snapshots_needing_llm -v
```
Expected: PASS

- [ ] **Step 7.5: Commit**

```bash
git add backend/app/worker/assessment_worker.py \
        backend/tests/test_workers_plan2_integration.py
git commit -m "feat(workers): add assessment_worker for LLM reassessment on fingerprint change"
```

---

## Task 8: Docker stack integration

**Files:**
- Modify: `infra/stack.dev.yml`

### Context

Replace the existing `similarity_worker` service entry with 4 dedicated workers. The `scan_worker.py` absorbs the manual queued job handling from `similarity_worker.py`, so the old service entry is no longer needed.

- [ ] **Step 8.1: Update `infra/stack.dev.yml`**

Remove the `similarity_worker:` service block and replace it with these 4 entries:

```yaml
  health_worker:
    image: observadordedominios-backend:dev
    volumes:
      - c:\PROJETOS\observadordedominios\backend:/app
    environment:
      - PYTHONUNBUFFERED=1
      - ENVIRONMENT=development
      - DATABASE_URL=postgresql://obs:obs@postgres:5432/obs
      - HEALTH_CHECK_CRON=0 6 * * *
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}
    command: ["python", "-m", "app.worker.health_worker"]
    networks:
      - app-network
    depends_on:
      - postgres
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure

  scan_worker:
    image: observadordedominios-backend:dev
    volumes:
      - c:\PROJETOS\observadordedominios\backend:/app
    environment:
      - PYTHONUNBUFFERED=1
      - ENVIRONMENT=development
      - DATABASE_URL=postgresql://obs:obs@postgres:5432/obs
      - SIMILARITY_SCAN_CRON=0 9 * * *
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}
    command: ["python", "-m", "app.worker.scan_worker"]
    networks:
      - app-network
    depends_on:
      - postgres
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure

  enrichment_worker:
    image: observadordedominios-backend:dev
    volumes:
      - c:\PROJETOS\observadordedominios\backend:/app
    environment:
      - PYTHONUNBUFFERED=1
      - ENVIRONMENT=development
      - DATABASE_URL=postgresql://obs:obs@postgres:5432/obs
      - ENRICHMENT_CRON=0 12 * * *
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}
    command: ["python", "-m", "app.worker.enrichment_worker"]
    networks:
      - app-network
    depends_on:
      - postgres
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure

  assessment_worker:
    image: observadordedominios-backend:dev
    volumes:
      - c:\PROJETOS\observadordedominios\backend:/app
    environment:
      - PYTHONUNBUFFERED=1
      - ENVIRONMENT=development
      - DATABASE_URL=postgresql://obs:obs@postgres:5432/obs
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}
    command: ["python", "-m", "app.worker.assessment_worker"]
    networks:
      - app-network
    depends_on:
      - postgres
    deploy:
      replicas: 1
      restart_policy:
        condition: on-failure
```

- [ ] **Step 8.2: Run the full test suite one final time**

```
docker exec -it <backend_container> pytest backend/tests/ -v --tb=short 2>&1 | tail -40
```
Expected: All previously passing tests still pass + all 5 new integration tests pass.

- [ ] **Step 8.3: Commit**

```bash
git add infra/stack.dev.yml
git commit -m "feat(infra): replace similarity_worker with 4 dedicated monitoring workers in stack.dev.yml"
```
