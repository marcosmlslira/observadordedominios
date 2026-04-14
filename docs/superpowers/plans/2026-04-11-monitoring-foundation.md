# Monitoring Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the event-sourced data foundation for the new monitoring model — 4 new tables, their repositories, the aggregator service, and the monitoring cycle lifecycle — so that Plan 2 (Workers) can write events and Plan 3 (API) can read snapshots.

**Architecture:** Event-sourced with materialized snapshots. `monitoring_event` records every tool execution as an immutable fact. An aggregator recalculates `match_state_snapshot` and `brand_domain_health` after each event. `monitoring_cycle` tracks the daily progress of each brand's monitoring pipeline. `similarity_match` gains 5 new columns for fingerprint, auto-disposition, and enrichment budget ranking.

**Tech Stack:** Python 3.12, FastAPI, PostgreSQL, SQLAlchemy ORM, Alembic migrations, pytest

**Spec:** `docs/superpowers/specs/2026-04-11-monitoring-model-redesign.md`

---

## File Map

### New files — Models
- `backend/app/models/monitoring_event.py` — immutable event record (tool execution, llm assessment, state change, auto-disposition)
- `backend/app/models/monitoring_cycle.py` — daily per-brand monitoring progress tracker
- `backend/app/models/brand_domain_health.py` — materialized health state of official domains
- `backend/app/models/match_state_snapshot.py` — materialized threat state of similarity matches

### Modified files — Models
- `backend/app/models/similarity_match.py` — add 5 new columns: `state_fingerprint`, `last_fingerprint_at`, `auto_disposition`, `auto_disposition_reason`, `enrichment_budget_rank`
- `backend/app/models/__init__.py` (or `base.py`) — register new models so Alembic detects them

### New files — Migrations
- `backend/alembic/versions/025_monitoring_foundation.py` — create the 4 new tables + alter similarity_match

### New files — Repositories
- `backend/app/repositories/monitoring_event_repository.py` — create events, fetch latest by target+tool, list by match/brand_domain
- `backend/app/repositories/monitoring_cycle_repository.py` — get_or_create cycle for today, update status/counters
- `backend/app/repositories/brand_domain_health_repository.py` — upsert health state per domain
- `backend/app/repositories/match_state_snapshot_repository.py` — upsert snapshot per match, fetch by brand/bucket

### New files — Services
- `backend/app/services/monitoring_cycle_service.py` — begin/finish each stage (health, scan, enrichment), increment counters
- `backend/app/services/state_aggregator.py` — recalculate `match_state_snapshot` from events; recalculate `brand_domain_health` from events; compute `state_fingerprint`

### New files — Tests
- `backend/tests/test_monitoring_event_repository.py`
- `backend/tests/test_monitoring_cycle_service.py`
- `backend/tests/test_state_aggregator.py`

---

## Task 1: New Models

**Files:**
- Create: `backend/app/models/monitoring_event.py`
- Create: `backend/app/models/monitoring_cycle.py`
- Create: `backend/app/models/brand_domain_health.py`
- Create: `backend/app/models/match_state_snapshot.py`

- [ ] **Step 1: Create `monitoring_event.py`**

```python
# backend/app/models/monitoring_event.py
"""MonitoringEvent — immutable record of a tool execution or state change."""
from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint, Column, DateTime, ForeignKey, Index, String, Text, text
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base


class MonitoringEvent(Base):
    """
    Immutable event sourced from tool executions, LLM assessments, or state changes.

    Responsibility: Entity — one record per tool execution against one target.
    Domain: monitoring
    Who writes: health_worker, enrichment_worker, assessment_worker, scan_worker
    Who reads: aggregator, API (events timeline)
    Volume: ~2300/day across all brands; max ~210k rows at 90-day retention
    Growth: linear with number of brands × tools per cycle

    NOTE: Does NOT inherit TimestampMixin — events are immutable and have no updated_at.
    TimestampMixin uses bare Column definitions (not @declared_attr), so it cannot be
    overridden per-subclass. We define created_at manually here.
    """
    __tablename__ = "monitoring_event"

    # Events are write-once — only created_at, no updated_at
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand.id", ondelete="CASCADE"),
        nullable=False,
    )
    cycle_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_cycle.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Polymorphic target: exactly one must be non-null (enforced by DB constraint)
    match_id = Column(
        UUID(as_uuid=True),
        ForeignKey("similarity_match.id", ondelete="CASCADE"),
        nullable=True,
    )
    brand_domain_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand_domain.id", ondelete="CASCADE"),
        nullable=True,
    )

    # Event classification
    event_type = Column(
        String(48), nullable=False
    )  # "tool_execution" | "llm_assessment" | "state_change" | "auto_disposition"
    event_source = Column(
        String(32), nullable=False
    )  # "health_check" | "enrichment" | "manual" | "scan"

    # Tool data (nullable for non-tool events like state_change)
    tool_name = Column(String(48), nullable=True)
    tool_version = Column(String(16), nullable=True)

    # Payload
    result_data = Column(JSONB, nullable=False, default=dict)
    signals = Column(JSONB, nullable=True)       # [{code, severity, score_adjustment, description}]
    score_snapshot = Column(JSONB, nullable=True)  # score at time of event

    # Cache TTL (when this data becomes stale and needs re-execution)
    ttl_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    brand = relationship("MonitoredBrand", back_populates=None, lazy="raise")
    match = relationship("SimilarityMatch", back_populates=None, lazy="raise")
    brand_domain = relationship("MonitoredBrandDomain", back_populates=None, lazy="raise")

    __table_args__ = (
        CheckConstraint(
            "(match_id IS NOT NULL AND brand_domain_id IS NULL) OR "
            "(match_id IS NULL AND brand_domain_id IS NOT NULL)",
            name="chk_event_target",
        ),
        Index("ix_event_match", "match_id", "created_at"),
        Index("ix_event_brand_domain", "brand_domain_id", "created_at"),
        Index("ix_event_brand_cycle", "brand_id", "cycle_id"),
        Index("ix_event_tool_latest", "match_id", "tool_name", "created_at"),
    )
```

- [ ] **Step 2: Create `monitoring_cycle.py`**

```python
# backend/app/models/monitoring_cycle.py
"""MonitoringCycle — daily per-brand monitoring progress tracker."""
from __future__ import annotations

import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class MonitoringCycle(Base, TimestampMixin):
    """
    One record per brand per day. Aggregates progress of all pipeline stages.

    Responsibility: Configuration/Event — daily pipeline state.
    Domain: monitoring
    Who writes: health_worker, scan_worker, enrichment_worker
    Who reads: API (brand detail), assessment_worker
    Volume: 1 per active brand per day; retained 180 days
    Growth: linear with number of brands
    """
    __tablename__ = "monitoring_cycle"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(UUID(as_uuid=True), nullable=False)
    cycle_date = Column(Date, nullable=False)
    cycle_type = Column(String(16), nullable=False, default="scheduled")  # "scheduled" | "manual"

    # Stage statuses
    health_status = Column(String(16), nullable=False, default="pending")
    health_started_at = Column(DateTime(timezone=True), nullable=True)
    health_finished_at = Column(DateTime(timezone=True), nullable=True)

    scan_status = Column(String(16), nullable=False, default="pending")
    scan_started_at = Column(DateTime(timezone=True), nullable=True)
    scan_finished_at = Column(DateTime(timezone=True), nullable=True)
    scan_job_id = Column(
        UUID(as_uuid=True),
        ForeignKey("similarity_scan_job.id", ondelete="SET NULL"),
        nullable=True,
    )

    enrichment_status = Column(String(16), nullable=False, default="pending")
    enrichment_started_at = Column(DateTime(timezone=True), nullable=True)
    enrichment_finished_at = Column(DateTime(timezone=True), nullable=True)
    enrichment_budget = Column(Integer, nullable=False, default=0)
    enrichment_total = Column(Integer, nullable=False, default=0)

    # Summary counters (updated incrementally)
    new_matches_count = Column(Integer, nullable=False, default=0)
    escalated_count = Column(Integer, nullable=False, default=0)
    dismissed_count = Column(Integer, nullable=False, default=0)
    threats_detected = Column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("brand_id", "cycle_date", name="uq_cycle_brand_date"),
        Index("ix_cycle_brand_date", "brand_id", "cycle_date"),
    )
```

