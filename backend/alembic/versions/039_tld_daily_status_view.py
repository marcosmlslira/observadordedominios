"""Add tld_daily_status_v — per-(source, tld, day) view with r2_status and pg_status.

This view is the foundation for the dual-phase heatmap in /admin/ingestion.
It reads ingestion_run.phase to separate what happened in the R2 phase from
what happened in the PG load phase, for each TLD and calendar day.

Revision ID: 039_tld_daily_status_view
Revises: 038_ingestion_run_phase
Create Date: 2026-04-29
"""

from __future__ import annotations

from alembic import op

revision = "039_tld_daily_status_view"
down_revision = "038_ingestion_run_phase"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS tld_daily_status_v")
    op.execute("""
        CREATE VIEW tld_daily_status_v AS
        WITH best_per_phase AS (
            -- For each (source, tld, day, phase) keep the best run:
            -- success wins over running wins over failed.
            SELECT DISTINCT ON (source, tld, COALESCE(snapshot_date, started_at::date), phase)
                source,
                tld,
                phase,
                COALESCE(snapshot_date, started_at::date)   AS day,
                status,
                reason_code,
                error_message,
                started_at,
                finished_at,
                domains_inserted,
                domains_deleted
            FROM ingestion_run
            ORDER BY
                source,
                tld,
                COALESCE(snapshot_date, started_at::date),
                phase,
                -- prefer success first, then by recency
                (status = 'success') DESC,
                started_at DESC
        )
        SELECT
            source,
            tld,
            day,
            -- R2 phase: either a dedicated 'r2' run or the r2-half of a 'full' run
            MAX(status)         FILTER (WHERE phase IN ('r2', 'full'))     AS r2_status,
            MAX(reason_code)    FILTER (WHERE phase IN ('r2', 'full'))     AS r2_reason,
            -- PG phase: either a dedicated 'pg' run or the pg-half of a 'full' run
            MAX(status)         FILTER (WHERE phase IN ('pg', 'full'))     AS pg_status,
            MAX(reason_code)    FILTER (WHERE phase IN ('pg', 'full'))     AS pg_reason,
            -- surface the most recent error regardless of phase
            MAX(error_message)  FILTER (WHERE status = 'failed')           AS last_error,
            -- cycle timing based on the first start and last finish of the day
            EXTRACT(EPOCH FROM (
                MAX(finished_at) - MIN(started_at)
            ))::int                                                        AS duration_seconds,
            COALESCE(
                SUM(domains_inserted) FILTER (WHERE phase IN ('pg', 'full')), 0
            )                                                              AS domains_inserted,
            COALESCE(
                SUM(domains_deleted)  FILTER (WHERE phase IN ('pg', 'full')), 0
            )                                                              AS domains_deleted
        FROM best_per_phase
        GROUP BY source, tld, day
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS tld_daily_status_v")
