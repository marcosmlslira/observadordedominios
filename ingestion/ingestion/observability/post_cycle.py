"""Post-cycle maintenance hooks.

Functions that should run once at the end of every full daily ingestion
cycle (after both OpenINTEL and CZDS finish), so derived/aggregate state
stays fresh.

Currently:
  * ``refresh_tld_domain_count_mv`` — refreshes the
    ``tld_domain_count_mv`` materialized view used by the admin
    ingestion endpoints and the domain-similarity tool.

Each helper is best-effort: failures are logged but never propagated, so
a maintenance error never marks the cycle itself as failed.
"""

from __future__ import annotations

import logging

import psycopg2

log = logging.getLogger(__name__)


def refresh_tld_domain_count_mv(db_url: str) -> None:
    """Refresh ``tld_domain_count_mv`` non-blockingly.

    The materialized view aggregates ``domain → tld → count`` and is read
    by ``/v1/ingestion/domain-counts`` and the ``domain_similarity`` tool.
    It must be refreshed after each daily cycle so the counts track the
    current zone state. ``CONCURRENTLY`` keeps reads unblocked during
    the refresh; it requires a ``UNIQUE`` index, which exists on
    ``(tld)`` (created in migrations 017 / 031).
    """

    conn = None
    try:
        conn = psycopg2.connect(db_url)
        # CONCURRENTLY cannot run inside a transaction block.
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY tld_domain_count_mv")
        log.info("post_cycle: tld_domain_count_mv refreshed")
    except Exception as exc:  # noqa: BLE001
        log.warning("post_cycle: tld_domain_count_mv refresh failed (non-fatal): %s", exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:  # noqa: BLE001
                pass
