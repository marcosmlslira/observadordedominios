"""Add trusted_registrants JSONB column to monitored_brand.

Stores per-brand lists of trusted CNPJ/CPF identifiers, org name variants,
and contact email domains. Used to detect and auto-classify self-owned domains
(e.g. subsidiary or related-brand domains) that would otherwise be flagged as
threats due to ccTLD WHOIS parsing limitations (registro.br, etc.).

Revision ID: 027_brand_trusted_registrants
Revises: 026_monitoring_foundation
Create Date: 2026-04-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "027_brand_trusted_registrants"
down_revision = "026_monitoring_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "monitored_brand",
        sa.Column("trusted_registrants", JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("monitored_brand", "trusted_registrants")
