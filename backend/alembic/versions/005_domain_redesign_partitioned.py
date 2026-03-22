"""Redesign domain table: partitioned by TLD, natural PK, label column, GIN trigram

- Replaces UUID PK with natural PK (name, tld)
- Adds label column (name without TLD suffix)
- Partitions by TLD (net, org, info)
- Installs pg_trgm + fuzzystrmatch extensions
- Creates GIN trigram index on label
- Drops domain_observation (0 rows, never used)
- Removes status, deleted_at, created_at, updated_at columns

Revision ID: 005_domain_redesign
Revises: 004_drop_dup_ix_domain_name
Create Date: 2026-03-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005_domain_redesign"
down_revision: Union[str, None] = "004_drop_dup_ix_domain_name"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Install extensions ────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch")

    # ── 2. Create new partitioned table ──────────────────────
    op.execute("""
        CREATE TABLE domain_new (
            name          VARCHAR(253) NOT NULL,
            tld           VARCHAR(24)  NOT NULL,
            label         TEXT         NOT NULL,
            first_seen_at TIMESTAMPTZ  NOT NULL,
            last_seen_at  TIMESTAMPTZ  NOT NULL,
            PRIMARY KEY (name, tld)
        ) PARTITION BY LIST (tld)
    """)

    # ── 3. Create partitions for existing TLDs ───────────────
    op.execute("CREATE TABLE domain_new_net  PARTITION OF domain_new FOR VALUES IN ('net')")
    op.execute("CREATE TABLE domain_new_org  PARTITION OF domain_new FOR VALUES IN ('org')")
    op.execute("CREATE TABLE domain_new_info PARTITION OF domain_new FOR VALUES IN ('info')")

    # ── 4. Migrate data (compute label from name - tld) ──────
    op.execute("""
        INSERT INTO domain_new (name, tld, label, first_seen_at, last_seen_at)
        SELECT
            name,
            tld,
            left(name, length(name) - length(tld) - 1),
            first_seen_at,
            last_seen_at
        FROM domain
    """)

    # ── 5. Create indexes on new table ───────────────────────
    op.execute("CREATE INDEX ix_domain_label_trgm ON domain_new USING gin (label gin_trgm_ops)")
    op.execute("CREATE INDEX ix_domain_first_seen ON domain_new (tld, first_seen_at DESC)")
    op.execute("CREATE INDEX ix_domain_last_seen  ON domain_new (tld, last_seen_at DESC)")

    # ── 6. Drop domain_observation (0 rows) ──────────────────
    op.execute("DROP TABLE IF EXISTS domain_observation")

    # ── 7. Rename tables ─────────────────────────────────────
    op.execute("ALTER TABLE domain RENAME TO domain_old")
    op.execute("ALTER TABLE domain_new RENAME TO domain")

    # ── 8. Rename partitions for consistency ─────────────────
    op.execute("ALTER TABLE domain_new_net  RENAME TO domain_net")
    op.execute("ALTER TABLE domain_new_org  RENAME TO domain_org")
    op.execute("ALTER TABLE domain_new_info RENAME TO domain_info")


def downgrade() -> None:
    # Reverse: rename back, recreate old structure
    op.execute("ALTER TABLE domain RENAME TO domain_partitioned")

    # Recreate original domain table
    op.execute("""
        CREATE TABLE domain (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name          VARCHAR(253) UNIQUE NOT NULL,
            tld           VARCHAR(24) NOT NULL,
            status        VARCHAR(16) NOT NULL DEFAULT 'active',
            first_seen_at TIMESTAMPTZ NOT NULL,
            last_seen_at  TIMESTAMPTZ NOT NULL,
            deleted_at    TIMESTAMPTZ,
            created_at    TIMESTAMPTZ NOT NULL,
            updated_at    TIMESTAMPTZ NOT NULL
        )
    """)

    # Migrate data back
    op.execute("""
        INSERT INTO domain (name, tld, status, first_seen_at, last_seen_at, created_at, updated_at)
        SELECT name, tld, 'active', first_seen_at, last_seen_at, first_seen_at, last_seen_at
        FROM domain_partitioned
    """)

    # Recreate indexes
    op.execute("CREATE INDEX ix_domain_status_tld ON domain (status, tld)")
    op.execute("CREATE INDEX ix_domain_tld_last_seen ON domain (tld, last_seen_at DESC)")

    # Recreate domain_observation
    op.execute("""
        CREATE TABLE domain_observation (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            domain_id         UUID NOT NULL REFERENCES domain(id) ON DELETE CASCADE,
            source            VARCHAR(32) NOT NULL,
            tld               VARCHAR(24) NOT NULL,
            observed_at       TIMESTAMPTZ NOT NULL,
            ingestion_run_id  UUID REFERENCES ingestion_run(id) ON DELETE SET NULL,
            UNIQUE (domain_id, source, observed_at, ingestion_run_id)
        )
    """)
    op.execute("CREATE INDEX ix_domain_obs_tld_observed ON domain_observation (tld, observed_at DESC)")
    op.execute("CREATE INDEX ix_domain_obs_domain_id ON domain_observation (domain_id)")
    op.execute("CREATE INDEX ix_domain_obs_run_id ON domain_observation (ingestion_run_id)")

    op.execute("DROP TABLE domain_partitioned")
