"""Add ordering_mode to ingestion_source_config.

Controls how the CZDS worker orders TLDs for processing.

Revision ID: 028_ingestion_ordering_mode
Revises: 027_brand_trusted_registrants
Create Date: 2026-04-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "028_ingestion_ordering_mode"
down_revision = "027_brand_trusted_registrants"
branch_labels = None
depends_on = None

_VALID_MODES = ("corpus_first", "priority_first", "alphabetical")
_CHECK_CONSTRAINT = f"ordering_mode IN ({', '.join(repr(m) for m in _VALID_MODES)})"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "ALTER TABLE ingestion_source_config "
            "ADD COLUMN IF NOT EXISTS ordering_mode VARCHAR(32) "
            "NOT NULL DEFAULT 'corpus_first';"
        )
    )
    conn.execute(
        sa.text(
            "ALTER TABLE ingestion_source_config "
            "DROP CONSTRAINT IF EXISTS ck_ingestion_source_config_ordering_mode;"
        )
    )
    conn.execute(
        sa.text(
            "ALTER TABLE ingestion_source_config "
            f"ADD CONSTRAINT ck_ingestion_source_config_ordering_mode "
            f"CHECK ({_CHECK_CONSTRAINT});"
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "ALTER TABLE ingestion_source_config "
            "DROP CONSTRAINT IF EXISTS ck_ingestion_source_config_ordering_mode;"
        )
    )
    conn.execute(
        sa.text(
            "ALTER TABLE ingestion_source_config "
            "DROP COLUMN IF EXISTS ordering_mode;"
        )
    )
