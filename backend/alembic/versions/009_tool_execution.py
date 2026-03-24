"""Add tool_execution table for free tools.

Revision ID: 009_tool_execution
Revises: 008_expand_czds_scope
Create Date: 2026-03-24

"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision: str = "009_tool_execution"
down_revision: Union[str, None] = "008_expand_czds_scope"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tool_execution",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", UUID(as_uuid=True), nullable=False),
        sa.Column("tool_type", sa.String(32), nullable=False),
        sa.Column("target", sa.String(253), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("result_data", JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("triggered_by", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("quick_analysis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_index("ix_tool_exec_org_created", "tool_execution", ["organization_id", "created_at"])
    op.create_index("ix_tool_exec_org_type_created", "tool_execution", ["organization_id", "tool_type", "created_at"])
    op.create_index("ix_tool_exec_org_target", "tool_execution", ["organization_id", "target"])
    op.execute(
        "CREATE INDEX ix_tool_exec_quick_analysis ON tool_execution (quick_analysis_id) "
        "WHERE quick_analysis_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_tool_exec_quick_analysis", table_name="tool_execution")
    op.drop_index("ix_tool_exec_org_target", table_name="tool_execution")
    op.drop_index("ix_tool_exec_org_type_created", table_name="tool_execution")
    op.drop_index("ix_tool_exec_org_created", table_name="tool_execution")
    op.drop_table("tool_execution")
