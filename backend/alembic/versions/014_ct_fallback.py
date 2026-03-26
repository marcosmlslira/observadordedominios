"""Add CT fallback bulk job persistence.

Revision ID: 014_ct_fallback
Revises: 013_similarity_enrich
Create Date: 2026-03-25 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "014_ct_fallback"
down_revision = "013_similarity_enrich"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ct_bulk_job",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("requested_tlds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("resolved_tlds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("priority_tlds", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("initiated_by", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("total_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pending_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("running_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("done_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_chunks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_raw_domains", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("total_inserted_domains", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ct_bulk_job_status_created",
        "ct_bulk_job",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "ct_bulk_chunk",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_chunk_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_tld", sa.String(length=24), nullable=False),
        sa.Column("chunk_key", sa.String(length=160), nullable=False),
        sa.Column("query_pattern", sa.String(length=255), nullable=False),
        sa.Column("prefix", sa.String(length=24), nullable=False, server_default=""),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error_type", sa.String(length=64), nullable=True),
        sa.Column("last_error_excerpt", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_domains", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("inserted_domains", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["ct_bulk_job.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_chunk_id"], ["ct_bulk_chunk.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("job_id", "chunk_key", name="uq_ct_bulk_chunk_job_key"),
    )
    op.create_index("ix_ct_bulk_chunk_job_status", "ct_bulk_chunk", ["job_id", "status"], unique=False)
    op.create_index("ix_ct_bulk_chunk_job_retry", "ct_bulk_chunk", ["job_id", "next_retry_at"], unique=False)
    op.create_index("ix_ct_bulk_chunk_tld_status", "ct_bulk_chunk", ["target_tld", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ct_bulk_chunk_tld_status", table_name="ct_bulk_chunk")
    op.drop_index("ix_ct_bulk_chunk_job_retry", table_name="ct_bulk_chunk")
    op.drop_index("ix_ct_bulk_chunk_job_status", table_name="ct_bulk_chunk")
    op.drop_table("ct_bulk_chunk")
    op.drop_index("ix_ct_bulk_job_status_created", table_name="ct_bulk_job")
    op.drop_table("ct_bulk_job")
