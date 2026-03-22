"""Add gen_random_uuid() server_default to domain.id

Revision ID: 003_domain_id_server_default
Revises: 002_indexes_artifact_ts
Create Date: 2026-03-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003_domain_id_server_default"
down_revision: Union[str, None] = "002_indexes_artifact_ts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE domain ALTER COLUMN id SET DEFAULT gen_random_uuid()")


def downgrade() -> None:
    op.execute("ALTER TABLE domain ALTER COLUMN id DROP DEFAULT")
