"""Add durable similarity scan jobs and match metadata.

Revision ID: 015_similarity_scan_jobs
Revises: 014_ct_fallback
Create Date: 2026-03-26 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "015_similarity_scan_jobs"
down_revision = "014_ct_fallback"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "similarity_scan_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("brand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_tld", sa.String(length=24), nullable=True),
        sa.Column("effective_tlds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tld_results", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("force_full", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("initiated_by", sa.String(length=128), nullable=True),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["monitored_brand.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_similarity_scan_job_status_queue",
        "similarity_scan_job",
        ["status", "queued_at"],
        unique=False,
    )
    op.create_index(
        "ix_similarity_scan_job_brand_created",
        "similarity_scan_job",
        ["brand_id", "created_at"],
        unique=False,
    )

    op.add_column("similarity_match", sa.Column("ownership_classification", sa.String(length=32), nullable=True))
    op.add_column("similarity_match", sa.Column("self_owned", sa.Boolean(), nullable=True))
    op.add_column("similarity_match", sa.Column("disposition", sa.String(length=32), nullable=True))
    op.add_column("similarity_match", sa.Column("confidence", sa.Float(), nullable=True))
    op.add_column("similarity_match", sa.Column("delivery_risk", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("similarity_match", "delivery_risk")
    op.drop_column("similarity_match", "confidence")
    op.drop_column("similarity_match", "disposition")
    op.drop_column("similarity_match", "self_owned")
    op.drop_column("similarity_match", "ownership_classification")
    op.drop_index("ix_similarity_scan_job_brand_created", table_name="similarity_scan_job")
    op.drop_index("ix_similarity_scan_job_status_queue", table_name="similarity_scan_job")
    op.drop_table("similarity_scan_job")