- [ ] **Step 3: Create `brand_domain_health.py`**

```python
# backend/app/models/brand_domain_health.py
"""BrandDomainHealth — materialized health state of an official brand domain."""
from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class BrandDomainHealth(Base, TimestampMixin):
    """
    Materialized view of the latest health check results for one official domain.
    Recalculated by the aggregator after each health check event.

    Responsibility: Snapshot — derived state, not source of truth.
    Domain: monitoring
    Who writes: state_aggregator (triggered by health_worker events)
    Who reads: API (brand detail /health endpoint)
    Volume: 1 per brand_domain; stable, grows with domains added
    Growth: very slow
    """
    __tablename__ = "brand_domain_health"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    brand_domain_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand_domain.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(UUID(as_uuid=True), nullable=False)

    # Derived overall status
    overall_status = Column(String(16), nullable=False, default="unknown")
    # "healthy" | "warning" | "critical" | "unknown"

    # Per-tool booleans (None = not checked yet / tool failed)
    dns_ok = Column(Boolean, nullable=True)
    ssl_ok = Column(Boolean, nullable=True)
    ssl_days_remaining = Column(Integer, nullable=True)
    email_security_ok = Column(Boolean, nullable=True)
    spoofing_risk = Column(String(16), nullable=True)  # "none" | "low" | "medium" | "high" | "critical"
    headers_score = Column(String(16), nullable=True)  # "good" | "partial" | "poor"
    takeover_risk = Column(Boolean, nullable=True)
    blacklisted = Column(Boolean, nullable=True)
    safe_browsing_hit = Column(Boolean, nullable=True)
    urlhaus_hit = Column(Boolean, nullable=True)
    phishtank_hit = Column(Boolean, nullable=True)
    suspicious_content = Column(Boolean, nullable=True)

    # Fingerprint and traceability
    state_fingerprint = Column(String(64), nullable=True)
    last_check_at = Column(DateTime(timezone=True), nullable=True)
    last_event_ids = Column(JSONB, nullable=True)  # [event_id, ...] that produced this state

    __table_args__ = (
        Index("ix_health_brand", "brand_id"),
    )
```

- [ ] **Step 4: Create `match_state_snapshot.py`**

```python
# backend/app/models/match_state_snapshot.py
"""MatchStateSnapshot — materialized threat state of a similarity match."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Float, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class MatchStateSnapshot(Base, TimestampMixin):
    """
    Materialized projection of the current threat state for one similarity match.
    Recalculated by the aggregator each time a new monitoring_event arrives for this match.

    Responsibility: Snapshot — derived state. Source of truth for current risk level.
    Domain: monitoring
    Who writes: state_aggregator (triggered by enrichment_worker events)
    Who reads: API (matches list, match drawer), assessment_worker
    Volume: 1 per similarity_match that has been enriched; ~hundreds to low thousands
    Growth: mirrors enriched matches count
    """
    __tablename__ = "match_state_snapshot"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    match_id = Column(
        UUID(as_uuid=True),
        ForeignKey("similarity_match.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    brand_id = Column(
        UUID(as_uuid=True),
        ForeignKey("monitored_brand.id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id = Column(UUID(as_uuid=True), nullable=False)

    # Derived scores (recalculated from lexical score + signal adjustments)
    derived_score = Column(Float, nullable=False, default=0.0)
    derived_bucket = Column(String(32), nullable=False, default="watchlist")
    # "immediate_attention" | "defensive_gap" | "watchlist"
    derived_risk = Column(String(16), nullable=False, default="low")
    # "low" | "medium" | "high" | "critical"
    derived_disposition = Column(String(32), nullable=True)

    # Aggregated signals from all active events
    active_signals = Column(JSONB, nullable=False, default=list)
    # [{code, severity, source_tool, source_event_id, score_adjustment}]
    signal_codes = Column(ARRAY(String), nullable=True)  # flat list for fast queries

    # LLM assessment (written by assessment_worker via aggregator)
    llm_assessment = Column(JSONB, nullable=True)
    llm_event_id = Column(UUID(as_uuid=True), nullable=True)
    llm_source_fingerprint = Column(String(64), nullable=True)
    # When llm_source_fingerprint != state_fingerprint, LLM reassessment is needed

    # Fingerprint for LLM staleness detection
    state_fingerprint = Column(String(64), nullable=False, default="")
    events_hash = Column(String(64), nullable=True)
    last_derived_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    __table_args__ = (
        Index("ix_snapshot_brand_bucket", "brand_id", "derived_bucket", "derived_score"),
        Index("ix_snapshot_brand_risk", "brand_id", "derived_risk", "derived_score"),
        # Partial index for needs_llm_assessment() query — avoids full table scan
        Index(
            "ix_snapshot_needs_llm",
            "brand_id",
            postgresql_where=text("llm_source_fingerprint IS DISTINCT FROM state_fingerprint"),
        ),
    )
```

- [ ] **Step 5: Register new models in `backend/app/models/__init__.py` (or wherever models are imported for Alembic auto-detection)**

Check if there's a central import file:
```bash
grep -r "from app.models" backend/app/main.py backend/alembic/env.py 2>/dev/null | head -20
```

Add imports so Alembic detects the new tables:
```python
from app.models.monitoring_event import MonitoringEvent  # noqa: F401
from app.models.monitoring_cycle import MonitoringCycle  # noqa: F401
from app.models.brand_domain_health import BrandDomainHealth  # noqa: F401
from app.models.match_state_snapshot import MatchStateSnapshot  # noqa: F401
```

---

## Task 2: Alter `similarity_match` Model

**Files:**
- Modify: `backend/app/models/similarity_match.py`

- [ ] **Step 1: Add 5 new columns to `SimilarityMatch`**

Open `backend/app/models/similarity_match.py`. Find the last column definition and add after it:

```python
# ── Event-sourced monitoring fields ───────────────────────────
state_fingerprint = Column(String(64), nullable=True)
last_fingerprint_at = Column(DateTime(timezone=True), nullable=True)
auto_disposition = Column(String(32), nullable=True)
# "auto_dismissed" | "auto_escalated" | NULL
auto_disposition_reason = Column(Text, nullable=True)
enrichment_budget_rank = Column(Integer, nullable=True)
# Position in per-cycle enrichment priority queue. NULL = not in budget this cycle.
```

Also add `Integer` to the imports at the top if not already present.

---

## Task 3: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/025_monitoring_foundation.py`

- [ ] **Step 1: Create migration file**

