"""Repository for domain bulk operations — staging, upsert, soft-delete."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class DomainRepository:
    """Encapsulates all DB operations on the domain table during a zone delta."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Staging table management ────────────────────────────
    def create_staging_table(self, run_id: uuid.UUID) -> str:
        """Create a temporary staging table for this run and return its name."""
        safe_id = str(run_id).replace("-", "")
        table_name = f"stg_zone_domain_{safe_id}"
        self.db.execute(text(f"""
            CREATE TEMP TABLE {table_name} (
                name VARCHAR(253) PRIMARY KEY
            ) ON COMMIT DROP
        """))
        logger.debug("Created staging table %s", table_name)
        return table_name

    def bulk_insert_staging(self, staging_table: str, domain_names: list[str]) -> int:
        """Insert a batch of domain names into the staging table."""
        if not domain_names:
            return 0
        
        # Deduplicate within the batch first
        unique_names = set(domain_names)
        values = ",".join(f"('{n}')" for n in unique_names)
        
        # Insert avoiding cross-batch duplicates
        self.db.execute(text(
            f"INSERT INTO {staging_table} (name) VALUES {values} "
            f"ON CONFLICT (name) DO NOTHING"
        ))
        return len(domain_names)

    # ── Delta application ───────────────────────────────────
    def apply_delta(
        self,
        staging_table: str,
        tld: str,
        run_id: uuid.UUID,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """
        Apply the delta between staged domain names and existing DB records.

        Returns dict with keys: seen, inserted, reactivated, deleted.
        """
        ts = now or datetime.now(timezone.utc)
        ts_str = ts.isoformat()

        # Count total seen
        seen = self.db.execute(
            text(f"SELECT count(*) FROM {staging_table}")
        ).scalar() or 0

        # 1. Insert brand-new domains
        result_insert = self.db.execute(text(f"""
            INSERT INTO domain (id, name, tld, status, first_seen_at, last_seen_at, created_at, updated_at)
            SELECT
                gen_random_uuid(),
                stg.name,
                :tld,
                'active',
                :ts, :ts, :ts, :ts
            FROM {staging_table} stg
            WHERE NOT EXISTS (
                SELECT 1 FROM domain d WHERE d.name = stg.name
            )
        """), {"tld": tld, "ts": ts})
        inserted = result_insert.rowcount

        # 2. Reactivate deleted domains that reappeared
        result_reactivate = self.db.execute(text(f"""
            UPDATE domain
            SET status = 'active',
                deleted_at = NULL,
                last_seen_at = :ts,
                updated_at = :ts
            FROM {staging_table} stg
            WHERE domain.name = stg.name
              AND domain.tld = :tld
              AND domain.status = 'deleted'
        """), {"tld": tld, "ts": ts})
        reactivated = result_reactivate.rowcount

        # 3. Update last_seen_at for already-active domains
        self.db.execute(text(f"""
            UPDATE domain
            SET last_seen_at = :ts,
                updated_at = :ts
            FROM {staging_table} stg
            WHERE domain.name = stg.name
              AND domain.tld = :tld
              AND domain.status = 'active'
        """), {"tld": tld, "ts": ts})

        # 4. Soft-delete domains of this TLD not in staging
        result_delete = self.db.execute(text(f"""
            UPDATE domain
            SET status = 'deleted',
                deleted_at = :ts,
                updated_at = :ts
            WHERE tld = :tld
              AND status = 'active'
              AND NOT EXISTS (
                  SELECT 1 FROM {staging_table} stg WHERE stg.name = domain.name
              )
        """), {"tld": tld, "ts": ts})
        deleted = result_delete.rowcount

        logger.info(
            "Delta applied: tld=%s seen=%d inserted=%d reactivated=%d deleted=%d",
            tld, seen, inserted, reactivated, deleted,
        )
        return {
            "seen": seen,
            "inserted": inserted,
            "reactivated": reactivated,
            "deleted": deleted,
        }
