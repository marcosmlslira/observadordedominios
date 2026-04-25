"""Disable legacy CT ingestion sources in active config.

Revision ID: 034_disable_legacy_ct_sources
Revises: 033_ingestion_run_snapshot_date
Create Date: 2026-04-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "034_disable_legacy_ct_sources"
down_revision = "033_ingestion_run_snapshot_date"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep historical runs for audit, but force-close any currently-running legacy CT runs.
    op.execute(
        sa.text(
            """
            UPDATE ingestion_run
            SET
                status = 'failed',
                finished_at = now(),
                updated_at = now(),
                error_message = COALESCE(
                    NULLIF(error_message, ''),
                    'Legacy CT ingestion path disabled by ADR-001 cleanup'
                )
            WHERE source IN ('certstream', 'crtsh')
              AND status = 'running'
            """
        )
    )

    # Active source config now contains only czds/openintel.
    op.execute(
        sa.text(
            "DELETE FROM ingestion_source_config WHERE source = 'certstream'"
        )
    )

    # Legacy certstream TLD policy rows are no longer operational.
    op.execute(
        sa.text(
            "DELETE FROM ingestion_tld_policy WHERE source = 'certstream'"
        )
    )


def downgrade() -> None:
    # Restore legacy source config row for rollback compatibility.
    op.execute(
        sa.text(
            """
            INSERT INTO ingestion_source_config (source, cron_expression)
            VALUES ('certstream', '0 5 * * *')
            ON CONFLICT (source) DO NOTHING
            """
        )
    )
