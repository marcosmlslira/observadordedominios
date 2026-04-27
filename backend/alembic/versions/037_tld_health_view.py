"""Add tld_health_v view — last ingestion_run row per (source, tld).

Revision ID: 037_tld_health_view
Revises: 036_ingestion_cycle
Create Date: 2026-05-08
"""

from __future__ import annotations

from alembic import op

revision = "037_tld_health_view"
down_revision = "036_ingestion_cycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS tld_health_v")
    op.execute("""
        CREATE VIEW tld_health_v AS
        SELECT DISTINCT ON (source, tld)
            source,
            tld,
            status              AS last_status,
            reason_code         AS last_reason_code,
            started_at          AS last_attempt_at,
            finished_at         AS last_finished_at,
            domains_inserted,
            domains_deleted,
            domains_seen,
            error_message       AS last_error_message
        FROM ingestion_run
        ORDER BY source, tld, started_at DESC
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS tld_health_v")
