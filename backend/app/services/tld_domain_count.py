"""Refresh the tld_domain_count_mv materialized view."""

from __future__ import annotations

import logging

from sqlalchemy import text

from app.infra.db.session import SessionLocal

logger = logging.getLogger(__name__)


def refresh_tld_domain_count_mv() -> None:
    """Refresh the tld_domain_count_mv materialized view (non-blocking).

    Uses CONCURRENTLY so reads are never blocked. Called once per day
    at the end of the CZDS catchup cycle.
    """
    db = SessionLocal()
    try:
        db.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY tld_domain_count_mv"))
        db.commit()
        logger.info("tld_domain_count_mv refreshed.")
    except Exception:
        logger.exception("Failed to refresh tld_domain_count_mv")
        db.rollback()
    finally:
        db.close()
