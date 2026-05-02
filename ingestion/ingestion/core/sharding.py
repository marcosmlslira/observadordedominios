"""Stable hash-based sharding — shared across all ingestion sources.

The function MUST be byte-identical across runs and across sources so that the
same domain always lands in the same shard regardless of which source produced
it. This invariant lets us compute deltas per-shard against R2 without ever
materialising the full snapshot in memory.
"""

from __future__ import annotations

import hashlib

from ingestion.config.constants import SHARD_COUNT


def stable_shard(name: str, num_shards: int = SHARD_COUNT) -> int:
    """Return a deterministic shard id in [0, num_shards) for a domain name."""
    return int(hashlib.md5(name.encode("utf-8")).hexdigest()[:8], 16) % num_shards
