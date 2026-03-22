"""Create similarity analysis tables: monitored_brand, similarity_scan_cursor, similarity_match

Revision ID: 006_similarity_tables
Revises: 005_domain_redesign
Create Date: 2026-03-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006_similarity_tables"
down_revision: Union[str, None] = "005_domain_redesign"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. monitored_brand ─────────────────────────────────
    op.execute("""
        CREATE TABLE monitored_brand (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organization_id UUID NOT NULL,
            brand_name      VARCHAR(253) NOT NULL,
            brand_label     VARCHAR(253) NOT NULL,
            keywords        TEXT[] NOT NULL DEFAULT '{}',
            tld_scope       TEXT[] NOT NULL DEFAULT '{}',
            is_active       BOOLEAN NOT NULL DEFAULT true,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_brand_org_name
        ON monitored_brand (organization_id, brand_name)
    """)
    op.execute("CREATE INDEX ix_brand_active ON monitored_brand (is_active)")

    # ── 2. similarity_scan_cursor ──────────────────────────
    op.execute("""
        CREATE TABLE similarity_scan_cursor (
            brand_id         UUID NOT NULL REFERENCES monitored_brand(id) ON DELETE CASCADE,
            tld              VARCHAR(24) NOT NULL,
            scan_phase       VARCHAR(16) NOT NULL DEFAULT 'initial',
            status           VARCHAR(16) NOT NULL DEFAULT 'pending',
            watermark_at     TIMESTAMPTZ,
            resume_after     VARCHAR(253),
            domains_scanned  BIGINT NOT NULL DEFAULT 0,
            domains_matched  BIGINT NOT NULL DEFAULT 0,
            started_at       TIMESTAMPTZ,
            finished_at      TIMESTAMPTZ,
            error_message    TEXT,
            updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (brand_id, tld)
        )
    """)
    op.execute("CREATE INDEX ix_cursor_status ON similarity_scan_cursor (status)")

    # ── 3. similarity_match ────────────────────────────────
    op.execute("""
        CREATE TABLE similarity_match (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            brand_id          UUID NOT NULL REFERENCES monitored_brand(id) ON DELETE CASCADE,
            domain_name       VARCHAR(253) NOT NULL,
            tld               VARCHAR(24) NOT NULL,
            label             TEXT NOT NULL,
            score_final       DOUBLE PRECISION NOT NULL,
            score_trigram     DOUBLE PRECISION,
            score_levenshtein DOUBLE PRECISION,
            score_brand_hit   DOUBLE PRECISION,
            score_keyword     DOUBLE PRECISION,
            score_homograph   DOUBLE PRECISION,
            reasons           TEXT[] NOT NULL,
            risk_level        VARCHAR(16) NOT NULL,
            first_detected_at TIMESTAMPTZ NOT NULL,
            domain_first_seen TIMESTAMPTZ NOT NULL,
            status            VARCHAR(16) NOT NULL DEFAULT 'new',
            reviewed_by       UUID,
            reviewed_at       TIMESTAMPTZ,
            notes             TEXT
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_match_brand_domain
        ON similarity_match (brand_id, domain_name)
    """)
    op.execute("""
        CREATE INDEX ix_match_brand_risk
        ON similarity_match (brand_id, risk_level, score_final DESC)
    """)
    op.execute("""
        CREATE INDEX ix_match_brand_status
        ON similarity_match (brand_id, status)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS similarity_match")
    op.execute("DROP TABLE IF EXISTS similarity_scan_cursor")
    op.execute("DROP TABLE IF EXISTS monitored_brand")
