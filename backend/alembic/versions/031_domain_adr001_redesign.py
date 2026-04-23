"""ADR-001 — Drop and recreate domain tables with simplified schema.

Removes: first_seen_at, last_seen_at, domain_raw_b64, is_active, domain_stage.
Adds:    added_day INTEGER (YYYYMMDD).
Creates: domain_removed table.

Revision ID: 031_domain_adr001_redesign
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "031_domain_adr001_redesign"
down_revision = "030_openintel_tld_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Drop everything that depends on domain ──────────────────────────
    # Drop similarity_match foreign key to domain (soft ref — it stores
    # (name, tld) strings, no FK constraint, so no action needed).

    # Drop domain_stage (from migration 025)
    op.execute("DROP TABLE IF EXISTS domain_stage CASCADE")

    # Drop domain (CASCADE drops any remaining partitions automatically)
    op.execute("DROP TABLE IF EXISTS domain CASCADE")

    # Drop domain_removed if it already exists (idempotent)
    op.execute("DROP TABLE IF EXISTS domain_removed CASCADE")

    # ── 2. Ensure pg_trgm extension (may already exist) ───────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # ── 3. Create new domain table ─────────────────────────────────────────
    op.execute("""
        CREATE TABLE domain (
            name      VARCHAR(253) NOT NULL,
            tld       VARCHAR(24)  NOT NULL,
            label     VARCHAR      NOT NULL,
            added_day INTEGER      NOT NULL,
            PRIMARY KEY (name, tld)
        ) PARTITION BY LIST (tld)
    """)

    op.execute("""
        CREATE INDEX ix_domain_label_trgm ON domain
        USING gin (label gin_trgm_ops)
    """)

    op.execute("""
        CREATE INDEX ix_domain_added_day ON domain (added_day)
    """)

    # ── 4. Create domain_removed table ────────────────────────────────────
    op.execute("""
        CREATE TABLE domain_removed (
            name         VARCHAR(253) NOT NULL,
            tld          VARCHAR(24)  NOT NULL,
            removed_day  INTEGER      NOT NULL,
            PRIMARY KEY (name, tld)
        ) PARTITION BY LIST (tld)
    """)

    op.execute("""
        CREATE INDEX ix_domain_removed_day ON domain_removed (removed_day)
    """)

    # ── 5. Recreate tld_domain_count_mv (was CASCADE-dropped with domain) ──
    # Created originally in 017_tld_domain_count_mv; must be rebuilt here.
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS tld_domain_count_mv AS
        SELECT tld, COUNT(*) AS count
        FROM domain
        GROUP BY tld
        ORDER BY count DESC
        WITH NO DATA
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS tld_domain_count_mv_tld_idx
        ON tld_domain_count_mv (tld)
    """)

    # ── 7. Add watermark_day to similarity_scan_cursor ────────────────────
    # Replaces watermark_at (TIMESTAMPTZ) semantics — now tracks YYYYMMDD integer
    op.execute("""
        ALTER TABLE similarity_scan_cursor
        ADD COLUMN IF NOT EXISTS watermark_day INTEGER
    """)


def downgrade() -> None:
    # Drop ADR-001 tables
    op.execute("DROP TABLE IF EXISTS domain_removed CASCADE")
    op.execute("DROP TABLE IF EXISTS domain CASCADE")

    # Recreate legacy domain table (pre-ADR-001)
    op.execute("""
        CREATE TABLE domain (
            name           VARCHAR(253) NOT NULL,
            tld            VARCHAR(24)  NOT NULL,
            label          VARCHAR      NOT NULL,
            first_seen_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            last_seen_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            PRIMARY KEY (name, tld)
        ) PARTITION BY LIST (tld)
    """)
    op.execute("""
        CREATE INDEX ix_domain_label_trgm ON domain
        USING gin (label gin_trgm_ops)
    """)
    op.execute("""
        CREATE TABLE domain_stage (
            name       VARCHAR(253) NOT NULL,
            tld        VARCHAR(24)  NOT NULL,
            label      VARCHAR      NOT NULL,
            loaded_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            PRIMARY KEY (name, tld)
        )
    """)
