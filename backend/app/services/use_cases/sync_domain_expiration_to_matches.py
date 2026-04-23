"""Use case: sync domain expiration and reactivation to similarity_match.

After each ingestion cycle the domain table and domain_removed table are
authoritative about which domains are active.  This use case propagates
that state into similarity_match.domain_expired_day so the admin UI can
show "expired domain" badges and let analysts filter active vs. historic
threats.

Algorithm:
  1. Expiration: for every domain in domain_removed, mark any similarity_match
     row for that domain as expired (set domain_expired_day = removed_day)
     if it wasn't already marked.
  2. Reactivation: domains that re-appeared in zone today (added_day = today)
     → clear domain_expired_day = NULL and delete from domain_removed.

The caller is responsible for committing the transaction.
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.orm import Session
from sqlalchemy import text

log = logging.getLogger(__name__)


def sync_domain_expiration_to_matches(
    db: Session,
    *,
    tld: str | None = None,
    today: date | None = None,
) -> dict[str, int]:
    """Propagate domain expiration/reactivation into similarity_match.

    Args:
        db: SQLAlchemy session (caller commits).
        tld: If provided, restrict updates to this TLD only (for per-cycle
             incremental updates). If None, processes all TLDs.
        today: Reference date for detecting reactivated domains. Defaults to
               today (UTC).

    Returns:
        Dict with ``expired_marked`` and ``reactivated`` counts.
    """
    today_int = int((today or date.today()).strftime("%Y%m%d"))
    tld_filter = "AND sm.tld = :tld" if tld else ""
    params: dict = {"today_int": today_int}
    if tld:
        params["tld"] = tld

    # ── 1. Mark newly-expired domains ────────────────────────────────────────
    expired_result = db.execute(
        text(f"""
            UPDATE similarity_match sm
            SET domain_expired_day = dr.removed_day
            FROM domain_removed dr
            WHERE sm.domain_name = dr.name
              AND sm.tld = dr.tld
              AND sm.domain_expired_day IS NULL
              {tld_filter}
        """),
        params,
    )
    expired_count = expired_result.rowcount

    # ── 2. Reactivate domains that re-appeared in zone today ─────────────────
    reactivate_result = db.execute(
        text(f"""
            UPDATE similarity_match sm
            SET domain_expired_day = NULL
            FROM domain d
            WHERE sm.domain_name = d.name
              AND sm.tld = d.tld
              AND d.added_day = :today_int
              AND sm.domain_expired_day IS NOT NULL
              {tld_filter}
        """),
        params,
    )
    reactivated_count = reactivate_result.rowcount

    # ── 3. Remove reactivated domains from domain_removed ────────────────────
    tld_filter_dr = "AND dr.tld = :tld" if tld else ""
    db.execute(
        text(f"""
            DELETE FROM domain_removed dr
            WHERE EXISTS (
                SELECT 1 FROM domain d
                WHERE d.name = dr.name
                  AND d.tld = dr.tld
                  AND d.added_day = :today_int
            )
            {tld_filter_dr}
        """),
        params,
    )

    log.info(
        "sync_domain_expiration tld=%s expired_marked=%d reactivated=%d",
        tld or "*",
        expired_count,
        reactivated_count,
    )
    return {"expired_marked": expired_count, "reactivated": reactivated_count}
