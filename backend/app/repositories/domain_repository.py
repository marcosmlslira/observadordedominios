"""Repository for domain bulk operations — ADR-001 schema (added_day INTEGER)."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime

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


class DomainRepository:
    """Bulk operations on the domain table (ADR-001: added_day INTEGER)."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def bulk_insert(
        self,
        domain_names: list[str],
        tld: str,
        added_day: int,
    ) -> int:
        """Bulk-insert new domain names — ON CONFLICT DO NOTHING.

        Args:
            domain_names: Fully-qualified domain names (e.g. 'foo.com').
            tld: TLD string (e.g. 'com').
            added_day: YYYYMMDD integer (e.g. 20260423).

        Returns:
            Number of rows processed (before conflict resolution).
        """
        if not domain_names:
            return 0

        unique_names = list(set(domain_names))
        labels = [n[:-(len(tld) + 1)] for n in unique_names]

        self.db.execute(
            text("""
                INSERT INTO domain (name, tld, label, added_day)
                SELECT unnest(:names), :tld, unnest(:labels), :added_day
                ON CONFLICT (name, tld) DO NOTHING
            """),
            {"names": unique_names, "labels": labels, "tld": tld, "added_day": added_day},
        )
        return len(unique_names)

    def bulk_insert_removed(
        self,
        domain_names: list[str],
        tld: str,
        removed_day: int,
    ) -> int:
        """Bulk-insert removed domain names into domain_removed."""
        if not domain_names:
            return 0

        unique_names = list(set(domain_names))
        self.db.execute(
            text("""
                INSERT INTO domain_removed (name, tld, removed_day)
                SELECT unnest(:names), :tld, :removed_day
                ON CONFLICT (name, tld) DO NOTHING
            """),
            {"names": unique_names, "tld": tld, "removed_day": removed_day},
        )
        return len(unique_names)

    @staticmethod
    def _to_added_day(value: datetime | int) -> int:
        if isinstance(value, int):
            return value
        return int(value.strftime("%Y%m%d"))

    def bulk_upsert(
        self,
        domain_names: list[str],
        tld: str,
        observed_at: datetime | int,
    ) -> int:
        """Compatibility helper used by legacy ingestion paths.

        Upserts by (name, tld), refreshing label + added_day on conflict.
        Returns number of unique names processed.
        """
        if not domain_names:
            return 0

        unique_names = list(set(domain_names))
        labels = [n[:-(len(tld) + 1)] for n in unique_names]
        added_day = self._to_added_day(observed_at)

        self.db.execute(
            text(
                """
                INSERT INTO domain (name, tld, label, added_day)
                SELECT unnest(:names), :tld, unnest(:labels), :added_day
                ON CONFLICT (name, tld) DO UPDATE SET
                    label = EXCLUDED.label,
                    added_day = EXCLUDED.added_day
                """
            ),
            {
                "names": unique_names,
                "labels": labels,
                "tld": tld,
                "added_day": added_day,
            },
        )
        return len(unique_names)

    def bulk_upsert_multi_tld(
        self,
        normalized_domains: list[tuple[str, str, str]],
        observed_at: datetime | int,
    ) -> dict[str, int]:
        """Compatibility helper for CT batch ingestion across multiple TLDs.

        Input rows are tuples: (name, tld, label).
        Returns per-TLD processed counts.
        """
        if not normalized_domains:
            return {}

        by_tld: dict[str, dict[str, str]] = defaultdict(dict)
        for name, tld, label in normalized_domains:
            by_tld[tld][name] = label

        added_day = self._to_added_day(observed_at)
        processed: dict[str, int] = {}

        for tld, names_map in by_tld.items():
            names = list(names_map.keys())
            labels = [names_map[n] for n in names]
            self.db.execute(
                text(
                    """
                    INSERT INTO domain (name, tld, label, added_day)
                    SELECT unnest(:names), :tld, unnest(:labels), :added_day
                    ON CONFLICT (name, tld) DO UPDATE SET
                        label = EXCLUDED.label,
                        added_day = EXCLUDED.added_day
                    """
                ),
                {
                    "names": names,
                    "labels": labels,
                    "tld": tld,
                    "added_day": added_day,
                },
            )
            processed[tld] = len(names)

        return processed
