# Ingestion Config & TLD Control — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow operators to control ingestion cron schedules and per-TLD enable/disable for CZDS, CertStream, and OpenINTEL sources from a frontend config page, with per-TLD metrics (duration, domains inserted, last success, last 10 run statuses visualized as sparkbars).

**Architecture:** Two new DB tables (`ingestion_source_config`, `ingestion_tld_policy`) store cron and TLD enable state; new API router exposes CRUD for both; workers read cron from DB at each cycle start and fall back to env vars; frontend gains a `[source]` dynamic route with cron card + TLD metrics table.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy / Alembic / Next.js App Router / TypeScript / shadcn/ui

**Spec:** `docs/superpowers/specs/2026-04-10-ingestion-config-tld-control-design.md`

---

## File Map

### Backend — New files
| File | Purpose |
|------|---------|
| `backend/app/models/ingestion_source_config.py` | SQLAlchemy model for cron-per-source table |
| `backend/app/models/ingestion_tld_policy.py` | SQLAlchemy model for generic TLD enable/disable table |
| `backend/alembic/versions/020_ingestion_config_tld_policy.py` | Migration: create both tables + seed crons from env defaults |
| `backend/app/repositories/ingestion_config_repository.py` | CRUD for `ingestion_source_config` and `ingestion_tld_policy` |
| `backend/app/services/ingestion_config_service.py` | Cron expression validation |
| `backend/app/schemas/ingestion_config.py` | Pydantic request/response schemas |
| `backend/app/api/v1/routers/ingestion_config.py` | API router: config + tld-policy endpoints |

### Backend — Modified files
| File | Change |
|------|--------|
| `backend/app/main.py` | Register new router |
| `backend/app/worker/openintel_ingestor.py` | Read enabled TLDs from DB; reload cron from DB each cycle |
| `backend/app/worker/czds_ingestor.py` | Reload cron from DB each cycle |
| `backend/app/worker/ct_ingestor.py` | TLD filter on certstream domains; reload crtsh cron from DB |

### Frontend — New files
| File | Purpose |
|------|---------|
| `frontend/app/admin/ingestion/[source]/page.tsx` | Dynamic route for per-source config page |
| `frontend/components/ingestion/sparkbar.tsx` | 10-bar sparkline: color=status, height∝duration |
| `frontend/components/ingestion/cron-config-card.tsx` | Cron input + validation + save |
| `frontend/components/ingestion/tld-metrics-table.tsx` | Table: toggle, TLD, duration, inserted, last OK, sparkbar |
| `frontend/components/ingestion/source-config-page.tsx` | Composes cron card + TLD table for a given source |

### Frontend — Modified files
| File | Change |
|------|--------|
| `frontend/lib/types.ts` | Add `IngestionSourceConfig`, `IngestionTldPolicy`, `TldMetricsRow` types |
| `frontend/lib/api.ts` | Add API calls for config and tld-policy endpoints |
| `frontend/hooks/use-ingestion-data.ts` | Add `updateCron`, `patchTldPolicy`, `bulkSetTldPolicy` actions |
| `frontend/app/admin/ingestion/page.tsx` | Add 3 source summary cards above existing tabs |

---

## Task 1: DB Models

**Files:**
- Create: `backend/app/models/ingestion_source_config.py`
- Create: `backend/app/models/ingestion_tld_policy.py`

- [ ] **Step 1: Create `ingestion_source_config` model**

```python
# backend/app/models/ingestion_source_config.py
"""IngestionSourceConfig — persisted cron schedule per ingestion source."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String

from app.models.base import Base


class IngestionSourceConfig(Base):
    __tablename__ = "ingestion_source_config"

    source = Column(String(32), primary_key=True)  # "czds" | "certstream" | "openintel"
    cron_expression = Column(String(64), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
```

- [ ] **Step 2: Create `ingestion_tld_policy` model**

```python
# backend/app/models/ingestion_tld_policy.py
"""IngestionTldPolicy — generic per-source TLD enable/disable (OpenINTEL, CertStream)."""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String

from app.models.base import Base


class IngestionTldPolicy(Base):
    __tablename__ = "ingestion_tld_policy"

    source = Column(String(32), primary_key=True)
    tld = Column(String(64), primary_key=True)
    is_enabled = Column(Boolean, nullable=False, default=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/ingestion_source_config.py backend/app/models/ingestion_tld_policy.py
git commit -m "feat(models): add ingestion_source_config and ingestion_tld_policy models"
```

---

## Task 2: Alembic Migration

**Files:**
- Create: `backend/alembic/versions/020_ingestion_config_tld_policy.py`

Migration creates both tables and seeds `ingestion_source_config` with the current env var defaults. The `down_revision` is `019_drop_ct_bulk`.

- [ ] **Step 1: Create migration file**

```python
# backend/alembic/versions/020_ingestion_config_tld_policy.py
"""Add ingestion_source_config and ingestion_tld_policy tables.

Revision ID: 020_ingestion_config_tld_policy
Revises: 019_drop_ct_bulk
Create Date: 2026-04-10 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "020_ingestion_config_tld_policy"
down_revision = "019_drop_ct_bulk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_source_config",
        sa.Column("source", sa.String(32), primary_key=True),
        sa.Column("cron_expression", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "ingestion_tld_policy",
        sa.Column("source", sa.String(32), primary_key=True),
        sa.Column("tld", sa.String(64), primary_key=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Seed default cron schedules from hardcoded defaults
    # (mirrors env var defaults so workers always find a row)
    op.execute(
        sa.text(
            """
            INSERT INTO ingestion_source_config (source, cron_expression)
            VALUES
                ('czds',        '0 7 * * *'),
                ('certstream',  '0 5 * * *'),
                ('openintel',   '0 2 * * *')
            ON CONFLICT (source) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_table("ingestion_tld_policy")
    op.drop_table("ingestion_source_config")
```

- [ ] **Step 2: Apply migration inside the backend container**

```bash
docker exec -it $(docker ps --filter name=obs_backend -q | head -1) \
  alembic upgrade 020_ingestion_config_tld_policy
```

Expected: `Running upgrade 019_drop_ct_bulk -> 020_ingestion_config_tld_policy, Add ingestion_source_config and ingestion_tld_policy tables`

- [ ] **Step 3: Verify tables exist**

```bash
docker exec -it $(docker ps --filter name=obs_postgres -q | head -1) \
  psql -U obs -d obs -c "\dt ingestion_*"
```

Expected: `ingestion_checkpoint`, `ingestion_run`, `ingestion_source_config`, `ingestion_tld_policy`

