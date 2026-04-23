"""Run log builder — writes a structured run summary to R2."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ingestion.core.types import RunStats


def build_run_log_payload(stats: RunStats) -> str:
    return json.dumps(
        {
            "source": stats.run_key.source.value,
            "tld": stats.run_key.tld,
            "snapshot_date": stats.run_key.snapshot_date.isoformat(),
            "started_at": stats.started_at,
            "finished_at": stats.finished_at,
            "status": stats.status,
            "snapshot_count": stats.snapshot_count,
            "added_count": stats.added_count,
            "removed_count": stats.removed_count,
            "error_message": stats.error_message,
            **stats.metadata,
        },
        ensure_ascii=False,
    )


def now_utc() -> str:
    return datetime.now(tz=timezone.utc).isoformat()
