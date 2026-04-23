"""Domain types used throughout the ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class Source(str, Enum):
    CZDS = "czds"
    OPENINTEL = "openintel"


@dataclass(frozen=True)
class RunKey:
    """Unique identifier for a single ingestion run."""

    source: Source
    tld: str
    snapshot_date: date

    def __str__(self) -> str:
        return f"{self.source.value}/{self.tld}/{self.snapshot_date.isoformat()}"


@dataclass
class DiffResult:
    """Output of a set-diff computation."""

    added_count: int = 0
    removed_count: int = 0
    snapshot_count: int = 0
    current_count: int = 0
    delta_path: str = ""
    delta_removed_path: str = ""
    next_current_path: str = ""


@dataclass
class RunStats:
    run_key: RunKey
    started_at: str = ""
    finished_at: str = ""
    status: str = "ok"
    added_count: int = 0
    removed_count: int = 0
    snapshot_count: int = 0
    error_message: str = ""
    metadata: dict = field(default_factory=dict)
