"""Add llm_assessment JSONB column to similarity_match

Revision ID: 018_llm_assessment
Revises: 017_tld_domain_count_mv
Create Date: 2026-03-28
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "018_llm_assessment"
down_revision = "017_tld_domain_count_mv"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "similarity_match",
        sa.Column("llm_assessment", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("similarity_match", "llm_assessment")
