"""Add .br TLD partitions for CT Logs ingestion

Creates partitions for Brazilian TLDs to support CertStream and crt.sh
domain ingestion. CZDS covers gTLDs (net, org, info) but not .br.

Revision ID: 007_ct_br_partitions
Revises: 006_similarity_tables
Create Date: 2026-03-23

"""
from typing import Sequence, Union

from alembic import op

revision: str = "007_ct_br_partitions"
down_revision: Union[str, None] = "006_similarity_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Brazilian TLDs to create partitions for
BR_TLDS = [
    "br",
    "com.br",
    "net.br",
    "org.br",
    "gov.br",
    "edu.br",
    "mil.br",
    "app.br",
    "dev.br",
    "log.br",
    "ong.br",
]


def _safe_partition_name(tld: str) -> str:
    """Convert TLD to valid SQL partition name: com.br -> domain_com_br"""
    return f"domain_{tld.replace('-', '_').replace('.', '_')}"


def upgrade() -> None:
    for tld in BR_TLDS:
        partition = _safe_partition_name(tld)
        op.execute(
            f"CREATE TABLE IF NOT EXISTS {partition} "
            f"PARTITION OF domain FOR VALUES IN ('{tld}')"
        )


def downgrade() -> None:
    for tld in reversed(BR_TLDS):
        partition = _safe_partition_name(tld)
        op.execute(f"DROP TABLE IF EXISTS {partition}")