- [ ] **Step 4: Verify seed data**

```bash
docker exec -it $(docker ps --filter name=obs_postgres -q | head -1) \
  psql -U obs -d obs -c "SELECT * FROM ingestion_source_config;"
```

Expected: 3 rows (czds, certstream, openintel) with their default cron strings.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/020_ingestion_config_tld_policy.py
git commit -m "feat(migration): 020 — ingestion_source_config + ingestion_tld_policy tables"
```

---

## Task 3: Repository

**Files:**
- Create: `backend/app/repositories/ingestion_config_repository.py`

- [ ] **Step 1: Write repository**

```python
# backend/app/repositories/ingestion_config_repository.py
"""Repository for ingestion_source_config and ingestion_tld_policy tables."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.ingestion_source_config import IngestionSourceConfig
from app.models.ingestion_tld_policy import IngestionTldPolicy


class IngestionConfigRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Source config (cron) ─────────────────────────────────

    def get_config(self, source: str) -> IngestionSourceConfig | None:
        return self.db.get(IngestionSourceConfig, source)

    def list_configs(self) -> list[IngestionSourceConfig]:
        return (
            self.db.query(IngestionSourceConfig)
            .order_by(IngestionSourceConfig.source)
            .all()
        )

    def get_cron(self, source: str) -> str | None:
        """Return cron expression for source, or None if not found."""
        cfg = self.get_config(source)
        return cfg.cron_expression if cfg else None

    def upsert_cron(self, source: str, cron_expression: str) -> IngestionSourceConfig:
        now = datetime.now(timezone.utc)
        cfg = self.get_config(source)
        if cfg is None:
            cfg = IngestionSourceConfig(
                source=source,
                cron_expression=cron_expression,
                created_at=now,
                updated_at=now,
            )
            self.db.add(cfg)
        else:
            cfg.cron_expression = cron_expression
            cfg.updated_at = now
        self.db.flush()
        return cfg

    # ── TLD policy ───────────────────────────────────────────

    def list_tld_policies(self, source: str) -> list[IngestionTldPolicy]:
        return (
            self.db.query(IngestionTldPolicy)
            .filter(IngestionTldPolicy.source == source)
            .order_by(IngestionTldPolicy.tld)
            .all()
        )

    def get_tld_policy(self, source: str, tld: str) -> IngestionTldPolicy | None:
        return self.db.get(IngestionTldPolicy, (source, tld))

    def is_tld_enabled(self, source: str, tld: str) -> bool:
        """Return True if TLD is enabled (also True if no row exists — default-allow)."""
        policy = self.get_tld_policy(source, tld)
        return policy.is_enabled if policy is not None else True

    def ensure_tld(self, source: str, tld: str, *, is_enabled: bool = True) -> IngestionTldPolicy:
        """Get or create a TLD policy row."""
        policy = self.get_tld_policy(source, tld)
        if policy is None:
            policy = IngestionTldPolicy(
                source=source,
                tld=tld,
                is_enabled=is_enabled,
                updated_at=datetime.now(timezone.utc),
            )
            self.db.add(policy)
            self.db.flush()
        return policy

    def patch_tld(self, source: str, tld: str, *, is_enabled: bool) -> IngestionTldPolicy:
        policy = self.ensure_tld(source, tld)
        policy.is_enabled = is_enabled
        policy.updated_at = datetime.now(timezone.utc)
        self.db.flush()
        return policy

    def bulk_upsert_tlds(
        self,
        source: str,
        tld_states: list[dict],  # [{"tld": str, "is_enabled": bool}]
    ) -> list[IngestionTldPolicy]:
        """Upsert is_enabled for the supplied TLDs. Rows not in list are unchanged."""
        now = datetime.now(timezone.utc)
        for item in tld_states:
            policy = self.get_tld_policy(source, item["tld"])
            if policy is None:
                policy = IngestionTldPolicy(
                    source=source,
                    tld=item["tld"],
                    is_enabled=item["is_enabled"],
                    updated_at=now,
                )
                self.db.add(policy)
            else:
                policy.is_enabled = item["is_enabled"]
                policy.updated_at = now
        self.db.flush()
        return self.list_tld_policies(source)

    def list_enabled_tlds(self, source: str) -> list[str]:
        """Return sorted list of enabled TLD names for a source."""
        return [
            p.tld
            for p in self.list_tld_policies(source)
            if p.is_enabled
        ]
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/repositories/ingestion_config_repository.py
git commit -m "feat(repository): IngestionConfigRepository for cron and TLD policy"
```

---

## Task 4: Service (cron validation)

**Files:**
- Create: `backend/app/services/ingestion_config_service.py`

- [ ] **Step 1: Write service**

```python
# backend/app/services/ingestion_config_service.py
"""Business logic for ingestion source configuration."""

from __future__ import annotations

import re

_CRON_PART_RANGES = [
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day", 1, 31),
    ("month", 1, 12),
    ("day_of_week", 0, 6),
]

_VALID_SOURCES = {"czds", "certstream", "openintel"}


class InvalidCronError(ValueError):
    pass


class InvalidSourceError(ValueError):
    pass


def validate_cron_expression(expr: str) -> str:
    """
    Validate a 5-part cron expression (minute hour day month dow).
    Returns the cleaned expression or raises InvalidCronError.
    """
    parts = expr.strip().split()
    if len(parts) != 5:
        raise InvalidCronError(
            f"Cron must have exactly 5 parts (got {len(parts)}): '{expr}'"
        )

    for part, (name, lo, hi) in zip(parts, _CRON_PART_RANGES):
        if part == "*":
            continue
        # Allow */n, ranges (1-5), and lists (1,3,5)
        if not re.fullmatch(r"[\d,\-\*/]+", part):
            raise InvalidCronError(f"Invalid cron {name}: '{part}'")
        # Validate plain integers are in range
        for token in re.split(r"[,\-/]", part):
            if token and token.isdigit():
                val = int(token)
                if not (lo <= val <= hi):
                    raise InvalidCronError(
                        f"Cron {name} value {val} out of range [{lo},{hi}]"
                    )

    return " ".join(parts)


def validate_source(source: str) -> str:
    if source not in _VALID_SOURCES:
        raise InvalidSourceError(
            f"Unknown source '{source}'. Valid: {sorted(_VALID_SOURCES)}"
        )
    return source
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/ingestion_config_service.py
git commit -m "feat(service): cron validation for ingestion config"
```

---

## Task 5: API Schemas

**Files:**
- Create: `backend/app/schemas/ingestion_config.py`

- [ ] **Step 1: Write schemas**

```python
# backend/app/schemas/ingestion_config.py
"""Pydantic schemas for ingestion config and TLD policy endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator

