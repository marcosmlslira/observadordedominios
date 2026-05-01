"""Drop legacy zone_file_artifact table and related FK on ingestion_run.

The CZDS zone-file artifact table was used by the legacy sync_czds_tld
pipeline. The new orchestrator (ingestion/ package) does not write to it.
After removing the legacy code, the table and the ingestion_run.artifact_id
column are inert and we drop them here to keep the schema lean.

Revision ID: 042_drop_legacy_zone_file_artifact
Revises: 041_tld_daily_policy_status_view
Create Date: 2026-04-30
"""

from __future__ import annotations

from alembic import op

revision = "042_drop_legacy_zone_file_artifact"
down_revision = "041_tld_daily_policy_status_view"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_run_artifact_id", table_name="ingestion_run")
    op.drop_constraint(
        "ingestion_run_artifact_id_fkey",
        "ingestion_run",
        type_="foreignkey",
    )
    op.drop_column("ingestion_run", "artifact_id")
    op.drop_table("zone_file_artifact")


def downgrade() -> None:
    # Recreating the legacy table is not useful: the code that populated
    # it has been removed. Downgrade is intentionally a no-op.
    pass
