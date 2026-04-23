"""ingestion.core package."""

from ingestion.core.types import DiffResult, RunKey, RunStats, Source
from ingestion.core.label import extract_label
from ingestion.core.diff_engine import simple_diff

__all__ = [
    "DiffResult",
    "RunKey",
    "RunStats",
    "Source",
    "extract_label",
    "simple_diff",
]
