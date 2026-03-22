"""Drop duplicate ix_domain_name index (redundant with domain_name_key UNIQUE)

Revision ID: 004_drop_dup_ix_domain_name
Revises: 003_domain_id_server_default
Create Date: 2026-03-19

"""
from typing import Sequence, Union

from alembic import op

revision: str = "004_drop_dup_ix_domain_name"
down_revision: Union[str, None] = "003_domain_id_server_default"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_domain_name", table_name="domain")


def downgrade() -> None:
    op.create_index("ix_domain_name", "domain", ["name"])
