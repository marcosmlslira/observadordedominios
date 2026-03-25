"""Add CZDS TLD quarantine metadata.

Revision ID: 011_czds_tld_quarantine
Revises: 010_profile_phase1
Create Date: 2026-03-24 22:20:00
"""

from alembic import op
import sqlalchemy as sa


revision = "011_czds_tld_quarantine"
down_revision = "010_profile_phase1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "czds_tld_policy",
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "czds_tld_policy",
        sa.Column("last_error_code", sa.Integer(), nullable=True),
    )
    op.add_column(
        "czds_tld_policy",
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "czds_tld_policy",
        sa.Column("suspended_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("czds_tld_policy", "failure_count", server_default=None)


def downgrade() -> None:
    op.drop_column("czds_tld_policy", "suspended_until")
    op.drop_column("czds_tld_policy", "last_error_at")
    op.drop_column("czds_tld_policy", "last_error_code")
    op.drop_column("czds_tld_policy", "failure_count")
