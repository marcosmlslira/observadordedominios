"""Repository for domain bulk operations — simplified upsert without staging."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def ensure_partition(db: Session, tld: str) -> None:
    """Create a partition for the TLD if it doesn't exist yet.

    Uses lock_timeout='0' (non-blocking) so the DDL never queues an
    ACCESS EXCLUSIVE lock that would cascade-block concurrent INSERTs.
    If the lock is unavailable, rolls back cleanly and re-raises so the
    caller can skip this TLD and retry on the next cycle.

    Handles multi-level TLDs: dots and hyphens are replaced with underscores
    in the partition name, but the actual TLD value is preserved in FOR VALUES IN.

    Examples:
        "net"    -> partition "domain_net"    FOR VALUES IN ('net')
        "com.br" -> partition "domain_com_br" FOR VALUES IN ('com.br')
    """
    safe_tld = tld.replace("-", "_").replace(".", "_")
    partition_name = f"domain_{safe_tld}"

    exists = db.execute(
        text("SELECT 1 FROM pg_class WHERE relname = :name"),
        {"name": partition_name},
    ).scalar()

    if not exists:
        try:
            # lock_timeout='0' means fail immediately if ACCESS EXCLUSIVE is unavailable
            # instead of queueing — prevents cascading stalls of concurrent INSERTs.
            db.execute(text("SET LOCAL lock_timeout = '0'"))
            db.execute(text(
                f"CREATE TABLE {partition_name} PARTITION OF domain "
                f"FOR VALUES IN ('{tld}')"
            ))
            db.commit()
            logger.info("Created partition %s for TLD=%s", partition_name, tld)
        except Exception as exc:
            db.rollback()
            # Re-check: another process may have created it during our attempt
            created_by_other = db.execute(
                text("SELECT 1 FROM pg_class WHERE relname = :name"),
                {"name": partition_name},
            ).scalar()
            if created_by_other:
                logger.info("Partition %s already created by concurrent process", partition_name)
                return
            logger.warning(
                "Cannot create partition %s (lock unavailable or error): %s — "
                "TLD will be retried on next cycle.",
                partition_name, exc,
            )
            raise


def list_partition_tlds(db: Session) -> list[str]:
    """Discover all TLDs from domain table partitions.

    Extracts the actual TLD value from the partition bound expression,
    not from the partition name (which may have dots replaced with underscores).
    """
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
        # bound_expr looks like: FOR VALUES IN ('com.br')
        # Extract the TLD value between single quotes
        start = bound_expr.find("'")
        end = bound_expr.rfind("'")
        if start != -1 and end > start:
            tlds.append(bound_expr[start + 1 : end])

    return tlds


class DomainRepository:
    """Bulk upsert of domains. No staging table, no soft-delete."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def bulk_upsert(self, domain_names: list[str], tld: str, now: datetime) -> int:
        """Upsert a batch into the domain table with label computation.

        Returns the count of names processed.
        """
        if not domain_names:
            return 0

        unique_names = list(set(domain_names))
        labels = [n[:-(len(tld) + 1)] for n in unique_names]

        self.db.execute(text("""
            INSERT INTO domain (name, tld, label, first_seen_at, last_seen_at)
            SELECT
                unnest(:names),
                :tld,
                unnest(:labels),
                :ts, :ts
            ON CONFLICT (name, tld) DO UPDATE
            SET last_seen_at = GREATEST(domain.last_seen_at, EXCLUDED.last_seen_at)
        """), {"names": unique_names, "labels": labels, "tld": tld, "ts": now})

        return len(unique_names)

    def bulk_upsert_multi_tld(
        self,
        domains: list[tuple[str, str, str]],
        now: datetime,
    ) -> dict[str, int]:
        """Upsert domains across multiple TLDs.

        Args:
            domains: List of (name, tld, label) tuples.
            now: Timestamp for first_seen_at / last_seen_at.

        Returns:
            Dict of {tld: count} for domains processed per TLD.
        """
        if not domains:
            return {}

        by_tld: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for name, tld, label in domains:
            by_tld[tld].append((name, label))

        counts: dict[str, int] = {}
        for tld, items in by_tld.items():
            names = [n for n, _ in items]
            labels = [l for _, l in items]

            self.db.execute(text("""
                INSERT INTO domain (name, tld, label, first_seen_at, last_seen_at)
                SELECT
                    unnest(:names),
                    :tld,
                    unnest(:labels),
                    :ts, :ts
                ON CONFLICT (name, tld) DO UPDATE
                SET last_seen_at = GREATEST(domain.last_seen_at, EXCLUDED.last_seen_at)
            """), {"names": names, "labels": labels, "tld": tld, "ts": now})

            counts[tld] = len(names)

        return counts
