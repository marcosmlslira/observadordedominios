"""Add missing FK indexes and temporal columns to zone_file_artifact

Revision ID: 002_indexes_artifact_ts
Revises: 001_initial_czds
Create Date: 2026-03-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "002_indexes_artifact_ts"
down_revision: Union[str, None] = "001_initial_czds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── P3: Missing FK indexes ────────────────────────────────
    op.create_index(
        "ix_run_artifact_id",
        "ingestion_run",
        ["artifact_id"],
    )
    op.create_index(
        "ix_domain_obs_domain_id",
        "domain_observation",
        ["domain_id"],
    )
    op.create_index(
        "ix_domain_obs_run_id",
        "domain_observation",
        ["ingestion_run_id"],
    )

    # ── P4: Temporal columns on zone_file_artifact ────────────
    op.add_column(
        "zone_file_artifact",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "zone_file_artifact",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # Backfill existing rows: use downloaded_at as sensible default
    op.execute(
        "UPDATE zone_file_artifact "
        "SET created_at = downloaded_at, updated_at = downloaded_at "
        "WHERE created_at IS NULL"
    )

    # Now enforce NOT NULL
    op.alter_column("zone_file_artifact", "created_at", nullable=False)
    op.alter_column("zone_file_artifact", "updated_at", nullable=False)


def downgrade() -> None:
    op.drop_column("zone_file_artifact", "updated_at")
    op.drop_column("zone_file_artifact", "created_at")
    op.drop_index("ix_domain_obs_run_id", table_name="domain_observation")
    op.drop_index("ix_domain_obs_domain_id", table_name="domain_observation")
    op.drop_index("ix_run_artifact_id", table_name="ingestion_run")