```python
# backend/alembic/versions/025_monitoring_foundation.py
"""Add event-sourced monitoring foundation tables.

Creates: monitoring_cycle, monitoring_event, brand_domain_health, match_state_snapshot
Alters: similarity_match (adds 5 new columns)

Revision ID: 025_monitoring_foundation
Revises: 024_ingestion_tld_priority
Create Date: 2026-04-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "025_monitoring_foundation"
down_revision = "024_ingestion_tld_priority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── monitoring_cycle ──────────────────────────────────────
    op.create_table(
        "monitoring_cycle",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", UUID(as_uuid=True),
                  sa.ForeignKey("monitored_brand.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_date", sa.Date, nullable=False),
        sa.Column("cycle_type", sa.String(16), nullable=False, server_default="scheduled"),
        # Stage: health
        sa.Column("health_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("health_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_finished_at", sa.DateTime(timezone=True), nullable=True),
        # Stage: scan
        sa.Column("scan_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("scan_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_job_id", UUID(as_uuid=True),
                  sa.ForeignKey("similarity_scan_job.id", ondelete="SET NULL"), nullable=True),
        # Stage: enrichment
        sa.Column("enrichment_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("enrichment_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrichment_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrichment_budget", sa.Integer, nullable=False, server_default="0"),
        sa.Column("enrichment_total", sa.Integer, nullable=False, server_default="0"),
        # Summary counters
        sa.Column("new_matches_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("escalated_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("dismissed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("threats_detected", sa.Integer, nullable=False, server_default="0"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_cycle_brand_date", "monitoring_cycle", ["brand_id", "cycle_date"])
    op.create_index("ix_cycle_brand_date", "monitoring_cycle", ["brand_id", "cycle_date"])

    # ── monitoring_event ──────────────────────────────────────
    op.create_table(
        "monitoring_event",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", UUID(as_uuid=True),
                  sa.ForeignKey("monitored_brand.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cycle_id", UUID(as_uuid=True),
                  sa.ForeignKey("monitoring_cycle.id", ondelete="SET NULL"), nullable=True),
        sa.Column("match_id", UUID(as_uuid=True),
                  sa.ForeignKey("similarity_match.id", ondelete="CASCADE"), nullable=True),
        sa.Column("brand_domain_id", UUID(as_uuid=True),
                  sa.ForeignKey("monitored_brand_domain.id", ondelete="CASCADE"), nullable=True),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("event_source", sa.String(32), nullable=False),
        sa.Column("tool_name", sa.String(48), nullable=True),
        sa.Column("tool_version", sa.String(16), nullable=True),
        sa.Column("result_data", JSONB, nullable=False, server_default="{}"),
        sa.Column("signals", JSONB, nullable=True),
        sa.Column("score_snapshot", JSONB, nullable=True),
        sa.Column("ttl_expires_at", sa.DateTime(timezone=True), nullable=True),
        # No updated_at — monitoring_event is immutable by design
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_check_constraint(
        "chk_event_target",
        "monitoring_event",
        "(match_id IS NOT NULL AND brand_domain_id IS NULL) OR "
        "(match_id IS NULL AND brand_domain_id IS NOT NULL)",
    )
    op.create_index("ix_event_match", "monitoring_event", ["match_id", "created_at"])
    op.create_index("ix_event_brand_domain", "monitoring_event", ["brand_domain_id", "created_at"])
    op.create_index("ix_event_brand_cycle", "monitoring_event", ["brand_id", "cycle_id"])
    op.create_index("ix_event_tool_latest", "monitoring_event",
                    ["match_id", "tool_name", "created_at"])

    # ── brand_domain_health ───────────────────────────────────
    op.create_table(
        "brand_domain_health",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_domain_id", UUID(as_uuid=True),
                  sa.ForeignKey("monitored_brand_domain.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("brand_id", UUID(as_uuid=True),
                  sa.ForeignKey("monitored_brand.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("overall_status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("dns_ok", sa.Boolean, nullable=True),
        sa.Column("ssl_ok", sa.Boolean, nullable=True),
        sa.Column("ssl_days_remaining", sa.Integer, nullable=True),
        sa.Column("email_security_ok", sa.Boolean, nullable=True),
        sa.Column("spoofing_risk", sa.String(16), nullable=True),
        sa.Column("headers_score", sa.String(16), nullable=True),
        sa.Column("takeover_risk", sa.Boolean, nullable=True),
        sa.Column("blacklisted", sa.Boolean, nullable=True),
        sa.Column("safe_browsing_hit", sa.Boolean, nullable=True),
        sa.Column("urlhaus_hit", sa.Boolean, nullable=True),
        sa.Column("phishtank_hit", sa.Boolean, nullable=True),
        sa.Column("suspicious_content", sa.Boolean, nullable=True),
        sa.Column("state_fingerprint", sa.String(64), nullable=True),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_ids", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_health_brand", "brand_domain_health", ["brand_id"])

    # ── match_state_snapshot ──────────────────────────────────
    op.create_table(
        "match_state_snapshot",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("match_id", UUID(as_uuid=True),
                  sa.ForeignKey("similarity_match.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("brand_id", UUID(as_uuid=True),
                  sa.ForeignKey("monitored_brand.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("derived_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("derived_bucket", sa.String(32), nullable=False, server_default="watchlist"),
        sa.Column("derived_risk", sa.String(16), nullable=False, server_default="low"),
        sa.Column("derived_disposition", sa.String(32), nullable=True),
        sa.Column("active_signals", JSONB, nullable=False, server_default="[]"),
        sa.Column("signal_codes", ARRAY(sa.String), nullable=True),
        sa.Column("llm_assessment", JSONB, nullable=True),
        sa.Column("llm_event_id", UUID(as_uuid=True), nullable=True),
        sa.Column("llm_source_fingerprint", sa.String(64), nullable=True),
        sa.Column("state_fingerprint", sa.String(64), nullable=False, server_default=""),
        sa.Column("events_hash", sa.String(64), nullable=True),
        sa.Column("last_derived_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_snapshot_brand_bucket", "match_state_snapshot",
                    ["brand_id", "derived_bucket", "derived_score"])
    op.create_index("ix_snapshot_brand_risk", "match_state_snapshot",
                    ["brand_id", "derived_risk", "derived_score"])
    # Partial index for needs_llm_assessment() — avoids full table scan in assessment_worker
    op.create_index(
        "ix_snapshot_needs_llm", "match_state_snapshot", ["brand_id"],
        postgresql_where=sa.text("llm_source_fingerprint IS DISTINCT FROM state_fingerprint"),
    )

    # ── similarity_match: new columns ─────────────────────────
    op.add_column("similarity_match",
                  sa.Column("state_fingerprint", sa.String(64), nullable=True))
    op.add_column("similarity_match",
                  sa.Column("last_fingerprint_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("similarity_match",
                  sa.Column("auto_disposition", sa.String(32), nullable=True))
    op.add_column("similarity_match",
                  sa.Column("auto_disposition_reason", sa.Text, nullable=True))
    op.add_column("similarity_match",
                  sa.Column("enrichment_budget_rank", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("similarity_match", "enrichment_budget_rank")
    op.drop_column("similarity_match", "auto_disposition_reason")
    op.drop_column("similarity_match", "auto_disposition")
    op.drop_column("similarity_match", "last_fingerprint_at")
    op.drop_column("similarity_match", "state_fingerprint")

    op.drop_table("match_state_snapshot")
    op.drop_table("brand_domain_health")
    op.drop_table("monitoring_event")
    op.drop_table("monitoring_cycle")
```

- [ ] **Step 2: Run migration to verify it applies cleanly**

```bash
docker exec -it $(docker ps --filter name=obs_backend -q) \
  alembic -c alembic.ini upgrade head
```

Expected output: `Running upgrade 024_ingestion_tld_priority -> 025_monitoring_foundation, ...`

- [ ] **Step 3: Verify tables exist in DB**

```bash
docker exec -it $(docker ps --filter name=obs_backend -q) \
  python -c "
from app.core.db import get_engine
from sqlalchemy import inspect
eng = get_engine()
insp = inspect(eng)
tables = insp.get_table_names()
for t in ['monitoring_cycle','monitoring_event','brand_domain_health','match_state_snapshot']:
    print(t, '✓' if t in tables else '✗ MISSING')
"
```

