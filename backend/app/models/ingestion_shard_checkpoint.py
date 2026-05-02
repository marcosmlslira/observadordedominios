"""IngestionShardCheckpoint — one row per shard successfully loaded into a partition.

Used by the ingestion bulk loader to skip shards that already finished on a
previous attempt of the same (source, tld, snapshot_date).
"""

from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base


class IngestionShardCheckpoint(Base):
    __tablename__ = "ingestion_shard_checkpoint"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    run_id = Column(UUID(as_uuid=True), ForeignKey("ingestion_run.id", ondelete="CASCADE"), nullable=False)
    source = Column(String(32), nullable=False)
    tld = Column(String(24), nullable=False)
    snapshot_date = Column(Date, nullable=False)
    partition = Column(String(64), nullable=False)
    shard_key = Column(Text, nullable=False)
    status = Column(String(16), nullable=False)
    rows_loaded = Column(BigInteger, nullable=False, server_default="0")
    loaded_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("run_id", "shard_key", "partition", name="uq_shard_checkpoint_run_key"),
        Index("ix_shard_checkpoint_lookup", "source", "tld", "snapshot_date", "partition", "status"),
        Index("ix_shard_checkpoint_run", "run_id"),
    )
