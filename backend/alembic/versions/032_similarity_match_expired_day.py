"""Add domain_expired_day to similarity_match for domain expiration tracking.

Revision ID: 032_similarity_match_expired_day
Revises: 031_domain_adr001_redesign
Create Date: 2026-04-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "032_similarity_match_expired_day"
down_revision = "031_domain_adr001_redesign"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "similarity_match",
        sa.Column("domain_expired_day", sa.Integer(), nullable=True),
    )
    # Partial index — only rows where the domain has expired, which is a minority.
    op.execute(
        """
        CREATE INDEX ix_match_expired
        ON similarity_match (domain_expired_day)
        WHERE domain_expired_day IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_match_expired")
    op.drop_column("similarity_match", "domain_expired_day")
