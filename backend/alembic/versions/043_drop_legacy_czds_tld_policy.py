"""Drop legacy czds_tld_policy table.

The czds_tld_policy table was used by the legacy CZDS pipeline together
with sync_czds_tld and the deprecated /v1/czds router. The new orchestrator
(ingestion/ package) governs TLD policy through ingestion_tld_policy
(model IngestionTldPolicy), making czds_tld_policy fully orphan after the
legacy code removal. We drop it here to keep the schema lean.

Migrations 008, 011, 021, 022 historically modified this table; none of
that prevents the drop.

Revision ID: 043_drop_legacy_czds_tld_policy
Revises: 042_drop_legacy_zone_file_artifact
Create Date: 2026-05-01
"""

from __future__ import annotations

from alembic import op

revision = "043_drop_legacy_czds_tld_policy"
down_revision = "042_drop_legacy_zone_file_artifact"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("czds_tld_policy")


def downgrade() -> None:
    # Recreating the legacy table is not useful: the code that populated
    # it has been removed. Downgrade is intentionally a no-op.
    pass
