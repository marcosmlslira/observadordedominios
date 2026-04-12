"""Add event-sourced monitoring foundation tables.

Creates: monitoring_cycle, monitoring_event, brand_domain_health, match_state_snapshot
Alters: similarity_match (adds 5 new columns)

Revision ID: 026_monitoring_foundation
Revises: 025_domain_staging_table
Create Date: 2026-04-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID

revision = "026_monitoring_foundation"
down_revision = "025_domain_staging_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── monitoring_cycle ──────────────────────────────────────
    op.create_table(
        "monitoring_cycle",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_id", UUID(as_uuid=True),
                  sa.ForeignKey("monitored_brand.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("cycle_date", sa.Date, nullable=False),
        sa.Column("cycle_type", sa.String(16), nullable=False, server_default="scheduled"),
        # Stage: health
        sa.Column("health_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("health_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health_finished_at", sa.DateTime(timezone=True), nullable=True),
        # Stage: scan
        sa.Column("scan_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("scan_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scan_job_id", UUID(as_uuid=True),
                  sa.ForeignKey("similarity_scan_job.id", ondelete="SET NULL"), nullable=True),
        # Stage: enrichment
        sa.Column("enrichment_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("enrichment_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrichment_finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrichment_budget", sa.Integer, nullable=False, server_default="0"),
        sa.Column("enrichment_total", sa.Integer, nullable=False, server_default="0"),
        # Summary counters
        sa.Column("new_matches_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("escalated_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("dismissed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("threats_detected", sa.Integer, nullable=False, server_default="0"),
        # Timestamps
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_unique_constraint("uq_cycle_brand_date", "monitoring_cycle", ["brand_id", "cycle_date"])
    op.create_index("ix_cycle_brand_date", "monitoring_cycle", ["brand_id", "cycle_date"])

    # ── monitoring_event ──────────────────────────────────────
    op.create_table(
        "monitoring_event",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("brand_id", UUID(as_uuid=True),
                  sa.ForeignKey("monitored_brand.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cycle_id", UUID(as_uuid=True),
                  sa.ForeignKey("monitoring_cycle.id", ondelete="SET NULL"), nullable=True),
        sa.Column("match_id", UUID(as_uuid=True),
                  sa.ForeignKey("similarity_match.id", ondelete="CASCADE"), nullable=True),
        sa.Column("brand_domain_id", UUID(as_uuid=True),
                  sa.ForeignKey("monitored_brand_domain.id", ondelete="CASCADE"), nullable=True),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("event_source", sa.String(32), nullable=False),
        sa.Column("tool_name", sa.String(48), nullable=True),
        sa.Column("tool_version", sa.String(16), nullable=True),
        sa.Column("result_data", JSONB, nullable=False, server_default="{}"),
        sa.Column("signals", JSONB, nullable=True),
        sa.Column("score_snapshot", JSONB, nullable=True),
        sa.Column("ttl_expires_at", sa.DateTime(timezone=True), nullable=True),
        # No updated_at — monitoring_event is immutable by design
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_check_constraint(
        "chk_event_target",
        "monitoring_event",
        "(match_id IS NOT NULL AND brand_domain_id IS NULL) OR "
        "(match_id IS NULL AND brand_domain_id IS NOT NULL)",
    )
    op.create_index("ix_event_match", "monitoring_event", ["match_id", "created_at"])
    op.create_index("ix_event_brand_domain", "monitoring_event", ["brand_domain_id", "created_at"])
    op.create_index("ix_event_brand_cycle", "monitoring_event", ["brand_id", "cycle_id"])
    op.create_index("ix_event_tool_latest", "monitoring_event",
                    ["match_id", "tool_name", "created_at"])

    # ── brand_domain_health ───────────────────────────────────
    op.create_table(
        "brand_domain_health",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("brand_domain_id", UUID(as_uuid=True),
                  sa.ForeignKey("monitored_brand_domain.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("brand_id", UUID(as_uuid=True),
                  sa.ForeignKey("monitored_brand.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("overall_status", sa.String(16), nullable=False, server_default="unknown"),
        sa.Column("dns_ok", sa.Boolean, nullable=True),
        sa.Column("ssl_ok", sa.Boolean, nullable=True),
        sa.Column("ssl_days_remaining", sa.Integer, nullable=True),
        sa.Column("email_security_ok", sa.Boolean, nullable=True),
        sa.Column("spoofing_risk", sa.String(16), nullable=True),
        sa.Column("headers_score", sa.String(16), nullable=True),
        sa.Column("takeover_risk", sa.Boolean, nullable=True),
        sa.Column("blacklisted", sa.Boolean, nullable=True),
        sa.Column("safe_browsing_hit", sa.Boolean, nullable=True),
        sa.Column("urlhaus_hit", sa.Boolean, nullable=True),
        sa.Column("phishtank_hit", sa.Boolean, nullable=True),
        sa.Column("suspicious_content", sa.Boolean, nullable=True),
        sa.Column("state_fingerprint", sa.String(64), nullable=True),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_event_ids", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_health_brand", "brand_domain_health", ["brand_id"])

    # ── match_state_snapshot ──────────────────────────────────
    op.create_table(
        "match_state_snapshot",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("match_id", UUID(as_uuid=True),
                  sa.ForeignKey("similarity_match.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("brand_id", UUID(as_uuid=True),
                  sa.ForeignKey("monitored_brand.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("derived_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("derived_bucket", sa.String(32), nullable=False, server_default="watchlist"),
        sa.Column("derived_risk", sa.String(16), nullable=False, server_default="low"),
        sa.Column("derived_disposition", sa.String(32), nullable=True),
        sa.Column("active_signals", JSONB, nullable=False, server_default="[]"),
        sa.Column("signal_codes", ARRAY(sa.String), nullable=True),
        sa.Column("llm_assessment", JSONB, nullable=True),
        sa.Column("llm_event_id", UUID(as_uuid=True), nullable=True),
        sa.Column("llm_source_fingerprint", sa.String(64), nullable=True),
        sa.Column("state_fingerprint", sa.String(64), nullable=False, server_default=""),
        sa.Column("events_hash", sa.String(64), nullable=True),
        sa.Column("last_derived_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_snapshot_brand_bucket", "match_state_snapshot",
                    ["brand_id", "derived_bucket", "derived_score"])
    op.create_index("ix_snapshot_brand_risk", "match_state_snapshot",
                    ["brand_id", "derived_risk", "derived_score"])
    # Partial index for needs_llm_assessment() — avoids full table scan in assessment_worker
    op.create_index(
        "ix_snapshot_needs_llm", "match_state_snapshot", ["brand_id"],
        postgresql_where=sa.text("llm_source_fingerprint IS DISTINCT FROM state_fingerprint"),
    )

    # ── similarity_match: new columns ─────────────────────────
    op.add_column("similarity_match",
                  sa.Column("state_fingerprint", sa.String(64), nullable=True))
    op.add_column("similarity_match",
                  sa.Column("last_fingerprint_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("similarity_match",
                  sa.Column("auto_disposition", sa.String(32), nullable=True))
    op.add_column("similarity_match",
                  sa.Column("auto_disposition_reason", sa.Text, nullable=True))
    op.add_column("similarity_match",
                  sa.Column("enrichment_budget_rank", sa.Integer, nullable=True))


def downgrade() -> None:
    op.drop_column("similarity_match", "enrichment_budget_rank")
    op.drop_column("similarity_match", "auto_disposition_reason")
    op.drop_column("similarity_match", "auto_disposition")
    op.drop_column("similarity_match", "last_fingerprint_at")
    op.drop_column("similarity_match", "state_fingerprint")

    op.drop_table("match_state_snapshot")
    op.drop_table("brand_domain_health")
    op.drop_table("monitoring_event")
    op.drop_table("monitoring_cycle")
