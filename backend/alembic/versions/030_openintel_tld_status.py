"""Create openintel_tld_status table for availability verification UI.

Revision ID: 030_openintel_tld_status
Revises: 029_certstream_tld_stats
Create Date: 2026-04-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "030_openintel_tld_status"
down_revision = "029_certstream_tld_stats"
branch_labels = None
depends_on = None

_OUTCOME_VALUES = (
    "no_snapshot_available",
    "already_ingested",
    "ingested_new_snapshot",
    "new_snapshot_pending_or_failed",
    "verification_failed",
)


def upgrade() -> None:
    op.create_table(
        "openintel_tld_status",
        sa.Column("tld", sa.String(length=24), nullable=False),
        sa.Column("last_verification_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_available_snapshot_date", sa.Date(), nullable=True),
        sa.Column("last_ingested_snapshot_date", sa.Date(), nullable=True),
        sa.Column("last_probe_outcome", sa.String(length=64), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "("
            "last_probe_outcome IS NULL OR "
            f"last_probe_outcome IN { _OUTCOME_VALUES }"
            ")",
            name="ck_openintel_tld_status_outcome",
        ),
        sa.PrimaryKeyConstraint("tld"),
    )


def downgrade() -> None:
    op.drop_table("openintel_tld_status")