from app.services.ingestion_config_service import InvalidCronError, validate_cron_expression


# ── Requests ─────────────────────────────────────────────────

class CronUpdateRequest(BaseModel):
    cron_expression: str

    @field_validator("cron_expression")
    @classmethod
    def validate_cron(cls, v: str) -> str:
        try:
            return validate_cron_expression(v)
        except InvalidCronError as exc:
            raise ValueError(str(exc)) from exc


class TldPolicyPatchRequest(BaseModel):
    is_enabled: bool


class TldPolicyBulkRequest(BaseModel):
    tlds: list[TldPolicyBulkItem]


class TldPolicyBulkItem(BaseModel):
    tld: str
    is_enabled: bool


# ── Responses ─────────────────────────────────────────────────

class SourceConfigResponse(BaseModel):
    source: str
    cron_expression: str
    updated_at: datetime

    model_config = {"from_attributes": True}


class TldPolicyResponse(BaseModel):
    source: str
    tld: str
    is_enabled: bool
    updated_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/ingestion_config.py
git commit -m "feat(schemas): ingestion config + TLD policy request/response schemas"
```

---

## Task 6: API Router + Register

**Files:**
- Create: `backend/app/api/v1/routers/ingestion_config.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write router**

```python
# backend/app/api/v1/routers/ingestion_config.py
"""Ingestion config API — cron management and generic TLD policy."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_admin
from app.infra.db.session import get_db
from app.repositories.ingestion_config_repository import IngestionConfigRepository
from app.schemas.ingestion_config import (
    CronUpdateRequest,
    SourceConfigResponse,
    TldPolicyBulkRequest,
    TldPolicyPatchRequest,
    TldPolicyResponse,
)
from app.services.ingestion_config_service import InvalidSourceError, validate_source

router = APIRouter(
    prefix="/v1/ingestion",
    tags=["Ingestion Config"],
    dependencies=[Depends(get_current_admin)],
)

_SOURCES = ["czds", "certstream", "openintel"]


@router.get("/config", response_model=list[SourceConfigResponse])
def list_configs(db: Session = Depends(get_db)):
    """List cron config for all sources."""
    repo = IngestionConfigRepository(db)
    return repo.list_configs()


@router.get("/config/{source}", response_model=SourceConfigResponse)
def get_config(source: str, db: Session = Depends(get_db)):
    """Get cron config for a single source."""
    _validate_source_or_404(source)
    repo = IngestionConfigRepository(db)
    cfg = repo.get_config(source)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"No config found for source '{source}'")
    return cfg


@router.put("/config/{source}", response_model=SourceConfigResponse)
def update_config(source: str, body: CronUpdateRequest, db: Session = Depends(get_db)):
    """Update (upsert) cron expression for a source."""
    _validate_source_or_404(source)
    repo = IngestionConfigRepository(db)
    cfg = repo.upsert_cron(source, body.cron_expression)
    db.commit()
    return cfg


@router.get("/tld-policy/{source}", response_model=list[TldPolicyResponse])
def list_tld_policies(source: str, db: Session = Depends(get_db)):
    """List all TLD policies for a source."""
    _validate_source_or_404(source)
    repo = IngestionConfigRepository(db)
    return repo.list_tld_policies(source)


@router.patch(
    "/tld-policy/{source}/{tld}",
    response_model=TldPolicyResponse,
)
def patch_tld_policy(
    source: str,
    tld: str,
    body: TldPolicyPatchRequest,
    db: Session = Depends(get_db),
):
    """Enable or disable a single TLD for a source."""
    _validate_source_or_404(source)
    repo = IngestionConfigRepository(db)
    policy = repo.patch_tld(source, tld.lower(), is_enabled=body.is_enabled)
    db.commit()
    return policy


@router.put(
    "/tld-policy/{source}",
    response_model=list[TldPolicyResponse],
)
def bulk_upsert_tld_policy(
    source: str,
    body: TldPolicyBulkRequest,
    db: Session = Depends(get_db),
):
    """Bulk upsert TLD policies. Rows not in the payload are unchanged."""
    _validate_source_or_404(source)
    repo = IngestionConfigRepository(db)
    policies = repo.bulk_upsert_tlds(
        source,
        [{"tld": item.tld.lower(), "is_enabled": item.is_enabled} for item in body.tlds],
    )
    db.commit()
    return policies


def _validate_source_or_404(source: str) -> None:
    try:
        validate_source(source)
    except InvalidSourceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
```

- [ ] **Step 2: Register router in `main.py`**

In `backend/app/main.py`, add import and `app.include_router(ingestion_config.router)`:

```python
# Add to imports at top:
from app.api.v1.routers import auth, czds_ingestion, ingestion, ingestion_config, monitored_brands, similarity, tools

# Add after ingestion router line:
app.include_router(ingestion_config.router)
```

- [ ] **Step 3: Verify endpoints are registered**

```bash
docker exec -it $(docker ps --filter name=obs_backend -q | head -1) \
  python -c "from app.main import app; routes = [r.path for r in app.routes]; print([r for r in routes if 'config' in r or 'tld-policy' in r])"
```

Expected output contains `/v1/ingestion/config`, `/v1/ingestion/tld-policy/{source}`, etc.

- [ ] **Step 4: Test endpoints via curl (inside container)**

```bash
# List configs
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/v1/ingestion/config | python -m json.tool

# Update cron
curl -s -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"cron_expression": "0 3 * * *"}' \
  http://localhost:8000/v1/ingestion/config/openintel

# Toggle a TLD
curl -s -X PATCH -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_enabled": false}' \
  http://localhost:8000/v1/ingestion/tld-policy/openintel/br
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/routers/ingestion_config.py backend/app/main.py
git commit -m "feat(api): ingestion config + TLD policy endpoints"
```

---

## Task 7: Worker — OpenINTEL TLD Filtering + Cron Reload

**Files:**
- Modify: `backend/app/worker/openintel_ingestor.py`

The `_get_enabled_tlds()` function currently reads from `settings.OPENINTEL_ENABLED_TLDS`. Replace it to read from DB first. The `main()` function sets up the scheduler once — modify it to reload cron from DB at the start of each `run_sync_cycle()`.

- [ ] **Step 1: Update `_get_enabled_tlds` and add cron reload in `openintel_ingestor.py`**

Replace `_get_enabled_tlds` and modify `run_sync_cycle` and `main`:

