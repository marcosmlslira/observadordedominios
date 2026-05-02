"""Per-TLD override for the stale watchdog timeout.

Long-running TLD ingestions (czds/xyz, czds/info, czds/org) legitimately take
several hours to complete. The previous 45-minute global default would mark
them as stale_recovered while they were still making progress.

This migration adds an opt-in column on ingestion_tld_policy. When NULL the
runtime keeps using settings.ingestion_stale_timeout_minutes; when populated
it overrides the watchdog threshold for that (source, tld) pair.

Revision ID: 044_tld_policy_stale_timeout
Revises: 043_drop_legacy_czds_tld_policy
Create Date: 2026-05-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "044_tld_policy_stale_timeout"
down_revision = "043_drop_legacy_czds_tld_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_tld_policy",
        sa.Column(
            "stale_timeout_seconds",
            sa.Integer(),
            nullable=True,
            comment=(
                "Per-TLD override for the stale watchdog timeout (seconds). "
                "NULL means use the global INGESTION_STALE_TIMEOUT_MINUTES."
            ),
        ),
    )

    # Seed overrides for the TLDs that triggered the 01/05 incident.
    # These are the largest CZDS zones and routinely exceed the default.
    op.execute(
        """
        UPDATE ingestion_tld_policy SET stale_timeout_seconds = 28800
         WHERE source = 'czds' AND tld IN ('xyz', 'info')
        """
    )
    op.execute(
        """
        UPDATE ingestion_tld_policy SET stale_timeout_seconds = 21600
         WHERE source = 'czds' AND tld = 'org'
        """
    )


def downgrade() -> None:
    op.drop_column("ingestion_tld_policy", "stale_timeout_seconds")
