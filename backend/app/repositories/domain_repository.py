"""Domain partition helpers — ADR-001 schema (added_day INTEGER).

Bulk write operations live in the new ingestion package
(``ingestion/loader/delta_loader.py``), which talks to PostgreSQL
directly via psycopg2/COPY for performance. The helpers below are still
used by tests/seed scripts and by the similarity scan path.
"""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def ensure_partition(db: Session, tld: str) -> None:
    """Create domain and domain_removed partitions for a TLD if they don't exist.

    Uses lock_timeout=1ms (non-blocking) to avoid queuing ACCESS EXCLUSIVE
    locks that would cascade-block concurrent INSERTs.
    """
    safe_tld = tld.replace("-", "_").replace(".", "_")

    for parent, suffix in [("domain", ""), ("domain_removed", "_removed")]:
        partition_name = f"domain{suffix}_{safe_tld}"
        exists = db.execute(
            text("SELECT 1 FROM pg_class WHERE relname = :name"),
            {"name": partition_name},
        ).scalar()

        if not exists:
            try:
                db.execute(text("SET LOCAL lock_timeout = 1"))
                db.execute(
                    text(
                        f"CREATE TABLE {partition_name} PARTITION OF {parent} "
                        f"FOR VALUES IN ('{tld}')"
                    )
                )
                db.commit()
                logger.info("Created partition %s for TLD=%s", partition_name, tld)
            except Exception as exc:
                db.rollback()
                created_by_other = db.execute(
                    text("SELECT 1 FROM pg_class WHERE relname = :name"),
                    {"name": partition_name},
                ).scalar()
                if created_by_other:
                    logger.info("Partition %s already created by concurrent process", partition_name)
                    return
                logger.warning(
                    "Cannot create partition %s (lock unavailable or error): %s",
                    partition_name, exc,
                )
                raise


def list_partition_tlds(db: Session) -> list[str]:
    """Discover all TLDs from domain table partitions."""
    rows = db.execute(text("""
        SELECT pg_get_expr(c.relpartbound, c.oid) AS bound_expr
        FROM pg_class c
        JOIN pg_inherits i ON c.oid = i.inhrelid
        JOIN pg_class p ON i.inhparent = p.oid
        WHERE p.relname = 'domain'
          AND c.relkind = 'r'
          AND c.relispartition = true
    """)).fetchall()

    tlds = []
    for (bound_expr,) in rows:
        start = bound_expr.find("'")
        end = bound_expr.rfind("'")
        if start != -1 and end > start:
            tlds.append(bound_expr[start + 1 : end])
    return tlds


