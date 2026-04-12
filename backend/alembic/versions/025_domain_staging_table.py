"""Add domain_stage UNLOGGED table for large-TLD incremental ingestion.

For TLDs with >50M domains (e.g. .com, .net), the standard bulk_upsert
path hits the GIN trigram index on every batch, making each run ~74h.

This staging table acts as a buffer:
  1. Load zone file into domain_stage (UNLOGGED, no GIN) in ~5-10 min
  2. Merge only net-new rows into domain (GIN touched only for delta ~1-2%)
  3. Subsequent daily runs complete in ~30-45 min instead of 74h

Revision ID: 025_domain_staging_table
Revises: 024_ingestion_tld_priority
Create Date: 2026-04-12
"""

from alembic import op

revision = "025_domain_staging_table"
down_revision = "024_ingestion_tld_priority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # UNLOGGED: skips WAL, ~2-3x faster bulk loads.
    # Acceptable because this is a staging buffer — not source of truth.
    # Data is cleared after each merge; loss on crash is harmless (re-run next cycle).
    op.execute("""
        CREATE UNLOGGED TABLE IF NOT EXISTS domain_stage (
            name        VARCHAR(253)            NOT NULL,
            tld         VARCHAR(24)             NOT NULL,
            label       VARCHAR                 NOT NULL,
            loaded_at   TIMESTAMPTZ             NOT NULL DEFAULT now(),
            PRIMARY KEY (name, tld)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS domain_stage")
