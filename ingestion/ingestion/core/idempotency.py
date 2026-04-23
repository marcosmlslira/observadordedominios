"""Idempotency helpers — check/write success markers in R2."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ingestion.core.types import RunKey


def marker_key(run_key: RunKey, prefix: str = "markers") -> str:
    """Return R2 object key for the success marker of a run."""
    d = run_key.snapshot_date.isoformat()
    return (
        f"{prefix}/source={run_key.source.value}"
        f"/tld={run_key.tld}"
        f"/snapshot_date={d}"
        f"/success.json"
    )


def build_marker_payload(run_key: RunKey, **extra) -> str:
    data = {
        "source": run_key.source.value,
        "tld": run_key.tld,
        "snapshot_date": run_key.snapshot_date.isoformat(),
        "completed_at": datetime.now(tz=timezone.utc).isoformat(),
        **extra,
    }
    return json.dumps(data, ensure_ascii=False)
