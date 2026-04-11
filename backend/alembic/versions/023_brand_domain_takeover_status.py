"""Add takeover_status to monitored_brand_domain.

Revision ID: 023_brand_domain_takeover_status
Revises: 022_complete_tld_lists
Create Date: 2026-04-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "023_brand_domain_takeover_status"
down_revision = "022_complete_tld_lists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monitored_brand_domain",
        sa.Column("takeover_status", sa.String(16), nullable=True),
    )
    # Valores: 'safe', 'vulnerable', 'unknown', NULL (não verificado)


def downgrade() -> None:
    op.drop_column("monitored_brand_domain", "takeover_status")
