"""Initial CZDS ingestion tables and seed data

Revision ID: 001_initial_czds
Revises:
Create Date: 2026-03-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = "001_initial_czds"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── zone_file_artifact (must exist before ingestion_run FK) ──
    op.create_table(
        "zone_file_artifact",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("tld", sa.String(24), nullable=False),
        sa.Column("bucket", sa.String(128), nullable=False),
        sa.Column("object_key", sa.Text, nullable=False),
        sa.Column("etag", sa.String(128), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_artifact_tld_downloaded",
        "zone_file_artifact",
        ["tld", sa.text("downloaded_at DESC")],
    )

    # ── ingestion_run ────────────────────────────────────────
    op.create_table(
        "ingestion_run",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("tld", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "artifact_id",
            UUID(as_uuid=True),
            sa.ForeignKey("zone_file_artifact.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("domains_seen", sa.BigInteger, server_default="0"),
        sa.Column("domains_inserted", sa.BigInteger, server_default="0"),
        sa.Column("domains_reactivated", sa.BigInteger, server_default="0"),
        sa.Column("domains_deleted", sa.BigInteger, server_default="0"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_run_source_tld_started",
        "ingestion_run",
        ["source", "tld", sa.text("started_at DESC")],
    )

    # ── domain ───────────────────────────────────────────────
    op.create_table(
        "domain",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(253), unique=True, nullable=False),
        sa.Column("tld", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_domain_name", "domain", ["name"])
    op.create_index(
        "ix_domain_tld_last_seen",
        "domain",
        ["tld", sa.text("last_seen_at DESC")],
    )
    op.create_index("ix_domain_status_tld", "domain", ["status", "tld"])

    # ── domain_observation ───────────────────────────────────
    op.create_table(
        "domain_observation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "domain_id",
            UUID(as_uuid=True),
            sa.ForeignKey("domain.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("tld", sa.String(24), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "ingestion_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("ingestion_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_unique_constraint(
        "uq_domain_obs_natural",
        "domain_observation",
        ["domain_id", "source", "observed_at", "ingestion_run_id"],
    )
    op.create_index(
        "ix_domain_obs_tld_observed",
        "domain_observation",
        ["tld", sa.text("observed_at DESC")],
    )

    # ── ingestion_checkpoint ─────────────────────────────────
    op.create_table(
        "ingestion_checkpoint",
        sa.Column("source", sa.String(32), primary_key=True),
        sa.Column("tld", sa.String(24), primary_key=True),
        sa.Column("last_successful_run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("last_successful_run_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── czds_tld_policy ──────────────────────────────────────
    op.create_table(
        "czds_tld_policy",
        sa.Column("tld", sa.String(24), primary_key=True),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="100"),
        sa.Column("cooldown_hours", sa.Integer, nullable=False, server_default="24"),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── Seed data: initial TLD policies ──────────────────────
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    op.execute(
        f"""
        INSERT INTO czds_tld_policy (tld, is_enabled, priority, cooldown_hours, notes, updated_at)
        VALUES
            ('net',  true, 1, 24, 'Phase 1 – lightweight TLD', '{now}'),
            ('org',  true, 2, 24, 'Phase 1 – lightweight TLD', '{now}'),
            ('info', true, 3, 24, 'Phase 1 – lightweight TLD', '{now}')
        ON CONFLICT (tld) DO NOTHING;
        """
    )


def downgrade() -> None:
    op.drop_table("czds_tld_policy")
    op.drop_table("ingestion_checkpoint")
    op.drop_table("domain_observation")
    op.drop_table("domain")
    op.drop_table("ingestion_run")
    op.drop_table("zone_file_artifact")
