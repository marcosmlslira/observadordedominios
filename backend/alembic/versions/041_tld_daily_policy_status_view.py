"""Add tld_daily_policy_status_v — policy-based daily coverage view.

Unlike tld_daily_status_v (which only shows TLDs that ran), this view
LEFT JOINs ingestion_tld_policy as the denominator so every enabled TLD
appears for every cycle day, even when it was never attempted.

This is the foundation for the policy-coverage metric and the not_reached
state in the heatmap.

Revision ID: 041_tld_daily_policy_status_view
Revises: 040_ingestion_cycle_tld
Create Date: 2026-04-30
"""

from __future__ import annotations

from alembic import op

revision = "041_tld_daily_policy_status_view"
down_revision = "040_ingestion_cycle_tld"
branch_labels = None
depends_on = None

_VIEW_SQL = """
CREATE OR REPLACE VIEW tld_daily_policy_status_v AS
SELECT
    p.source,
    p.tld,
    c.started_at::date                              AS day,
    p.is_enabled,
    p.priority,
    ct.planned_phase,
    ct.execution_status,
    ct.reason_code,
    ct.error_message,

    -- Preserve r2/pg breakdown from ingestion_run for heatmap compat
    r2.status                                       AS r2_status,
    r2.reason_code                                  AS r2_reason,
    pg.status                                       AS pg_status,
    pg.reason_code                                  AS pg_reason,

    ct.databricks_run_url,
    ct.databricks_result_state,
    ct.snapshot_date,
    ct.started_at                                   AS tld_started_at,
    ct.finished_at                                  AS tld_finished_at,
    ct.duration_seconds
FROM ingestion_tld_policy p
-- Each cycle day the policy appears in
CROSS JOIN (
    SELECT DISTINCT cycle_id, started_at
    FROM ingestion_cycle
    WHERE status != 'running'          -- only closed cycles
) c
LEFT JOIN ingestion_cycle_tld ct
    ON  ct.cycle_id = c.cycle_id
    AND ct.source   = p.source
    AND ct.tld      = p.tld
-- R2 phase run (for heatmap dual-phase compat)
LEFT JOIN LATERAL (
    SELECT status, reason_code
    FROM ingestion_run ir
    WHERE ir.source = p.source
      AND ir.tld    = p.tld
      AND ir.phase  = 'r2'
      AND ir.started_at::date = c.started_at::date
    ORDER BY ir.started_at DESC
    LIMIT 1
) r2 ON true
-- PG phase run
LEFT JOIN LATERAL (
    SELECT status, reason_code
    FROM ingestion_run ir
    WHERE ir.source = p.source
      AND ir.tld    = p.tld
      AND ir.phase  IN ('pg', 'full')
      AND ir.started_at::date = c.started_at::date
    ORDER BY ir.started_at DESC
    LIMIT 1
) pg ON true
WHERE p.is_enabled = true
"""


def upgrade() -> None:
    op.execute(_VIEW_SQL)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_ict_cycle_day
            ON ingestion_cycle ((started_at::date) DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ict_cycle_day")
    op.execute("DROP VIEW IF EXISTS tld_daily_policy_status_v")
