"""Add reason_code to ingestion_run for auditability.

Revision ID: 035_ingestion_run_reason_code
Revises: 034_disable_legacy_ct_sources
Create Date: 2026-04-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "035_ingestion_run_reason_code"
down_revision = "034_disable_legacy_ct_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            ALTER TABLE ingestion_run
            ADD COLUMN IF NOT EXISTS reason_code VARCHAR(64)
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS ix_ingestion_run_reason_code_finished
            ON ingestion_run (reason_code, finished_at)
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_run_reason_code_finished", table_name="ingestion_run")
    op.drop_column("ingestion_run", "reason_code")
