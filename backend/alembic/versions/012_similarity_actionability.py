"""Add actionability fields to similarity matches.

Revision ID: 012_similarity_actionability
Revises: 011_czds_tld_quarantine
Create Date: 2026-03-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "012_similarity_actionability"
down_revision = "011_czds_tld_quarantine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("similarity_match", sa.Column("actionability_score", sa.Float(), nullable=True))
    op.add_column("similarity_match", sa.Column("attention_bucket", sa.String(length=32), nullable=True))
    op.add_column("similarity_match", sa.Column("attention_reasons", postgresql.ARRAY(sa.Text()), nullable=True))
    op.add_column("similarity_match", sa.Column("recommended_action", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE similarity_match
        SET actionability_score = score_final,
            attention_bucket = CASE
                WHEN risk_level IN ('high', 'critical') THEN 'defensive_gap'
                WHEN risk_level = 'medium' THEN 'watchlist'
                ELSE 'watchlist'
            END,
            attention_reasons = ARRAY['legacy_backfill'],
            recommended_action = CASE
                WHEN risk_level IN ('high', 'critical')
                    THEN 'Review manually and decide whether this is an operational threat or defensive gap.'
                ELSE 'Keep in watchlist until enrichment or review adds priority.'
            END
        """
    )

    op.alter_column("similarity_match", "actionability_score", nullable=False)
    op.alter_column("similarity_match", "attention_bucket", nullable=False)
    op.alter_column("similarity_match", "attention_reasons", nullable=False)
    op.alter_column("similarity_match", "recommended_action", nullable=False)

    op.execute(
        """
        CREATE INDEX ix_match_brand_attention
        ON similarity_match (brand_id, attention_bucket, actionability_score DESC)
        """
    )


def downgrade() -> None:
    op.drop_index("ix_match_brand_attention", table_name="similarity_match")
    op.drop_column("similarity_match", "recommended_action")
    op.drop_column("similarity_match", "attention_reasons")
    op.drop_column("similarity_match", "attention_bucket")
    op.drop_column("similarity_match", "actionability_score")
