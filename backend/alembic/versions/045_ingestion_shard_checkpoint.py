"""Per-shard checkpointing for the ingestion bulk loader.

Until now a long ingestion that failed mid-flight (e.g. czds/xyz with 128
shards) re-processed every shard from scratch on retry. With this table the
loader records each shard that finished its INSERT in the partition; on a
subsequent attempt for the same (source, tld, snapshot_date) those shard keys
are skipped.

The lookup window is intentionally short (24h) — checkpoints from earlier
snapshots are irrelevant and would only bloat the queries. A separate cleanup
task may prune old rows; not in scope here.

Revision ID: 045_ingestion_shard_checkpoint
Revises: 044_tld_policy_stale_timeout
Create Date: 2026-05-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "045_ingestion_shard_checkpoint"
down_revision = "044_tld_policy_stale_timeout"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ingestion_shard_checkpoint",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ingestion_run.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("tld", sa.String(24), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("partition", sa.String(64), nullable=False),
        sa.Column("shard_key", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("rows_loaded", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "loaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("run_id", "shard_key", "partition", name="uq_shard_checkpoint_run_key"),
    )
    op.create_index(
        "ix_shard_checkpoint_lookup",
        "ingestion_shard_checkpoint",
        ["source", "tld", "snapshot_date", "partition", "status"],
    )
    op.create_index(
        "ix_shard_checkpoint_run",
        "ingestion_shard_checkpoint",
        ["run_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_shard_checkpoint_run", table_name="ingestion_shard_checkpoint")
    op.drop_index("ix_shard_checkpoint_lookup", table_name="ingestion_shard_checkpoint")
    op.drop_table("ingestion_shard_checkpoint")