Expected: all 4 `✓`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/monitoring_event.py \
        backend/app/models/monitoring_cycle.py \
        backend/app/models/brand_domain_health.py \
        backend/app/models/match_state_snapshot.py \
        backend/app/models/similarity_match.py \
        backend/alembic/versions/025_monitoring_foundation.py
git commit -m "feat(monitoring): add event-sourced foundation models and migration 025"
```

---

## Task 4: Repositories

**Files:**
- Create: `backend/app/repositories/monitoring_event_repository.py`
- Create: `backend/app/repositories/monitoring_cycle_repository.py`
- Create: `backend/app/repositories/brand_domain_health_repository.py`
- Create: `backend/app/repositories/match_state_snapshot_repository.py`

- [ ] **Step 1: Write failing test for `MonitoringEventRepository`**

```python
# backend/tests/test_monitoring_event_repository.py
"""Tests for MonitoringEventRepository."""
from __future__ import annotations
import sys, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from unittest.mock import MagicMock, patch
from app.repositories.monitoring_event_repository import MonitoringEventRepository
from app.models.monitoring_event import MonitoringEvent


def make_event(**kwargs):
    defaults = dict(
        organization_id=uuid.uuid4(),
        brand_id=uuid.uuid4(),
        match_id=uuid.uuid4(),
        brand_domain_id=None,
        event_type="tool_execution",
        event_source="enrichment",
        tool_name="dns_lookup",
        result_data={"records": []},
    )
    defaults.update(kwargs)
    return defaults


def test_create_event_returns_model():
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    repo = MonitoringEventRepository(db)
    evt = repo.create(**make_event())
    db.add.assert_called_once()
    assert isinstance(evt, MonitoringEvent)


def test_fetch_latest_for_match_tool():
    db = MagicMock()
    repo = MonitoringEventRepository(db)
    match_id = uuid.uuid4()
    # Should call db.query with match_id and tool_name filters
    result = repo.fetch_latest_for_match_tool(match_id=match_id, tool_name="dns_lookup")
    db.query.assert_called_once_with(MonitoringEvent)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
docker exec -it $(docker ps --filter name=obs_backend -q) \
  python -m pytest tests/test_monitoring_event_repository.py -v 2>&1 | head -30
