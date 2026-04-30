"""Add ingestion_cycle_tld — per-TLD plan row for every cycle.

Each row is created at cycle start (status='planned') and updated as the
TLD progresses. TLDs not reached before cycle end are closed as 'not_reached'.
This gives every enabled TLD a deterministic status for every cycle day.

Revision ID: 040_ingestion_cycle_tld
Revises: 039_tld_daily_status_view
Create Date: 2026-04-30
"""

from __future__ import annotations

from alembic import op

revision = "040_ingestion_cycle_tld"
down_revision = "039_tld_daily_status_view"
branch_labels = None
depends_on = None

_EXECUTION_STATUSES = (
    "planned",
    "running",
    "success",
    "failed",
    "skipped",
    "not_reached",
    "interrupted",
)

_PLANNED_PHASES = ("skip", "load_only", "full_run")


def upgrade() -> None:
    op.execute(f"""
        CREATE TABLE IF NOT EXISTS ingestion_cycle_tld (
            cycle_id                UUID        NOT NULL
                                    REFERENCES ingestion_cycle (cycle_id) ON DELETE CASCADE,
            source                  TEXT        NOT NULL,
            tld                     TEXT        NOT NULL,

            -- Planning metadata
            priority                INT,
            planned_position        INT,
            planned_phase           TEXT        CHECK (planned_phase IN {_PLANNED_PHASES}),

            -- Execution state
            execution_status        TEXT        NOT NULL DEFAULT 'planned'
                                    CHECK (execution_status IN {_EXECUTION_STATUSES}),
            blocked_by_source       TEXT,
            blocked_by_tld          TEXT,

            -- Error detail
            reason_code             TEXT,
            error_message           TEXT,

            -- Run linkage
            r2_run_id               UUID,
            pg_run_id               UUID,

            -- Databricks metadata
            databricks_run_id       BIGINT,
            databricks_run_url      TEXT,
            databricks_result_state TEXT,

            -- Snapshot info
            r2_marker_date          DATE,
            snapshot_date           DATE,

            -- Timing
            started_at              TIMESTAMPTZ,
            finished_at             TIMESTAMPTZ,
            duration_seconds        INT,

            -- PK
            PRIMARY KEY (cycle_id, source, tld)
        )
    """)

    # Fast lookups for "all not_reached in cycle X" and "latest status of TLD Y"
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_ict_cycle_status
            ON ingestion_cycle_tld (cycle_id, execution_status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_ict_source_tld
            ON ingestion_cycle_tld (source, tld, finished_at DESC)
    """)
    # Partial index: quickly find any cycle with pending rows
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_ict_planned
            ON ingestion_cycle_tld (cycle_id)
            WHERE execution_status = 'planned'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_ict_planned")
    op.execute("DROP INDEX IF EXISTS ix_ict_source_tld")
    op.execute("DROP INDEX IF EXISTS ix_ict_cycle_status")
    op.execute("DROP TABLE IF EXISTS ingestion_cycle_tld")
