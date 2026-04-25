from __future__ import annotations

import base64
from datetime import date


CURRENT_COLUMNS = [
    "source",
    "tld",
    "domain_norm",
    "domain_raw",
    "domain_raw_b64",
    "domain",
    "first_seen_date",
    "last_seen_date",
    "is_active",
    "first_seen_run_id",
    "last_seen_run_id",
    "updated_at",
]

DOMAIN_EVENT_COLUMNS = [
    "source",
    "tld",
    "snapshot_date",
    "domain_norm",
    "domain_raw",
    "domain_raw_b64",
    "domain",
    "run_id",
    "processed_at",
]

RUN_COLUMNS = [
    "run_id",
    "source",
    "tld",
    "snapshot_date",
    "started_at",
    "finished_at",
    "status",
    "total_snapshot_count",
    "added_count",
    "removed_count",
    "raw_object_key",
    "error_message",
]

SNAPSHOT_COLUMNS = ["domain_norm", "domain_raw", "domain_raw_b64"]


def bytes_to_b64(raw_bytes: bytes) -> str:
    return base64.b64encode(raw_bytes).decode("ascii")


def text_to_b64(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return bytes_to_b64(value.encode("latin-1"))
    except UnicodeEncodeError:
        return bytes_to_b64(value.encode("utf-8"))


def snapshot_record_from_raw_bytes(raw_bytes: bytes) -> dict[str, str]:
    raw_text = raw_bytes.decode("latin-1")
    norm_text = raw_text.lower().strip()
    return {
        "domain_norm": norm_text,
        "domain_raw": raw_text,
        "domain_raw_b64": bytes_to_b64(raw_bytes),
    }


def day_str(d: date) -> str:
    return d.isoformat()

