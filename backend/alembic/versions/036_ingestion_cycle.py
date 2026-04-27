"""Add ingestion_cycle table for per-cycle audit trail.

Revision ID: 036_ingestion_cycle
Revises: 035_ingestion_run_reason_code
Create Date: 2026-05-08
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "036_ingestion_cycle"
down_revision = "035_ingestion_run_reason_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS ingestion_cycle (
            cycle_id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            started_at        TIMESTAMPTZ NOT NULL    DEFAULT now(),
            finished_at       TIMESTAMPTZ,
            status            TEXT        NOT NULL    DEFAULT 'running'
                                          CHECK (status IN ('running','succeeded','failed','interrupted')),
            triggered_by      TEXT        NOT NULL    DEFAULT 'cron'
                                          CHECK (triggered_by IN ('cron','manual','api')),
            tld_total         INT,
            tld_success       INT         NOT NULL    DEFAULT 0,
            tld_failed        INT         NOT NULL    DEFAULT 0,
            tld_skipped       INT         NOT NULL    DEFAULT 0,
            tld_load_only     INT         NOT NULL    DEFAULT 0,
            last_heartbeat_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_ingestion_cycle_started_at ON ingestion_cycle (started_at DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ingestion_cycle_started_at")
    op.execute("DROP TABLE IF EXISTS ingestion_cycle")
