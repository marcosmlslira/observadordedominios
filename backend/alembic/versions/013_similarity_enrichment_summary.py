"""Add enrichment summary fields to similarity matches.

Revision ID: 013_similarity_enrich
Revises: 012_similarity_actionability
Create Date: 2026-03-25
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "013_similarity_enrich"
down_revision = "012_similarity_actionability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("similarity_match", sa.Column("enrichment_status", sa.String(length=16), nullable=True))
    op.add_column("similarity_match", sa.Column("enrichment_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("similarity_match", sa.Column("last_enriched_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("similarity_match", "last_enriched_at")
    op.drop_column("similarity_match", "enrichment_summary")
    op.drop_column("similarity_match", "enrichment_status")
