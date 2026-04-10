"""Add ingestion_source_config and ingestion_tld_policy tables.

Revision ID: 020_ingestion_config_tld_policy
Revises: 019_drop_ct_bulk
Create Date: 2026-04-10 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "020_ingestion_config_tld_policy"
down_revision = "019_drop_ct_bulk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_source_config",
        sa.Column("source", sa.String(32), primary_key=True),
        sa.Column("cron_expression", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "ingestion_tld_policy",
        sa.Column("source", sa.String(32), primary_key=True),
        sa.Column("tld", sa.String(24), primary_key=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Seed default cron schedules (mirrors env var defaults so workers always find a row)
    op.execute(
        sa.text(
            """
            INSERT INTO ingestion_source_config (source, cron_expression)
            VALUES
                ('czds',        '0 7 * * *'),
                ('certstream',  '0 5 * * *'),
                ('openintel',   '0 2 * * *')
            ON CONFLICT (source) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_table("ingestion_tld_policy")
    op.drop_table("ingestion_source_config")