```python
# Replace the existing _get_enabled_tlds function:
def _get_enabled_tlds() -> list[str]:
    """Read enabled TLDs from DB; fall back to env if table is empty."""
    db = SessionLocal()
    try:
        from app.repositories.ingestion_config_repository import IngestionConfigRepository
        repo = IngestionConfigRepository(db)
        db_tlds = repo.list_enabled_tlds("openintel")
        if db_tlds:
            return db_tlds
    except Exception:
        logger.exception("Failed to read OpenINTEL TLDs from DB, falling back to env")
    finally:
        db.close()
    raw = settings.OPENINTEL_ENABLED_TLDS
    if not raw:
        return []
    return [t.strip().lower() for t in raw.split(",") if t.strip()]
```

Add a module-level variable to track the active cron and a helper to reload it:

```python
# Add at module level (after STOP_EVENT):
_active_cron: str = settings.OPENINTEL_SYNC_CRON
_scheduler_ref: BlockingScheduler | None = None


def _reload_cron_if_changed() -> None:
    """Check DB for updated cron; reschedule APScheduler job if it changed."""
    global _active_cron
    if _scheduler_ref is None or not _scheduler_ref.running:
        return
    db = SessionLocal()
    try:
        from app.repositories.ingestion_config_repository import IngestionConfigRepository
        repo = IngestionConfigRepository(db)
        db_cron = repo.get_cron("openintel") or settings.OPENINTEL_SYNC_CRON
        if db_cron != _active_cron:
            parts = db_cron.split()
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1], day=parts[2],
                month=parts[3], day_of_week=parts[4],
            )
            _scheduler_ref.reschedule_job("openintel_sync", trigger=trigger)
            logger.info("Cron updated: %s → %s", _active_cron, db_cron)
            _active_cron = db_cron
    except Exception:
        logger.exception("Failed to reload cron from DB")
    finally:
        db.close()
```

At the top of `run_sync_cycle()`, call `_reload_cron_if_changed()`:

```python
def run_sync_cycle() -> None:
    _reload_cron_if_changed()  # ← add this line first
    tlds = _get_enabled_tlds()
    ...
```

In `main()`, assign the scheduler to `_scheduler_ref` before starting:

```python
def main() -> None:
    global _scheduler_ref
    ...
    scheduler = BlockingScheduler()
    _scheduler_ref = scheduler  # ← add this line
    ...
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/worker/openintel_ingestor.py
git commit -m "feat(worker): openintel reads TLDs from DB + DB cron reload"
```

---

## Task 8: Worker — CZDS Cron Reload

**Files:**
- Modify: `backend/app/worker/czds_ingestor.py`

CZDS already reads TLDs from `czds_tld_policy` (no change needed there). Only add DB cron reload.

- [ ] **Step 1: Add cron reload to `czds_ingestor.py`**

Add these module-level globals and helper (after `STOP_EVENT`):

```python
_active_cron: str = settings.CZDS_SYNC_CRON
_scheduler_ref = None  # set to BlockingScheduler instance in main()


def _reload_cron_if_changed() -> None:
    """Check DB for updated cron; reschedule APScheduler job if it changed."""
    global _active_cron
    if _scheduler_ref is None or not _scheduler_ref.running:
        return
    db = SessionLocal()
    try:
        from app.repositories.ingestion_config_repository import IngestionConfigRepository
        repo = IngestionConfigRepository(db)
        db_cron = repo.get_cron("czds") or settings.CZDS_SYNC_CRON
        if db_cron != _active_cron:
            parts = db_cron.split()
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1], day=parts[2],
                month=parts[3], day_of_week=parts[4],
            )
            _scheduler_ref.reschedule_job("czds_sync", trigger=trigger)
            logger.info("CZDS cron updated: %s → %s", _active_cron, db_cron)
            _active_cron = db_cron
    except Exception:
        logger.exception("Failed to reload CZDS cron from DB")
    finally:
        db.close()
```

At the top of `run_sync_cycle()` add `_reload_cron_if_changed()`.

In `main()`, set `global _scheduler_ref` and assign `_scheduler_ref = scheduler` before `scheduler.start()`. Look up the existing APScheduler job ID for CZDS in `czds_ingestor.py` (search for `scheduler.add_job(`) — use that exact ID string in `reschedule_job`.

- [ ] **Step 2: Commit**

```bash
git add backend/app/worker/czds_ingestor.py
git commit -m "feat(worker): czds DB cron reload"
```

---

## Task 9: Worker — CertStream TLD Filtering + Cron Reload

**Files:**
- Modify: `backend/app/worker/ct_ingestor.py`

The `ct_ingestor` has two parts: CertStream (realtime stream, no cron) and crt.sh (BackgroundScheduler with `CT_CRTSH_SYNC_CRON`). We add TLD filtering to the CertStream flush path and DB cron reload to the crtsh scheduler.

- [ ] **Step 1: Add TLD filter helper to `ct_ingestor.py`**

Add this function after the module-level logger:

```python
def _is_tld_enabled_certstream(tld: str) -> bool:
    """
    Check if a TLD is enabled for CertStream ingestion.
    Auto-creates the row with is_enabled=True if it doesn't exist yet.
    Uses a short-lived DB session (called per-domain in flush batches).
    """
    db = SessionLocal()
    try:
        from app.repositories.ingestion_config_repository import IngestionConfigRepository
        repo = IngestionConfigRepository(db)
        policy = repo.get_tld_policy("certstream", tld)
        if policy is None:
            # First time we see this TLD — auto-register as enabled
            repo.ensure_tld("certstream", tld, is_enabled=True)
            db.commit()
            return True
        return policy.is_enabled
    except Exception:
        logger.exception("TLD policy check failed for tld=%s, allowing through", tld)
        return True
    finally:
        db.close()
```

- [ ] **Step 2: Apply TLD filter in `_flush_loop`**

In `_flush_loop`, before calling `ingest_ct_batch`, filter domains by TLD:

```python
# Inside _flush_loop, replace the ingest_ct_batch call block:
domains = buffer.drain()
if not domains:
    continue

# Filter to enabled TLDs only
def _extract_tld(domain: str) -> str:
    parts = domain.rsplit(".", 1)
    return parts[-1].lower() if len(parts) > 1 else domain.lower()

filtered = [d for d in domains if _is_tld_enabled_certstream(_extract_tld(d))]
if not filtered:
    logger.debug("All %d domains filtered out by TLD policy", len(domains))
    continue
domains = filtered
```

**Note:** For performance, move `_extract_tld` to module level (not inside the loop body).

