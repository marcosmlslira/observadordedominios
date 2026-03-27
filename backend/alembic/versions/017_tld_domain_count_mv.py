"""Create materialized view tld_domain_count_mv

Revision ID: 017_tld_domain_count_mv
Revises: 016_brand_alert_webhook
Create Date: 2026-03-27
"""

from alembic import op

revision = "017_tld_domain_count_mv"
down_revision = "016_brand_alert_webhook"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # WITH NO DATA: creates structure instantly, no full table scan at migration time.
    # The view is populated on the next CZDS worker cycle via REFRESH CONCURRENTLY.
    op.execute("""
        CREATE MATERIALIZED VIEW IF NOT EXISTS tld_domain_count_mv AS
        SELECT tld, COUNT(*) AS count
        FROM domain
        GROUP BY tld
        ORDER BY count DESC
        WITH NO DATA
    """)
    # Unique index required for REFRESH MATERIALIZED VIEW CONCURRENTLY
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS tld_domain_count_mv_tld_idx
        ON tld_domain_count_mv (tld)
    """)


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS tld_domain_count_mv")
