"""Business logic for ingestion source configuration."""

from __future__ import annotations

import re

_CRON_PART_RANGES = [
    ("minute", 0, 59),
    ("hour", 0, 23),
    ("day", 1, 31),
    ("month", 1, 12),
    ("day_of_week", 0, 6),
]

_VALID_SOURCES = {"czds", "openintel"}


class InvalidCronError(ValueError):
    pass


class InvalidSourceError(ValueError):
    pass


def validate_cron_expression(expr: str) -> str:
    """
    Validate a 5-part cron expression (minute hour day month dow).
    Returns the cleaned expression or raises InvalidCronError.
    """
    parts = expr.strip().split()
    if len(parts) != 5:
        raise InvalidCronError(
            f"Cron must have exactly 5 parts (got {len(parts)}): '{expr}'"
        )

    for part, (name, lo, hi) in zip(parts, _CRON_PART_RANGES):
        if part == "*":
            continue
        # Allow */n, ranges (1-5), and lists (1,3,5)
        if not re.fullmatch(r"[\d,\-\*/]+", part):
            raise InvalidCronError(f"Invalid cron {name}: '{part}'")
        # Validate plain integers are in range
        for token in re.split(r"[,\-/]", part):
            if token and token.isdigit():
                val = int(token)
                if not (lo <= val <= hi):
                    raise InvalidCronError(
                        f"Cron {name} value {val} out of range [{lo},{hi}]"
                    )

    return " ".join(parts)


def validate_source(source: str) -> str:
    if source not in _VALID_SOURCES:
        raise InvalidSourceError(
            f"Unknown source '{source}'. Valid: {sorted(_VALID_SOURCES)}"
        )
    return source
