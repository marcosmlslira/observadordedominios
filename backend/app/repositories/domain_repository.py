"""Repository for domain bulk operations — simplified upsert without staging."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


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
