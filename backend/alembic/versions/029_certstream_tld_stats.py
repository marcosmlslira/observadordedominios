"""Add per-TLD stats columns to ingestion_tld_policy for CertStream tracking.

Tracks cumulative domains inserted and last activity per TLD.

Revision ID: 029_certstream_tld_stats
Revises: 028_ingestion_ordering_mode
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "029_certstream_tld_stats"
down_revision = "028_ingestion_ordering_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ingestion_tld_policy",
        sa.Column("domains_inserted", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ingestion_tld_policy",
        sa.Column("last_seen_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ingestion_tld_policy", "last_seen_at")
    op.drop_column("ingestion_tld_policy", "domains_inserted")
