"""Seed ingestion_tld_policy from czds_tld_policy and default OpenINTEL TLDs.

Revision ID: 021_seed_ingestion_tld_policy
Revises: 020_ingestion_config_tld_policy
Create Date: 2026-04-10 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "021_seed_ingestion_tld_policy"
down_revision = "020_ingestion_config_tld_policy"
branch_labels = None
depends_on = None

# Default TLDs for OpenINTEL (mirrors settings.OPENINTEL_ENABLED_TLDS)
_OPENINTEL_DEFAULT_TLDS = ["fr", "ch", "se", "sk", "ee", "li", "nu"]


def upgrade() -> None:
    # Seed CZDS TLDs from czds_tld_policy (preserves is_enabled state)
    op.execute(
        sa.text(
            """
            INSERT INTO ingestion_tld_policy (source, tld, is_enabled)
            SELECT 'czds', tld, is_enabled
            FROM czds_tld_policy
            ON CONFLICT (source, tld) DO NOTHING
            """
        )
    )

    # Seed OpenINTEL default TLDs (enabled by default)
    tld_values = ", ".join(f"('openintel', '{tld}', true)" for tld in _OPENINTEL_DEFAULT_TLDS)
    op.execute(
        sa.text(
            f"""
            INSERT INTO ingestion_tld_policy (source, tld, is_enabled)
            VALUES {tld_values}
            ON CONFLICT (source, tld) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM ingestion_tld_policy WHERE source IN ('czds', 'openintel')")
    )