```

Expected: `ImportError: cannot import name 'MonitoringEventRepository'`

- [ ] **Step 3: Implement `MonitoringEventRepository`**

```python
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

    def list_for_brand_domain(
        self,
        *,
        brand_domain_id: UUID,
        limit: int = 50,
    ) -> list[MonitoringEvent]:
        """Return recent events for one official domain."""
        return (
            self.db.query(MonitoringEvent)
            .filter(MonitoringEvent.brand_domain_id == brand_domain_id)
            .order_by(MonitoringEvent.created_at.desc())
            .limit(limit)
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
docker exec -it $(docker ps --filter name=obs_backend -q) \
  python -m pytest tests/test_monitoring_event_repository.py -v
```

Expected: `2 passed`

- [ ] **Step 5: Create `MonitoringCycleRepository`**

```python
# backend/app/repositories/monitoring_cycle_repository.py
"""Repository for monitoring cycles — one record per brand per day."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.monitoring_cycle import MonitoringCycle


class MonitoringCycleRepository:
    """CRUD for monitoring_cycle records."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_or_create_today(
        self,
        *,
        brand_id: UUID,
        organization_id: UUID,
        cycle_type: str = "scheduled",
    ) -> tuple[MonitoringCycle, bool]:
        """
        Return (cycle, created). If a cycle for today already exists, return it.
        Idempotent — safe to call multiple times per day.
        """
        today = date.today()
        existing = (
            self.db.query(MonitoringCycle)
            .filter(
                MonitoringCycle.brand_id == brand_id,
                MonitoringCycle.cycle_date == today,
            )
            .first()
        )
        if existing:
            return existing, False

        cycle = MonitoringCycle(
            id=uuid.uuid4(),
            brand_id=brand_id,
            organization_id=organization_id,
            cycle_date=today,
            cycle_type=cycle_type,
        )
        self.db.add(cycle)
        self.db.flush()
        return cycle, True

    def get_latest_for_brand(self, brand_id: UUID) -> MonitoringCycle | None:
        """Return the most recent cycle for a brand."""
        return (
            self.db.query(MonitoringCycle)
            .filter(MonitoringCycle.brand_id == brand_id)
            .order_by(MonitoringCycle.cycle_date.desc())
            .first()
        )

    def list_for_brand(
        self,
        brand_id: UUID,
        *,
        limit: int = 30,
        offset: int = 0,
    ) -> list[MonitoringCycle]:
        return (
            self.db.query(MonitoringCycle)
            .filter(MonitoringCycle.brand_id == brand_id)
            .order_by(MonitoringCycle.cycle_date.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def update_stage(
        self,
        cycle_id: UUID,
        *,
        stage: str,          # "health" | "scan" | "enrichment"
        status: str,         # "running" | "completed" | "failed" | "skipped"
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        scan_job_id: UUID | None = None,
    ) -> None:
        """Update one stage's status and timestamps. Caller must commit."""
        updates: dict = {f"{stage}_status": status}
        if started_at:
            updates[f"{stage}_started_at"] = started_at
        if finished_at:
            updates[f"{stage}_finished_at"] = finished_at
        if scan_job_id and stage == "scan":
            updates["scan_job_id"] = scan_job_id
        updates["updated_at"] = datetime.now(timezone.utc)
        self.db.query(MonitoringCycle).filter(
            MonitoringCycle.id == cycle_id
        ).update(updates)

    _ALLOWED_COUNTERS = frozenset({
        "new_matches_count", "escalated_count", "dismissed_count", "threats_detected"
    })

    def increment_counter(
        self,
        cycle_id: UUID,
        *,
        field: str,  # must be one of _ALLOWED_COUNTERS
        amount: int = 1,
    ) -> None:
        """Atomically increment a summary counter. Caller must commit."""
        if field not in self._ALLOWED_COUNTERS:
            raise ValueError(f"Invalid counter field: {field!r}. Allowed: {self._ALLOWED_COUNTERS}")
        from sqlalchemy import text
        self.db.execute(
            text(f"UPDATE monitoring_cycle SET {field} = {field} + :amt, updated_at = now() WHERE id = :id"),
            {"amt": amount, "id": cycle_id},
        )
```

- [ ] **Step 6: Create `BrandDomainHealthRepository`**

```python
# backend/app/repositories/brand_domain_health_repository.py
"""Repository for brand_domain_health — upsert derived health state."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.brand_domain_health import BrandDomainHealth


class BrandDomainHealthRepository:
    """Upsert-only access to brand_domain_health records."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(
        self,
        *,
        brand_domain_id: UUID,
        brand_id: UUID,
        organization_id: UUID,
        **health_fields,
    ) -> BrandDomainHealth:
        """
        Upsert health state for a domain. Pass any health field as a keyword argument.
        Always updates updated_at. Caller must commit.
        """
        now = datetime.now(timezone.utc)

        stmt = insert(BrandDomainHealth).values(
            id=uuid.uuid4(),
            brand_domain_id=brand_domain_id,
            brand_id=brand_id,
            organization_id=organization_id,
            created_at=now,
            updated_at=now,
            **health_fields,
        ).on_conflict_do_update(
            index_elements=["brand_domain_id"],
            set_={**health_fields, "updated_at": now},
        ).returning(BrandDomainHealth)

        result = self.db.execute(stmt)
        self.db.flush()
        return result.scalar_one()

    def get_by_domain(self, brand_domain_id: UUID) -> BrandDomainHealth | None:
        return (
            self.db.query(BrandDomainHealth)
            .filter(BrandDomainHealth.brand_domain_id == brand_domain_id)
            .first()
        )

    def list_for_brand(self, brand_id: UUID) -> list[BrandDomainHealth]:
        return (
            self.db.query(BrandDomainHealth)
            .filter(BrandDomainHealth.brand_id == brand_id)
            .all()
        )
```

- [ ] **Step 7: Create `MatchStateSnapshotRepository`**

```python
# backend/app/repositories/match_state_snapshot_repository.py
"""Repository for match_state_snapshot — upsert and query derived match state."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.match_state_snapshot import MatchStateSnapshot


class MatchStateSnapshotRepository:
    """Upsert-only writes, rich reads for match state snapshots."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(
        self,
        *,
        match_id: UUID,
        brand_id: UUID,
        organization_id: UUID,
        derived_score: float,
        derived_bucket: str,
        derived_risk: str,
        active_signals: list[dict],
        signal_codes: list[str],
        state_fingerprint: str,
        last_derived_at: datetime,
        derived_disposition: str | None = None,
        llm_assessment: dict | None = None,
        llm_event_id: UUID | None = None,
        llm_source_fingerprint: str | None = None,
        events_hash: str | None = None,
    ) -> MatchStateSnapshot:
        """Upsert snapshot for a match. Caller must commit."""
        now = datetime.now(timezone.utc)
        values = dict(
            match_id=match_id,
            brand_id=brand_id,
            organization_id=organization_id,
            derived_score=derived_score,
            derived_bucket=derived_bucket,
            derived_risk=derived_risk,
            derived_disposition=derived_disposition,
            active_signals=active_signals,
            signal_codes=signal_codes,
            state_fingerprint=state_fingerprint,
            last_derived_at=last_derived_at,
            events_hash=events_hash,
            updated_at=now,
        )
        if llm_assessment is not None:
            values["llm_assessment"] = llm_assessment
        if llm_event_id is not None:
            values["llm_event_id"] = llm_event_id
        if llm_source_fingerprint is not None:
            values["llm_source_fingerprint"] = llm_source_fingerprint

        insert_values = {**values, "id": uuid.uuid4(), "created_at": now}
        update_values = {k: v for k, v in values.items()}

        stmt = insert(MatchStateSnapshot).values(
            **insert_values
        ).on_conflict_do_update(
            index_elements=["match_id"],
            set_=update_values,
        ).returning(MatchStateSnapshot)

        result = self.db.execute(stmt)
        self.db.flush()
        return result.scalar_one()

    def get_by_match(self, match_id: UUID) -> MatchStateSnapshot | None:
        return (
            self.db.query(MatchStateSnapshot)
            .filter(MatchStateSnapshot.match_id == match_id)
            .first()
        )

    def list_for_brand(
        self,
        brand_id: UUID,
        *,
        bucket: str | None = None,
        exclude_auto_dismissed: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MatchStateSnapshot]:
        """List snapshots for a brand, optionally filtered by bucket."""
        from app.models.similarity_match import SimilarityMatch

        q = (
            self.db.query(MatchStateSnapshot)
            .filter(MatchStateSnapshot.brand_id == brand_id)
        )
        if bucket:
            q = q.filter(MatchStateSnapshot.derived_bucket == bucket)
        if exclude_auto_dismissed:
            q = q.join(SimilarityMatch, MatchStateSnapshot.match_id == SimilarityMatch.id).filter(
                SimilarityMatch.auto_disposition.is_(None)
            )
        return (
            q.order_by(MatchStateSnapshot.derived_score.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def count_by_bucket(self, brand_id: UUID) -> dict[str, int]:
        """Return counts per bucket. Used by monitoring_summary in brand list."""
        from sqlalchemy import func
        rows = (
            self.db.query(
                MatchStateSnapshot.derived_bucket,
                func.count(MatchStateSnapshot.id),
            )
            .filter(MatchStateSnapshot.brand_id == brand_id)
            .group_by(MatchStateSnapshot.derived_bucket)
            .all()
        )
        return {bucket: count for bucket, count in rows}

    def needs_llm_assessment(
        self,
        *,
        brand_id: UUID | None = None,
        limit: int = 10,
    ) -> list[MatchStateSnapshot]:
        """
        Return snapshots that need LLM assessment:
        1. fingerprint changed since last LLM assessment, or no LLM yet
        2. last assessment older than 7 days (TTL expiry — force reassess even if fingerprint unchanged)
        Only for immediate_attention or defensive_gap buckets.
        """
        from datetime import timedelta
        from sqlalchemy import func, or_
        LLM_TTL_DAYS = 7
        TTL_TRIGGER = or_(
            MatchStateSnapshot.llm_assessment.is_(None),
            MatchStateSnapshot.llm_source_fingerprint != MatchStateSnapshot.state_fingerprint,
            MatchStateSnapshot.last_derived_at < func.now() - timedelta(days=LLM_TTL_DAYS),
        )
        q = self.db.query(MatchStateSnapshot).filter(
            MatchStateSnapshot.derived_bucket.in_(["immediate_attention", "defensive_gap"]),
            TTL_TRIGGER,
        )
        if brand_id:
            q = q.filter(MatchStateSnapshot.brand_id == brand_id)
        return q.order_by(MatchStateSnapshot.derived_score.desc()).limit(limit).all()
```

- [ ] **Step 8: Commit repositories**

```bash
git add backend/app/repositories/monitoring_event_repository.py \
        backend/app/repositories/monitoring_cycle_repository.py \
        backend/app/repositories/brand_domain_health_repository.py \
        backend/app/repositories/match_state_snapshot_repository.py \
        backend/tests/test_monitoring_event_repository.py
git commit -m "feat(monitoring): add event, cycle, health, and snapshot repositories"
```

---

## Task 5: Monitoring Cycle Service

**Files:**
- Create: `backend/app/services/monitoring_cycle_service.py`
- Test: `backend/tests/test_monitoring_cycle_service.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_monitoring_cycle_service.py
from __future__ import annotations
import sys, uuid
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from unittest.mock import MagicMock, patch, call
from app.services.monitoring_cycle_service import MonitoringCycleService
from app.models.monitoring_cycle import MonitoringCycle


def make_cycle(**kwargs):
    c = MagicMock(spec=MonitoringCycle)
    c.id = uuid.uuid4()
    c.health_status = "pending"
    c.scan_status = "pending"
    c.enrichment_status = "pending"
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def test_begin_stage_updates_status_and_timestamp():
    db = MagicMock()
    cycle = make_cycle()
    repo = MagicMock()
    svc = MonitoringCycleService(db, cycle_repo=repo)
    svc.begin_stage(cycle.id, stage="health")
    repo.update_stage.assert_called_once()
    call_kwargs = repo.update_stage.call_args.kwargs
    assert call_kwargs["stage"] == "health"
    assert call_kwargs["status"] == "running"
    assert call_kwargs["started_at"] is not None


def test_finish_stage_updates_status_and_finished_at():
    db = MagicMock()
    cycle = make_cycle()
    repo = MagicMock()
    svc = MonitoringCycleService(db, cycle_repo=repo)
    svc.finish_stage(cycle.id, stage="health", success=True)
    call_kwargs = repo.update_stage.call_args.kwargs
    assert call_kwargs["status"] == "completed"
    assert call_kwargs["finished_at"] is not None


def test_finish_stage_marks_failed_on_error():
    db = MagicMock()
    repo = MagicMock()
    svc = MonitoringCycleService(db, cycle_repo=repo)
    svc.finish_stage(uuid.uuid4(), stage="enrichment", success=False)
    assert repo.update_stage.call_args.kwargs["status"] == "failed"
```

- [ ] **Step 2: Run failing tests**

```bash
docker exec -it $(docker ps --filter name=obs_backend -q) \
  python -m pytest tests/test_monitoring_cycle_service.py -v 2>&1 | head -20
```

Expected: `ImportError`

- [ ] **Step 3: Implement `MonitoringCycleService`**

```python
# backend/app/services/monitoring_cycle_service.py
"""Service for managing the lifecycle of a monitoring cycle."""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.monitoring_cycle_repository import MonitoringCycleRepository


class MonitoringCycleService:
    """
    Manages stage transitions for a monitoring_cycle record.
    Workers call begin_stage/finish_stage to record progress.
    """

    def __init__(
        self,
        db: Session,
        *,
        cycle_repo: MonitoringCycleRepository | None = None,
    ) -> None:
        self.db = db
        self.repo = cycle_repo or MonitoringCycleRepository(db)

    def begin_stage(self, cycle_id: UUID, *, stage: str) -> None:
        """Mark a stage as running and record start timestamp. Caller must commit."""
        self.repo.update_stage(
            cycle_id,
            stage=stage,
            status="running",
            started_at=datetime.now(timezone.utc),
        )

    def finish_stage(
        self,
        cycle_id: UUID,
        *,
        stage: str,
        success: bool,
        scan_job_id: UUID | None = None,
    ) -> None:
        """Mark a stage as completed or failed and record end timestamp. Caller must commit."""
        self.repo.update_stage(
            cycle_id,
            stage=stage,
            status="completed" if success else "failed",
            finished_at=datetime.now(timezone.utc),
            scan_job_id=scan_job_id,
        )

    def skip_stage(self, cycle_id: UUID, *, stage: str) -> None:
        """Mark a stage as skipped (e.g., brand has no official domains). Caller must commit."""
        self.repo.update_stage(cycle_id, stage=stage, status="skipped")

    def record_new_match(self, cycle_id: UUID) -> None:
        """Increment new_matches_count. Caller must commit at batch boundary."""
        self.repo.increment_counter(cycle_id, field="new_matches_count")

    def record_threat_detected(self, cycle_id: UUID) -> None:
        """Increment threats_detected. Caller must commit at batch boundary."""
        self.repo.increment_counter(cycle_id, field="threats_detected")

    def record_dismissed(self, cycle_id: UUID) -> None:
        """Increment dismissed_count. Caller must commit at batch boundary."""
        self.repo.increment_counter(cycle_id, field="dismissed_count")

    def record_escalated(self, cycle_id: UUID) -> None:
        """Increment escalated_count. Caller must commit at batch boundary."""
        self.repo.increment_counter(cycle_id, field="escalated_count")
```

- [ ] **Step 4: Run tests**

```bash
docker exec -it $(docker ps --filter name=obs_backend -q) \
  python -m pytest tests/test_monitoring_cycle_service.py -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/monitoring_cycle_service.py \
        backend/tests/test_monitoring_cycle_service.py
git commit -m "feat(monitoring): add MonitoringCycleService for stage lifecycle"
```

---

## Task 6: State Aggregator

**Files:**
- Create: `backend/app/services/state_aggregator.py`
- Test: `backend/tests/test_state_aggregator.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_state_aggregator.py
"""Tests for the state aggregator — fingerprint, score, bucket derivation."""
from __future__ import annotations
import sys, uuid, hashlib, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.state_aggregator import (
    compute_state_fingerprint,
    derive_bucket_from_score,
    compute_derived_score,
)


def make_signals(*codes):
    return [{"code": c, "severity": "high", "score_adjustment": 0.1} for c in codes]


# ── fingerprint ───────────────────────────────────────────────

def test_fingerprint_is_stable_for_same_inputs():
    signals = make_signals("recent_registration", "live_http_surface")
    fp1 = compute_state_fingerprint(
        derived_risk="high",
        derived_bucket="defensive_gap",
        signal_codes=["recent_registration", "live_http_surface"],
        latest_tool_results={},
    )
    fp2 = compute_state_fingerprint(
        derived_risk="high",
        derived_bucket="defensive_gap",
        signal_codes=["live_http_surface", "recent_registration"],  # different order
        latest_tool_results={},
    )
    assert fp1 == fp2, "fingerprint must be order-independent"


def test_fingerprint_changes_when_threat_intel_added():
    base = compute_state_fingerprint("high", "defensive_gap", [], {})
    with_hit = compute_state_fingerprint("high", "defensive_gap", ["safe_browsing_hit"], {})
    assert base != with_hit


def test_fingerprint_changes_when_risk_changes():
    fp_medium = compute_state_fingerprint("medium", "watchlist", [], {})
    fp_high = compute_state_fingerprint("high", "defensive_gap", [], {})
    assert fp_medium != fp_high


# ── bucket derivation ─────────────────────────────────────────

def test_bucket_immediate_at_080():
    assert derive_bucket_from_score(0.80) == "immediate_attention"

def test_bucket_immediate_above_080():
    assert derive_bucket_from_score(0.95) == "immediate_attention"

def test_bucket_defensive_at_048():
    assert derive_bucket_from_score(0.48) == "defensive_gap"

def test_bucket_watchlist_below_048():
    assert derive_bucket_from_score(0.47) == "watchlist"


# ── derived score ─────────────────────────────────────────────

def test_derived_score_adds_signal_adjustments():
    signals = [
        {"code": "recent_registration", "score_adjustment": 0.18},
        {"code": "live_http_surface", "score_adjustment": 0.05},
    ]
    # domain_age_days=10 is > 7, so no temporal bonus (+0.05 only applies for <=7 days)
    score = compute_derived_score(base_lexical_score=0.50, signals=signals, domain_age_days=10)
    assert abs(score - 0.73) < 0.001  # 0.50 + 0.18 + 0.05 = 0.73


def test_derived_score_clamped_to_1():
    signals = [{"code": "x", "score_adjustment": 0.99}]
    score = compute_derived_score(base_lexical_score=0.90, signals=signals, domain_age_days=5)
    assert score == 1.0


def test_derived_score_temporal_bonus_recent():
    # domain age <= 7 days gets +0.05 on top
    score = compute_derived_score(base_lexical_score=0.50, signals=[], domain_age_days=5)
    assert abs(score - 0.55) < 0.001


def test_derived_score_temporal_penalty_old():
    # domain age > 1 year without signals gets -0.10
    score = compute_derived_score(base_lexical_score=0.50, signals=[], domain_age_days=400)
    assert abs(score - 0.40) < 0.001
```

- [ ] **Step 2: Run failing tests**

```bash
docker exec -it $(docker ps --filter name=obs_backend -q) \
  python -m pytest tests/test_state_aggregator.py -v 2>&1 | head -20
```

Expected: `ImportError`

- [ ] **Step 3: Implement `state_aggregator.py`**

```python
# backend/app/services/state_aggregator.py
"""
State aggregator — derives current match state from monitoring events.

This module contains pure functions (no DB access) used by workers and repositories
to recalculate derived state after each new event.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.monitoring_event_repository import MonitoringEventRepository
from app.repositories.match_state_snapshot_repository import MatchStateSnapshotRepository
from app.repositories.brand_domain_health_repository import BrandDomainHealthRepository


# ── Pure functions (no DB) ────────────────────────────────────

def compute_state_fingerprint(
    derived_risk: str,
    derived_bucket: str,
    signal_codes: list[str],
    latest_tool_results: dict,  # {tool_name: result_data}
) -> str:
    """
    SHA-256 of the properties that, when changed, require LLM reassessment.
    Signal codes are sorted for order-independence.
    """
    THREAT_INTEL_CODES = {
        "safe_browsing_hit",
        "phishtank_verified_phish",
        "phishtank_in_database",
        "urlhaus_malware_listed",
    }
    SPOOFING_CODES = {"high_spoofing_risk", "elevated_spoofing_risk"}

    payload = {
        "derived_risk": derived_risk,
        "derived_bucket": derived_bucket,
        "signal_codes": sorted(signal_codes),
        "dns_resolves": any(c in signal_codes for c in ("live_http_surface", "restricted_live_surface")),
        "ssl_revoked": "certificate_revoked" in signal_codes,
        "threat_intel_hits": sorted(c for c in signal_codes if c in THREAT_INTEL_CODES),
        "spoofing_risk": next((c for c in signal_codes if c in SPOOFING_CODES), None),
        "suspicious_page_risk": latest_tool_results.get("suspicious_page", {}).get("risk_level"),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()


def derive_bucket_from_score(derived_score: float) -> str:
    """
    Map derived score to attention bucket.
    Special signals (clone_detected, credential+impersonation) are handled separately
    by callers before invoking this function.
    """
    if derived_score >= 0.80:
        return "immediate_attention"
    if derived_score >= 0.48:
        return "defensive_gap"
    return "watchlist"


def derive_risk_from_signals(signal_codes: list[str]) -> str:
    """Derive risk level from the highest-severity signal present."""
    CRITICAL_SIGNALS = {
        "credential_collection_surface", "safe_browsing_hit",
        "phishtank_verified_phish", "certificate_revoked",
    }
    HIGH_SIGNALS = {
        "recent_registration", "mail_only_infrastructure",
        "brand_impersonation_content", "phishtank_in_database",
        "urlhaus_malware_listed", "high_spoofing_risk",
    }
    MEDIUM_SIGNALS = {
        "fresh_registration", "live_http_surface", "unusual_hosting_country",
        "shielded_hosting_provider", "elevated_spoofing_risk",
    }
    if any(s in signal_codes for s in CRITICAL_SIGNALS):
        return "critical"
    if any(s in signal_codes for s in HIGH_SIGNALS):
        return "high"
    if any(s in signal_codes for s in MEDIUM_SIGNALS):
        return "medium"
    return "low"


def compute_derived_score(
    *,
    base_lexical_score: float,
    signals: list[dict],
    domain_age_days: int | None,
) -> float:
    """
    Calculate derived_score = base + signal adjustments + temporal bonus.
    Result is clamped to [0, 1].
    """
    total = base_lexical_score + sum(
        s.get("score_adjustment", 0) for s in signals
    )

    # Temporal bonus/penalty
    if domain_age_days is not None:
        if domain_age_days <= 7:
            total += 0.05
        elif domain_age_days > 1095:  # > 3 years
            total -= 0.15
        elif domain_age_days > 365:   # > 1 year, no negative signals
            has_negative = any(
                s.get("score_adjustment", 0) < 0 for s in signals
            )
            if not has_negative:
                total -= 0.10

    return max(0.0, min(1.0, total))


# ── DB-aware aggregation ──────────────────────────────────────

class StateAggregator:
    """
    Recalculates match_state_snapshot and brand_domain_health
    after new monitoring_event records are created.

    Workers create events, then call aggregator methods to update
    the materialized state. API reads the materialized state.
    """

    def __init__(self, db: Session) -> None:
        self.db = db
        self.event_repo = MonitoringEventRepository(db)
        self.snapshot_repo = MatchStateSnapshotRepository(db)
        self.health_repo = BrandDomainHealthRepository(db)

    def recalculate_match_snapshot(
        self,
        *,
        match_id: UUID,
        brand_id: UUID,
        organization_id: UUID,
        base_lexical_score: float,
        domain_age_days: int | None = None,
    ) -> None:
        """
        Read all recent events for this match, aggregate signals,
        compute derived state, and upsert match_state_snapshot.
        """
        events = self.event_repo.list_for_match(match_id=match_id, limit=200)

        # Collect all signals from all events (deduplicate by code, keep latest)
        signals_by_code: dict[str, dict] = {}
        latest_tool_results: dict[str, dict] = {}

        for evt in reversed(events):  # oldest first so latest wins
            if evt.signals:
                for sig in evt.signals:
                    signals_by_code[sig["code"]] = {
                        **sig,
                        "source_tool": evt.tool_name,
                        "source_event_id": str(evt.id),
                    }
            if evt.tool_name and evt.result_data:
                latest_tool_results[evt.tool_name] = evt.result_data

        active_signals = list(signals_by_code.values())
        signal_codes = list(signals_by_code.keys())

        # Derive score and classification
        derived_score = compute_derived_score(
            base_lexical_score=base_lexical_score,
            signals=active_signals,
            domain_age_days=domain_age_days,
        )

        # Force immediate_attention for specific signal combos
        if "clone_detected" in signal_codes:
            derived_score = max(derived_score, 0.95)
        if "credential_collection_surface" in signal_codes and "brand_impersonation_content" in signal_codes:
            derived_score = max(derived_score, 0.85)

        derived_bucket = derive_bucket_from_score(derived_score)
        derived_risk = derive_risk_from_signals(signal_codes)

        state_fingerprint = compute_state_fingerprint(
            derived_risk=derived_risk,
            derived_bucket=derived_bucket,
            signal_codes=signal_codes,
            latest_tool_results=latest_tool_results,
        )

        events_hash = hashlib.sha256(
            json.dumps(sorted(str(e.id) for e in events)).encode()
        ).hexdigest()

        self.snapshot_repo.upsert(
            match_id=match_id,
            brand_id=brand_id,
            organization_id=organization_id,
            derived_score=derived_score,
            derived_bucket=derived_bucket,
            derived_risk=derived_risk,
            active_signals=active_signals,
            signal_codes=signal_codes,
            state_fingerprint=state_fingerprint,
            last_derived_at=datetime.now(timezone.utc),
            events_hash=events_hash,
        )
        self.db.commit()

    def recalculate_domain_health(
        self,
        *,
        brand_domain_id: UUID,
        brand_id: UUID,
        organization_id: UUID,
    ) -> None:
        """
        Read latest health check events for this domain, derive overall_status,
        and upsert brand_domain_health.
        """
        HEALTH_TOOLS = [
            "dns_lookup", "ssl_check", "http_headers", "email_security",
            "subdomain_takeover", "blacklist_check", "safe_browsing",
            "urlhaus", "phishtank", "suspicious_page",
        ]

        latest_results: dict[str, dict] = {}
        latest_event_ids: list[str] = []

        for tool in HEALTH_TOOLS:
            evt = self.event_repo.fetch_latest_for_domain_tool(
                brand_domain_id=brand_domain_id,
                tool_name=tool,
            )
            if evt:
                latest_results[tool] = evt.result_data or {}
                latest_event_ids.append(str(evt.id))

        # Derive boolean health fields from tool results
        health_fields = _derive_health_fields(latest_results)
        overall_status = _derive_overall_status(health_fields)

        import hashlib as _hl, json as _json
        state_fingerprint = _hl.sha256(
            _json.dumps(health_fields, sort_keys=True).encode()
        ).hexdigest()

        self.health_repo.upsert(
            brand_domain_id=brand_domain_id,
            brand_id=brand_id,
            organization_id=organization_id,
            overall_status=overall_status,
            last_check_at=datetime.now(timezone.utc),
            last_event_ids=latest_event_ids,
            state_fingerprint=state_fingerprint,
            **health_fields,
        )
        self.db.commit()


def _derive_health_fields(results: dict[str, dict]) -> dict:
    """Extract boolean health indicators from raw tool result data."""
    fields: dict = {}

    # DNS
    dns = results.get("dns_lookup", {})
    records = dns.get("records", [])
    fields["dns_ok"] = len(records) > 0 if dns else None

    # SSL
    ssl = results.get("ssl_check", {})
    if ssl:
        cert = ssl.get("certificate", {})
        days = cert.get("days_remaining")
        ocsp = cert.get("ocsp_status", "unknown")
        fields["ssl_ok"] = ssl.get("is_valid", False) and ocsp != "revoked"
        fields["ssl_days_remaining"] = days
    else:
        fields["ssl_ok"] = None
        fields["ssl_days_remaining"] = None

    # Email security
    email = results.get("email_security", {})
    if email:
        fields["email_security_ok"] = email.get("spoofing_risk") in ("none", "low")
        fields["spoofing_risk"] = email.get("spoofing_risk")
    else:
        fields["email_security_ok"] = None
        fields["spoofing_risk"] = None

    # HTTP headers
    headers = results.get("http_headers", {})
    if headers:
        sec = headers.get("security_headers", [])
        present = sum(1 for h in sec if h.get("present"))
        total = len(sec)
        if total == 0:
            fields["headers_score"] = None
        elif present == total:
            fields["headers_score"] = "good"
        elif present >= total // 2:
            fields["headers_score"] = "partial"
        else:
            fields["headers_score"] = "poor"
    else:
        fields["headers_score"] = None

    # Subdomain takeover
    takeover = results.get("subdomain_takeover", {})
    if takeover:
        vulnerable = takeover.get("vulnerable_subdomains", [])
        fields["takeover_risk"] = len(vulnerable) > 0
    else:
        fields["takeover_risk"] = None

    # Reputation
    bl = results.get("blacklist_check", {})
    fields["blacklisted"] = bool(bl.get("listed_count", 0) > 0) if bl else None

    sb = results.get("safe_browsing", {})
    fields["safe_browsing_hit"] = bool(sb.get("threats")) if sb else None

    uh = results.get("urlhaus", {})
    fields["urlhaus_hit"] = bool(uh.get("listed")) if uh else None

    pt = results.get("phishtank", {})
    fields["phishtank_hit"] = bool(pt.get("in_database")) if pt else None

    sp = results.get("suspicious_page", {})
    if sp:
        risk = sp.get("risk_level", "safe")
        fields["suspicious_content"] = risk not in ("safe", "inconclusive", "protected")
    else:
        fields["suspicious_content"] = None

    return fields


def _derive_overall_status(fields: dict) -> str:
    """Derive overall health status from boolean fields."""
    # Critical: any reputation hit or revoked SSL
    if any([
        fields.get("safe_browsing_hit"),
        fields.get("urlhaus_hit"),
        fields.get("phishtank_hit"),
        fields.get("blacklisted"),
        fields.get("suspicious_content"),
        fields.get("ssl_ok") is False,
    ]):
        return "critical"

    # Warning: email security issues, takeover risk, SSL expiring soon
    days_remaining = fields.get("ssl_days_remaining")
    if any([
        fields.get("email_security_ok") is False,
        fields.get("takeover_risk"),
        fields.get("headers_score") == "poor",
        days_remaining is not None and days_remaining < 30,
    ]):
        return "warning"

    # Unknown: not checked yet
    if all(v is None for v in fields.values()):
        return "unknown"

    return "healthy"
```

- [ ] **Step 4: Run tests**

```bash
docker exec -it $(docker ps --filter name=obs_backend -q) \
  python -m pytest tests/test_state_aggregator.py -v
```

Expected: `9 passed` (adjust count to actual)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/state_aggregator.py \
        backend/tests/test_state_aggregator.py
git commit -m "feat(monitoring): add StateAggregator with fingerprint and score derivation"
```

---

## Task 7: Integration Smoke Test

**Files:**
- Test: `backend/tests/test_monitoring_foundation_integration.py`

- [ ] **Step 1: Verify `db_session` fixture exists in `conftest.py`**

Before writing the integration test, check that a `db_session` fixture is defined:

```bash
grep -r "def db_session" backend/tests/conftest.py 2>/dev/null || echo "NOT FOUND"
```

If not found, add this minimal fixture to `backend/tests/conftest.py`:

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings  # adjust to actual config import

@pytest.fixture
def db_session():
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
        session.rollback()
    finally:
        session.close()
```

- [ ] **Step 2: Write integration test that exercises the full write path**

```python
# backend/tests/test_monitoring_foundation_integration.py
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

    brand_id = uuid.uuid4()
    org_id = uuid.uuid4()

    repo = MonitoringCycleRepository(db_session)
    svc = MonitoringCycleService(db_session, cycle_repo=repo)

    cycle, created = repo.get_or_create_today(brand_id=brand_id, organization_id=org_id)
    assert created is True
    assert cycle.health_status == "pending"

    svc.begin_stage(cycle.id, stage="health")
    db_session.refresh(cycle)
    assert cycle.health_status == "running"
    assert cycle.health_started_at is not None

    svc.finish_stage(cycle.id, stage="health", success=True)
    db_session.refresh(cycle)
    assert cycle.health_status == "completed"
    assert cycle.health_finished_at is not None

    # Second call returns existing cycle
    cycle2, created2 = repo.get_or_create_today(brand_id=brand_id, organization_id=org_id)
    assert created2 is False
    assert cycle2.id == cycle.id
```

- [ ] **Step 3: Run smoke test (requires running stack)**

```bash
docker exec -it $(docker ps --filter name=obs_backend -q) \
  python -m pytest tests/test_monitoring_foundation_integration.py -v -m integration
```

Expected: `1 passed` (or skip if no DB fixture configured — the unit tests above provide sufficient coverage for Plan 1)

- [ ] **Step 4: Final commit for Plan 1**

```bash
git add backend/tests/conftest.py backend/tests/test_monitoring_foundation_integration.py
git commit -m "test(monitoring): add foundation integration smoke test"
```

---

## Final Verification

- [ ] All unit tests pass:

```bash
docker exec -it $(docker ps --filter name=obs_backend -q) \
  python -m pytest tests/test_monitoring_event_repository.py \
                   tests/test_monitoring_cycle_service.py \
                   tests/test_state_aggregator.py -v
```

- [ ] Existing tests still pass (no regressions):

```bash
docker exec -it $(docker ps --filter name=obs_backend -q) \
  python -m pytest tests/ -v --ignore=tests/test_monitoring_foundation_integration.py
```

- [ ] Migration applies cleanly and downgrades cleanly:

```bash
docker exec -it $(docker ps --filter name=obs_backend -q) \
  alembic downgrade 024_ingestion_tld_priority && \
  alembic upgrade head
```

---

## What's Next

**Plan 2 — Workers** (`2026-04-11-monitoring-workers.md`):
- `health_worker.py` — runs 10 tools against official domains, writes events, calls `StateAggregator.recalculate_domain_health()`
- `scan_worker.py` — refactored from `similarity_worker.py`, writes scan events, computes `enrichment_budget_rank`
- `enrichment_worker.py` — extracts enrichment from scan, applies budget + auto-dismiss rules
- `assessment_worker.py` — polls `needs_llm_assessment()`, calls LLM, writes assessment events

**Plan 3 — API** (`2026-04-11-monitoring-api.md`):
- New `GET /v1/brands/{id}/health`, `GET /v1/brands/{id}/cycles`, `GET /v1/matches/{id}/events`
- Modify `GET /v1/brands` (add monitoring_summary), `GET /v1/brands/{id}/matches` (read from snapshot)

**Plan 4 — Frontend** (`2026-04-11-monitoring-frontend.md`):
- Brand list (cards), brand detail (sections), match drawer (5 evidence cards)
