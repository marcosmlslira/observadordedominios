"""Add alert_webhook_url to monitored_brand.

Revision ID: 016_brand_alert_webhook
Revises: 015_similarity_scan_jobs
Create Date: 2026-03-26 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "016_brand_alert_webhook"
down_revision = "015_similarity_scan_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monitored_brand",
        sa.Column("alert_webhook_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("monitored_brand", "alert_webhook_url")
