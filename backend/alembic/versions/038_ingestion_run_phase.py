"""Add phase column to ingestion_run — separates R2 phase from PG phase.

  phase='full' → local path covering both R2 diff and PG load (default for
                  all existing rows and small TLDs processed locally)
  phase='r2'   → Databricks job that produced the delta+marker in R2
  phase='pg'   → standalone PG load from R2 (LOAD_ONLY or post-Databricks)

Revision ID: 038_ingestion_run_phase
Revises: 037_tld_health_view
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "038_ingestion_run_phase"
down_revision = "037_tld_health_view"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ADD COLUMN with a constant DEFAULT does not rewrite the table on Postgres 16.
    op.execute("""
        ALTER TABLE ingestion_run
        ADD COLUMN IF NOT EXISTS phase TEXT NOT NULL DEFAULT 'full'
            CHECK (phase IN ('full', 'r2', 'pg'))
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_ingestion_run_phase
        ON ingestion_run (phase)
        WHERE phase != 'full'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ingestion_run_phase")
    op.execute("ALTER TABLE ingestion_run DROP COLUMN IF EXISTS phase")