- [ ] **Step 3: Add crtsh cron reload**

First, look up the existing crtsh job ID in `ct_ingestor.py` by searching for `scheduler.add_job(` — the `id=` argument is the string to use in `reschedule_job`.

Add module-level globals and helper (same pattern as Task 7/8, but using `BackgroundScheduler`):

```python
_active_crtsh_cron: str = settings.CT_CRTSH_SYNC_CRON
_crtsh_scheduler_ref = None  # set to BackgroundScheduler in main()


def _reload_crtsh_cron_if_changed() -> None:
    global _active_crtsh_cron
    if _crtsh_scheduler_ref is None or not _crtsh_scheduler_ref.running:
        return
    db = SessionLocal()
    try:
        from app.repositories.ingestion_config_repository import IngestionConfigRepository
        repo = IngestionConfigRepository(db)
        db_cron = repo.get_cron("certstream") or settings.CT_CRTSH_SYNC_CRON
        if db_cron != _active_crtsh_cron:
            parts = db_cron.split()
            trigger = CronTrigger(
                minute=parts[0], hour=parts[1], day=parts[2],
                month=parts[3], day_of_week=parts[4],
            )
            _crtsh_scheduler_ref.reschedule_job("<CRTSH_JOB_ID>", trigger=trigger)
            logger.info("crtsh cron updated: %s → %s", _active_crtsh_cron, db_cron)
            _active_crtsh_cron = db_cron
    except Exception:
        logger.exception("Failed to reload crtsh cron from DB")
    finally:
        db.close()
```

Replace `<CRTSH_JOB_ID>` with the actual job ID found in the file. Call `_reload_crtsh_cron_if_changed()` at the top of the crtsh sync function. Assign `_crtsh_scheduler_ref = scheduler` in `main()` before `scheduler.start()`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/worker/ct_ingestor.py
git commit -m "feat(worker): certstream TLD filtering + crtsh cron reload from DB"
```

---

## Task 10: Frontend — Types + API + Hook

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/lib/api.ts`
- Modify: `frontend/hooks/use-ingestion-data.ts`

- [ ] **Step 1: Add types to `frontend/lib/types.ts`**

Append at the end of the file:

```typescript
// ── Ingestion Config ──────────────────────────────────────

export interface IngestionSourceConfig {
  source: string
  cron_expression: string
  updated_at: string
}

export interface IngestionTldPolicy {
  source: string
  tld: string
  is_enabled: boolean
  updated_at: string
}

export interface TldMetricsRow {
  tld: string
  is_enabled: boolean
  last_duration_seconds: number | null   // finished_at - started_at of last run
  last_domains_inserted: number | null
  last_successful_run_at: string | null
  recent_runs: Array<{                   // last 10 runs, oldest→newest
    status: "success" | "failed" | "running"
    duration_seconds: number | null
    started_at: string
  }>
}
```

- [ ] **Step 2: Add API calls to `frontend/lib/api.ts`**

Find the `ingestionApi` export (or the `api` object) and add:

```typescript
// Add to ingestionApi or as standalone functions:

export async function getIngestionConfigs(): Promise<IngestionSourceConfig[]> {
  return apiFetch("/v1/ingestion/config")
}

export async function updateIngestionCron(
  source: string,
  cron_expression: string
): Promise<IngestionSourceConfig> {
  return apiFetch(`/v1/ingestion/config/${source}`, {
    method: "PUT",
    body: JSON.stringify({ cron_expression }),
  })
}

export async function getTldPolicies(source: string): Promise<IngestionTldPolicy[]> {
  return apiFetch(`/v1/ingestion/tld-policy/${source}`)
}

export async function patchTldPolicy(
  source: string,
  tld: string,
  is_enabled: boolean
): Promise<IngestionTldPolicy> {
  return apiFetch(`/v1/ingestion/tld-policy/${source}/${tld}`, {
    method: "PATCH",
    body: JSON.stringify({ is_enabled }),
  })
}

export async function bulkSetTldPolicies(
  source: string,
  tlds: Array<{ tld: string; is_enabled: boolean }>
): Promise<IngestionTldPolicy[]> {
  return apiFetch(`/v1/ingestion/tld-policy/${source}`, {
    method: "PUT",
    body: JSON.stringify({ tlds }),
  })
}
```

Look at how `apiFetch` or the existing API functions work in `api.ts` and follow the same auth header pattern.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/types.ts frontend/lib/api.ts
git commit -m "feat(frontend): types + API functions for ingestion config"
```

---

## Task 11: Frontend — Sparkbar Component

**Files:**
- Create: `frontend/components/ingestion/sparkbar.tsx`

- [ ] **Step 1: Create sparkbar**

```tsx
// frontend/components/ingestion/sparkbar.tsx
"use client"

interface SparkRun {
  status: "success" | "failed" | "running" | null
  duration_seconds: number | null
}

interface SparkbarProps {
  runs: SparkRun[]  // up to 10, oldest first
  maxRuns?: number
}

