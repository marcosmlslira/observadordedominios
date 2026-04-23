"""Shared constants for the ingestion pipeline."""

from __future__ import annotations

# Domains with >= SHARD_THRESHOLD entries use sharded processing.
SHARD_THRESHOLD: int = 50_000_000
SHARD_COUNT: int = 128

# Maximum concurrent downloads in CZDS source.
CZDS_DOWNLOAD_CONCURRENCY: int = 4

# Polars streaming batch size for large zone-file processing.
STREAM_BATCH_SIZE: int = 1_000_000

# R2 marker path template — checked for idempotency.
MARKER_PREFIX: str = "markers"

# Parquet delta path template (relative to r2_prefix).
# Pattern: delta/source={s}/tld={t}/snapshot_date={d}/part.parquet
DELTA_PREFIX: str = "delta"
DELTA_REMOVED_PREFIX: str = "delta_removed"

# Current-state snapshot path.
# Pattern: current/source={s}/tld={t}/current.parquet
CURRENT_PREFIX: str = "current"

# Maximum rows kept in memory per shard when doing sharded diffs.
SHARD_MEMORY_ROWS: int = 5_000_000
