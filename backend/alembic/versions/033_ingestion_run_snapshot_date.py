"""Add snapshot_date to ingestion_run for precise deduplication.

Revision ID: 033_ingestion_run_snapshot_date
Revises: 032_similarity_match_expired_day
Create Date: 2026-04-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "033_ingestion_run_snapshot_date"
down_revision = "032_similarity_match_expired_day"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingestion_run", sa.Column("snapshot_date", sa.Date(), nullable=True))
    op.create_index(
        "ix_ingestion_run_source_tld_snapshot",
        "ingestion_run",
        ["source", "tld", "snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_run_source_tld_snapshot", table_name="ingestion_run")
    op.drop_column("ingestion_run", "snapshot_date")