export function Sparkbar({ runs, maxRuns = 10 }: SparkbarProps) {
  // Pad to maxRuns with empty slots
  const slots: SparkRun[] = [
    ...Array(Math.max(0, maxRuns - runs.length)).fill({ status: null, duration_seconds: null }),
    ...runs.slice(-maxRuns),
  ]

  // Normalize heights: max duration = full height (20px), empty = 4px
  const maxDuration = Math.max(
    1,
    ...slots.map((s) => s.duration_seconds ?? 0)
  )
  const MIN_HEIGHT = 4
  const MAX_HEIGHT = 20

  return (
    <div className="flex gap-[2px] items-end h-5" title="últimas 10 ingestões (mais antiga → mais recente)">
      {slots.map((slot, i) => {
        const height =
          slot.duration_seconds != null
            ? MIN_HEIGHT + ((slot.duration_seconds / maxDuration) * (MAX_HEIGHT - MIN_HEIGHT))
            : MIN_HEIGHT

        const color =
          slot.status === "success"
            ? "bg-green-500"
            : slot.status === "failed"
            ? "bg-red-500"
            : slot.status === "running"
            ? "bg-blue-400 animate-pulse"
            : "bg-muted"

        const tooltip =
          slot.status != null
            ? `${slot.status} · ${slot.duration_seconds != null ? Math.round(slot.duration_seconds) + "s" : "?"}`
            : "sem dado"

        return (
          <div
            key={i}
            className={`w-[5px] rounded-sm ${color}`}
            style={{ height: `${Math.round(height)}px` }}
            title={tooltip}
          />
        )
      })}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/ingestion/sparkbar.tsx
git commit -m "feat(frontend): Sparkbar component for ingestion run history"
```

---

## Task 12: Frontend — Cron Config Card

**Files:**
- Create: `frontend/components/ingestion/cron-config-card.tsx`

- [ ] **Step 1: Create cron config card**

```tsx
// frontend/components/ingestion/cron-config-card.tsx
"use client"

import { useState } from "react"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"

interface CronConfigCardProps {
  source: string
  initialCron: string
  isContinuousStream?: boolean  // true for certstream realtime part
  onSave: (cron: string) => Promise<void>
}

function parseCronDescription(cron: string): string {
  const parts = cron.trim().split(/\s+/)
  if (parts.length !== 5) return cron
  const [min, hour] = parts
  if (min.match(/^\d+$/) && hour.match(/^\d+$/)) {
    return `Todo dia às ${hour.padStart(2, "0")}:${min.padStart(2, "0")} UTC`
  }
  return cron
}

function validateCron(cron: string): string | null {
  const parts = cron.trim().split(/\s+/)
  if (parts.length !== 5) return "Cron deve ter 5 partes (ex: 0 7 * * *)"
  return null
}

export function CronConfigCard({
  source,
  initialCron,
  isContinuousStream = false,
  onSave,
}: CronConfigCardProps) {
  const [cron, setCron] = useState(initialCron)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  async function handleSave() {
    const validationError = validateCron(cron)
    if (validationError) {
      setError(validationError)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await onSave(cron)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch {
      setError("Erro ao salvar. Tente novamente.")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Agendamento
        </CardTitle>
      </CardHeader>
      <CardContent>
        {isContinuousStream && (
          <p className="text-xs text-muted-foreground mb-3">
            Stream CertStream: contínuo (sempre ativo). Cron aplica ao batch crt.sh.
          </p>
        )}
        <div className="flex items-center gap-3">
          <Label className="text-sm text-muted-foreground whitespace-nowrap">
            Expressão cron
          </Label>
          <Input
            value={cron}
            onChange={(e) => {
              setCron(e.target.value)
              setError(null)
              setSaved(false)
            }}
            className="font-mono w-36 h-8 text-sm"
            placeholder="0 7 * * *"
          />
          <span className="text-xs text-muted-foreground">
            {validateCron(cron) ? "" : parseCronDescription(cron)}
          </span>
          <Button
            size="sm"
            variant="outline"
            onClick={handleSave}
            disabled={saving || cron === initialCron}
            className="ml-auto h-8"
          >
            {saving ? "Salvando…" : saved ? "Salvo ✓" : "Salvar"}
          </Button>
        </div>
        {error && <p className="text-xs text-destructive mt-2">{error}</p>}
      </CardContent>
    </Card>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/ingestion/cron-config-card.tsx
git commit -m "feat(frontend): CronConfigCard component"
```

---

## Task 13: Frontend — TLD Metrics Table

**Files:**
- Create: `frontend/components/ingestion/tld-metrics-table.tsx`

- [ ] **Step 1: Create TLD metrics table**

```tsx
// frontend/components/ingestion/tld-metrics-table.tsx
"use client"

import { useMemo, useState } from "react"
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table"
import { Switch } from "@/components/ui/switch"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Sparkbar } from "./sparkbar"
import type { TldMetricsRow } from "@/lib/types"

interface TldMetricsTableProps {
  rows: TldMetricsRow[]
  onToggle: (tld: string, enabled: boolean) => Promise<void>
  onEnableAll: () => void
  onDisableAll: () => void
}

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "—"
  if (seconds < 60) return `${Math.round(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s}s`
}

function formatCount(n: number | null): string {
  if (n == null) return "—"
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return `${n}`
}

function formatDate(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  const now = new Date()
  const diffH = (now.getTime() - d.getTime()) / 3_600_000
  if (diffH < 24) return `hoje ${d.getUTCHours().toString().padStart(2, "0")}:${d.getUTCMinutes().toString().padStart(2, "0")}`
  if (diffH < 48) return "ontem"
  return d.toLocaleDateString("pt-BR")
}

export function TldMetricsTable({
  rows,
  onToggle,
  onEnableAll,
  onDisableAll,
}: TldMetricsTableProps) {
  const [filter, setFilter] = useState("")
  const [toggling, setToggling] = useState<Set<string>>(new Set())

  const filtered = useMemo(
    () => rows.filter((r) => r.tld.includes(filter.toLowerCase())),
    [rows, filter]
  )

  const activeCount = rows.filter((r) => r.is_enabled).length

  async function handleToggle(tld: string, enabled: boolean) {
    setToggling((prev) => new Set(prev).add(tld))
    try {
      await onToggle(tld, enabled)
    } finally {
      setToggling((prev) => {
        const next = new Set(prev)
        next.delete(tld)
        return next
      })
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">
          {activeCount} ativos de {rows.length}
        </span>
        <Input
          placeholder="Filtrar TLDs…"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="h-7 w-40 text-xs"
        />
        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onEnableAll}>
          Habilitar todos
        </Button>
        <Button variant="outline" size="sm" className="h-7 text-xs" onClick={onDisableAll}>
          Desabilitar todos
        </Button>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="font-mono text-xs">TLD</TableHead>
              <TableHead className="text-center text-xs">Ativo</TableHead>
              <TableHead className="text-right text-xs">Duração</TableHead>
              <TableHead className="text-right text-xs">Inseridos</TableHead>
              <TableHead className="text-center text-xs">Última OK</TableHead>
              <TableHead className="text-center text-xs">Últimas 10</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((row) => (
              <TableRow key={row.tld} className={row.is_enabled ? "" : "opacity-50"}>
                <TableCell className="font-mono text-sm font-medium">{row.tld}</TableCell>
                <TableCell className="text-center">
                  <Switch
                    checked={row.is_enabled}
                    disabled={toggling.has(row.tld)}
                    onCheckedChange={(checked) => handleToggle(row.tld, checked)}
                  />
                </TableCell>
                <TableCell className="text-right text-xs tabular-nums text-muted-foreground">
                  {formatDuration(row.last_duration_seconds)}
                </TableCell>
                <TableCell className="text-right text-xs tabular-nums">
                  {formatCount(row.last_domains_inserted)}
                </TableCell>
                <TableCell className="text-center text-xs text-muted-foreground">
                  {formatDate(row.last_successful_run_at)}
                </TableCell>
                <TableCell className="text-center">
                  <Sparkbar
                    runs={row.recent_runs.map((r) => ({
                      status: r.status === "running" ? "running" : r.status,
                      duration_seconds: r.duration_seconds,
                    }))}
                  />
                </TableCell>
              </TableRow>
            ))}
            {filtered.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-xs text-muted-foreground py-6">
                  Nenhum TLD encontrado
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      <p className="text-xs text-muted-foreground">
        Barras: altura proporcional à duração · verde = sucesso · vermelho = erro · cinza = sem dado
      </p>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/ingestion/tld-metrics-table.tsx
git commit -m "feat(frontend): TldMetricsTable component with sparkbar"
```

---

## Task 14: Frontend — Source Config Page Component

**Files:**
- Create: `frontend/components/ingestion/source-config-page.tsx`

This is the "smart" component that fetches data for a source and composes CronConfigCard + TldMetricsTable. It handles data loading, metric computation (joins runs + checkpoints + tld policies), and all actions.

- [ ] **Step 0: Verify existing API function names in `frontend/lib/api.ts`**

Before writing the component, confirm:
- The function/method to fetch checkpoints (search for `checkpoint` in `api.ts`) — note its exact name and call signature
- The function/method to fetch runs filtered by source+tld (search for `getRuns` or `runs` in `api.ts`) — note its exact params

Update the `ingestionApi.getCheckpoints(source)` and `ingestionApi.getRuns(...)` calls in the component below to match the actual names.

- [ ] **Step 1: Create source-config-page**

```tsx
// frontend/components/ingestion/source-config-page.tsx
"use client"

import { useCallback, useEffect, useState } from "react"
import { ArrowLeft, RefreshCw } from "lucide-react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { CronConfigCard } from "./cron-config-card"
import { TldMetricsTable } from "./tld-metrics-table"
import {
  getIngestionConfigs,
  getTldPolicies,
  updateIngestionCron,
  patchTldPolicy,
  bulkSetTldPolicies,
} from "@/lib/api"
import type {
  IngestionSourceConfig,
  IngestionTldPolicy,
  TldMetricsRow,
} from "@/lib/types"

// Import existing API functions for runs and checkpoints
import { ingestionApi } from "@/lib/api"

const SOURCE_LABELS: Record<string, string> = {
  czds: "CZDS",
  certstream: "CertStream",
  openintel: "OpenINTEL",
}

interface SourceConfigPageProps {
  source: string
}

export function SourceConfigPage({ source }: SourceConfigPageProps) {
  const [config, setConfig] = useState<IngestionSourceConfig | null>(null)
  const [policies, setPolicies] = useState<IngestionTldPolicy[]>([])
  const [metricsRows, setMetricsRows] = useState<TldMetricsRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const label = SOURCE_LABELS[source] ?? source.toUpperCase()
  const isContinuousStream = source === "certstream"

  const loadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      // Fetch config, policies, runs, and checkpoints in parallel
      const [configs, tldPolicies, checkpoints] = await Promise.all([
        getIngestionConfigs(),
        getTldPolicies(source),
        ingestionApi.getCheckpoints(source),
      ])

      const sourceConfig = configs.find((c) => c.source === source) ?? null
      setConfig(sourceConfig)
      setPolicies(tldPolicies)

      // Build checkpoint index: tld → last_successful_run_at
      const checkpointMap = Object.fromEntries(
        checkpoints.map((c: { tld: string; last_successful_run_at: string | null }) => [
          c.tld,
          c.last_successful_run_at,
        ])
      )

      // For each TLD in policies, fetch last 10 runs
      const rowPromises = tldPolicies.map(async (p): Promise<TldMetricsRow> => {
        try {
          const runs = await ingestionApi.getRuns({
            source,
            tld: p.tld,
            limit: 10,
          })
          const lastRun = runs[0] ?? null
          const durationSeconds =
            lastRun?.finished_at && lastRun?.started_at
              ? (new Date(lastRun.finished_at).getTime() -
                  new Date(lastRun.started_at).getTime()) /
                1000
              : null

          return {
            tld: p.tld,
            is_enabled: p.is_enabled,
            last_duration_seconds: durationSeconds,
            last_domains_inserted: lastRun?.domains_inserted ?? null,
            last_successful_run_at: checkpointMap[p.tld] ?? null,
            recent_runs: runs
              .slice()
              .reverse() // oldest first
              .map((r: { status: string; started_at: string; finished_at: string | null }) => ({
                status: r.status as "success" | "failed" | "running",
                duration_seconds:
                  r.finished_at
                    ? (new Date(r.finished_at).getTime() -
                        new Date(r.started_at).getTime()) /
                      1000
                    : null,
                started_at: r.started_at,
              })),
          }
        } catch {
          return {
            tld: p.tld,
            is_enabled: p.is_enabled,
            last_duration_seconds: null,
            last_domains_inserted: null,
            last_successful_run_at: checkpointMap[p.tld] ?? null,
            recent_runs: [],
          }
        }
      })

      const rows = await Promise.all(rowPromises)
      // Sort: enabled first, then alphabetically
      rows.sort((a, b) => {
        if (a.is_enabled !== b.is_enabled) return a.is_enabled ? -1 : 1
        return a.tld.localeCompare(b.tld)
      })
      setMetricsRows(rows)
    } catch (e) {
      setError("Erro ao carregar dados. Tente novamente.")
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [source])

  useEffect(() => {
    loadData()
  }, [loadData])

  async function handleSaveCron(cron: string) {
    await updateIngestionCron(source, cron)
    setConfig((prev) => prev ? { ...prev, cron_expression: cron } : prev)
  }

  async function handleToggleTld(tld: string, enabled: boolean) {
    await patchTldPolicy(source, tld, enabled)
    // Optimistic update
    setMetricsRows((prev) =>
      prev.map((r) => (r.tld === tld ? { ...r, is_enabled: enabled } : r))
    )
    setPolicies((prev) =>
      prev.map((p) => (p.tld === tld ? { ...p, is_enabled: enabled } : p))
    )
  }

  async function handleEnableAll() {
    const tlds = metricsRows.map((r) => ({ tld: r.tld, is_enabled: true }))
    await bulkSetTldPolicies(source, tlds)
    setMetricsRows((prev) => prev.map((r) => ({ ...r, is_enabled: true })))
  }

  async function handleDisableAll() {
    const tlds = metricsRows.map((r) => ({ tld: r.tld, is_enabled: false }))
    await bulkSetTldPolicies(source, tlds)
    setMetricsRows((prev) => prev.map((r) => ({ ...r, is_enabled: false })))
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link href="/admin/ingestion">
            <Button variant="ghost" size="sm" className="gap-1">
              <ArrowLeft className="h-3 w-3" />
              Ingestions
            </Button>
          </Link>
          <h1 className="text-2xl font-semibold">{label}</h1>
        </div>
        <Button variant="outline" size="sm" onClick={loadData} disabled={loading}>
          <RefreshCw className={`h-3 w-3 mr-1 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <p className="text-sm text-destructive">{error}</p>
      )}

      {loading ? (
        <div className="space-y-4">
          <Skeleton className="h-20 rounded-xl" />
          <Skeleton className="h-64 rounded-xl" />
        </div>
      ) : (
        <>
          {config && (
            <CronConfigCard
              source={source}
              initialCron={config.cron_expression}
              isContinuousStream={isContinuousStream}
              onSave={handleSaveCron}
            />
          )}

          <TldMetricsTable
            rows={metricsRows}
            onToggle={handleToggleTld}
            onEnableAll={handleEnableAll}
            onDisableAll={handleDisableAll}
          />
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/ingestion/source-config-page.tsx
git commit -m "feat(frontend): SourceConfigPage component (cron + TLD metrics)"
```

---

## Task 15: Frontend — Dynamic Route Page

**Files:**
- Create: `frontend/app/admin/ingestion/[source]/page.tsx`

- [ ] **Step 1: Create dynamic route**

```tsx
// frontend/app/admin/ingestion/[source]/page.tsx
import { SourceConfigPage } from "@/components/ingestion/source-config-page"

const VALID_SOURCES = ["czds", "certstream", "openintel"]

interface Props {
  params: { source: string }
}

export default function IngestionSourcePage({ params }: Props) {
  if (!VALID_SOURCES.includes(params.source)) {
    return (
      <div className="p-8 text-muted-foreground">
        Fonte desconhecida: {params.source}
      </div>
    )
  }
  return <SourceConfigPage source={params.source} />
}

export function generateStaticParams() {
  return VALID_SOURCES.map((source) => ({ source }))
}
```

- [ ] **Step 2: Commit**

```bash
git add "frontend/app/admin/ingestion/[source]/page.tsx"
git commit -m "feat(frontend): /admin/ingestion/[source] dynamic route"
```

---

## Task 16: Frontend — Update Overview Page

**Files:**
- Modify: `frontend/app/admin/ingestion/page.tsx`

Add 3 source summary cards above the existing `<Tabs>`. Each card shows source name, status badge, cron preview (from `cycleStatus.schedules`), active TLD count, and a "Configurar →" link.

- [ ] **Step 1: Verify data fields before editing**

Read `frontend/app/admin/ingestion/page.tsx` to confirm:
- The hook call (should be `const data = useIngestionData()`)
- That `data.cycleStatus?.schedules` exists and has `source` + `cron_expression` + `mode` fields (check `frontend/lib/types.ts` for `IngestionCycleStatus`)
- That `data.summaries` has `source`, `running_now`, and `last_status` fields

If field names differ, adjust the JSX below accordingly.

- [ ] **Step 2: Add source cards to `page.tsx`**

After the existing `<div className="flex items-center justify-between">` header block and before `<Tabs defaultValue="overview">`, insert:

```tsx
{/* Source summary cards */}
{(() => {
  const SOURCES = [
    { key: "czds", label: "CZDS" },
    { key: "certstream", label: "CertStream" },
    { key: "openintel", label: "OpenINTEL" },
  ]
  const schedules = data.cycleStatus?.schedules ?? []

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
      {SOURCES.map(({ key, label }) => {
        const schedule = schedules.find((s) => s.source === key)
        const summary = data.summaries.find((s) => s.source === key)
        const isRealtime = schedule?.mode === "realtime"
        const statusColor =
          summary?.running_now ? "text-blue-400" :
          summary?.last_status === "success" ? "text-green-500" :
          "text-muted-foreground"

        return (
          <div
            key={key}
            className="rounded-lg border bg-card p-4 space-y-2"
          >
            <div className="flex items-center justify-between">
              <span className="font-semibold text-sm">{label}</span>
              <span className={`text-xs ${statusColor}`}>
                ● {summary?.running_now ? "Running" : summary?.last_status ?? "Idle"}
              </span>
            </div>
            <div className="text-xs text-muted-foreground">
              {isRealtime
                ? "Stream contínuo"
                : `Cron: ${schedule?.cron_expression ?? "—"}`}
            </div>
            <Link
              href={`/admin/ingestion/${key}`}
              className="text-xs text-blue-400 hover:underline"
            >
              Configurar →
            </Link>
          </div>
        )
      })}
    </div>
  )
})()}
```

Add `import Link from "next/link"` at the top if not already present.

- [ ] **Step 3: Verify migration seed matches env defaults**

```bash
# Check that seeded cron values match the env var defaults in config.py
grep -E "(CZDS_SYNC_CRON|CT_CRTSH_SYNC_CRON|OPENINTEL_SYNC_CRON)" backend/app/core/config.py
```

Expected: `"0 7 * * *"`, `"0 5 * * *"`, `"0 2 * * *"` — matching the hardcoded values in the migration seed.

- [ ] **Step 4: Verify overview page renders**

Navigate to `/admin/ingestion` in the browser. You should see 3 cards above the existing tabs.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/admin/ingestion/page.tsx
git commit -m "feat(frontend): add source summary cards to ingestion overview page"
```

---

## Verification

Run these checks after all tasks are complete:

- [ ] **Backend:** `GET /v1/ingestion/config` returns 3 rows with cron expressions
- [ ] **Backend:** `PUT /v1/ingestion/config/openintel` with `{"cron_expression": "0 3 * * *"}` updates row and returns new value
- [ ] **Backend:** `GET /v1/ingestion/tld-policy/openintel` returns empty list initially
- [ ] **Backend:** `PATCH /v1/ingestion/tld-policy/openintel/br` with `{"is_enabled": false}` creates+disables the row
- [ ] **Worker:** Restart openintel_ingestor, trigger a cycle — verify `.br` is skipped in logs
- [ ] **Worker:** Change cron via API, wait for next cycle start — verify log shows "Cron updated: old → new"
- [ ] **Frontend:** `/admin/ingestion` shows 3 source cards with "Configurar →" links
- [ ] **Frontend:** `/admin/ingestion/openintel` loads, shows cron card and TLD table
- [ ] **Frontend:** Toggling a TLD updates the switch optimistically and fires PATCH API call
- [ ] **Frontend:** Sparkbar shows 10 bars for a TLD with run history; gray bars for empty slots
