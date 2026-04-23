"""Set-diff engine — computes added/removed sets between snapshot and current state.

Design (from ADR-001):
    added   = snapshot − current
    removed = current  − snapshot
    next    = snapshot          (full overwrite of current)

Schema contract: DataFrames must have at least columns: name, tld, label.
For large TLDs (e.g. .com) the runner calls shard_diff() instead.
"""

from __future__ import annotations

import hashlib
from typing import Iterator

import polars as pl

from ingestion.config.constants import SHARD_COUNT


_SNAP_KEY = "name"  # primary key column for set-diff


def _stable_shard(name: str, num_shards: int = SHARD_COUNT) -> int:
    """Consistent MD5-based shard number — must be byte-identical across runs."""
    return int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16) % num_shards


def simple_diff(
    snapshot: pl.DataFrame,
    current: pl.DataFrame,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Return (added, removed) DataFrames using set arithmetic on 'name'.

    Both DataFrames must have at least a 'name' column.
    """
    snap_names = set(snapshot[_SNAP_KEY].to_list())
    curr_names = set(current[_SNAP_KEY].to_list()) if len(current) > 0 else set()

    added_names = snap_names - curr_names
    removed_names = curr_names - snap_names

    added = snapshot.filter(pl.col(_SNAP_KEY).is_in(added_names))
    removed = current.filter(pl.col(_SNAP_KEY).is_in(removed_names))
    return added, removed


def shard_iter(df: pl.DataFrame, num_shards: int = SHARD_COUNT) -> Iterator[tuple[int, pl.DataFrame]]:
    """Yield (shard_id, shard_df) for in-memory sharding of large DataFrames."""
    df = df.with_columns(
        pl.col(_SNAP_KEY)
        .map_elements(lambda d: _stable_shard(d, num_shards), return_dtype=pl.Int64)
        .alias("_shard")
    )
    for shard_id in range(num_shards):
        shard_df = df.filter(pl.col("_shard") == shard_id).drop("_shard")
        yield shard_id, shard_df
