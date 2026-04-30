"""Canonical reason codes persisted in ingestion_run.reason_code and ingestion_cycle_tld.reason_code.

Keep values in sync with the DB — never change a code that is already stored in production.
New codes can be added freely; deprecate old ones by leaving them here with a comment.
"""

from __future__ import annotations

# ── Run-level success ─────────────────────────────────────────────────────────
SUCCESS = "success"
PARTIAL_LOAD_ADDED_ONLY = "partial_load_added_only"
PARTIAL_LOAD_RECOVERED = "partial_load_recovered"
DATABRICKS_BATCH_OK = "databricks_batch_ok"

# ── Run-level skip / no data ──────────────────────────────────────────────────
NO_SNAPSHOT = "no_snapshot"

# ── Run-level failures ────────────────────────────────────────────────────────
UNEXPECTED_ERROR = "unexpected_error"
TLD_RUNNER_ERROR = "tld_runner_error"
R2_MARKER_MISSING = "r2_marker_missing"
R2_PARQUET_MISSING = "r2_parquet_missing"
DATABRICKS_SUBMIT_ERROR = "databricks_submit_error"
DATABRICKS_RUN_ERROR = "databricks_run_error"
DATABRICKS_CONTRACT_VIOLATION = "databricks_contract_violation"
PG_LOAD_ERROR = "pg_load_error"

# ── Recovery ──────────────────────────────────────────────────────────────────
STALE_RECOVERED = "stale_recovered"

# ── Cycle-level / plan-level (ingestion_cycle_tld) ───────────────────────────
NOT_REACHED = "not_reached"
CYCLE_INTERRUPTED = "cycle_interrupted"
WORKER_SHUTDOWN = "worker_shutdown"
PREVIOUS_PHASE_BLOCKED = "previous_phase_blocked"
SOURCE_CRASHED = "source_crashed"
