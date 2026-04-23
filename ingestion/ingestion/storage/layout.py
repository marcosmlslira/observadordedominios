"""R2 path layout for all ingestion artefacts.

Canonical key structure:
  {prefix}/delta/source={s}/tld={t}/snapshot_date={d}/part.parquet
  {prefix}/delta_removed/source={s}/tld={t}/snapshot_date={d}/part.parquet
  {prefix}/current/source={s}/tld={t}/current.parquet
  {prefix}/markers/source={s}/tld={t}/snapshot_date={d}/success.json
"""

from __future__ import annotations

from datetime import date


class Layout:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix.rstrip("/")

    # ── Deltas ────────────────────────────────────────────────────────────────

    def delta_key(self, source: str, tld: str, snapshot_date: date | str) -> str:
        d = snapshot_date.isoformat() if isinstance(snapshot_date, date) else snapshot_date
        return f"{self.prefix}/delta/source={source}/tld={tld}/snapshot_date={d}/part.parquet"

    def delta_removed_key(self, source: str, tld: str, snapshot_date: date | str) -> str:
        d = snapshot_date.isoformat() if isinstance(snapshot_date, date) else snapshot_date
        return f"{self.prefix}/delta_removed/source={source}/tld={tld}/snapshot_date={d}/part.parquet"

    # ── Current state ─────────────────────────────────────────────────────────

    def current_key(self, source: str, tld: str) -> str:
        return f"{self.prefix}/current/source={source}/tld={tld}/current.parquet"

    # ── Markers (idempotency) ─────────────────────────────────────────────────

    def marker_key(self, source: str, tld: str, snapshot_date: date | str) -> str:
        d = snapshot_date.isoformat() if isinstance(snapshot_date, date) else snapshot_date
        return f"{self.prefix}/markers/source={source}/tld={tld}/snapshot_date={d}/success.json"

    # ── Shards (large TLDs like .com) ─────────────────────────────────────────

    def shard_current_key(self, source: str, tld: str, shard_id: int) -> str:
        return f"{self.prefix}/current_sharded/source={source}/tld={tld}/shard={shard_id:04d}.parquet"

    def shard_snapshot_key(self, source: str, tld: str, snapshot_date: date | str, shard_id: int) -> str:
        d = snapshot_date.isoformat() if isinstance(snapshot_date, date) else snapshot_date
        return (
            f"{self.prefix}/snapshot_sharded/source={source}"
            f"/tld={tld}/snapshot_date={d}/shard={shard_id:04d}.parquet"
        )
