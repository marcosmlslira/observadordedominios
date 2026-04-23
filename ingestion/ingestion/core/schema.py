"""Polars schema definitions for ingestion Parquet files (ADR-001)."""

from __future__ import annotations

import polars as pl

# ── Snapshot schema (in-memory + current-state Parquet in R2) ─────────────────
SNAPSHOT_SCHEMA: dict[str, pl.DataType] = {
    "name":  pl.Utf8,   # fully-qualified domain (e.g. "google.com")
    "tld":   pl.Utf8,   # TLD suffix (e.g. "com")
    "label": pl.Utf8,   # SLD label (e.g. "google")
}

# ── Delta schema (written to R2 Parquet, loaded to PostgreSQL) ────────────────
# delta_loader injects added_day from snapshot_date parameter at load time.
DELTA_SCHEMA: dict[str, pl.DataType] = {
    "name":  pl.Utf8,
    "tld":   pl.Utf8,
    "label": pl.Utf8,
}

# ── Current-state schema (full snapshot in R2, used for set-diff) ─────────────
CURRENT_SCHEMA: dict[str, pl.DataType] = {
    "name":  pl.Utf8,
    "tld":   pl.Utf8,
    "label": pl.Utf8,
}
