"""Repository for ingestion_cycle_tld — per-TLD plan rows per cycle."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.ingestion_cycle_tld import IngestionCycleTld


class IngestionCycleTldRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Write ─────────────────────────────────────────────────────────────────

    def bulk_insert_planned(
        self,
        cycle_id: uuid.UUID | str,
        source: str,
        tlds: list[dict[str, Any]],
    ) -> None:
        """Insert one 'planned' row per TLD at cycle start.

        Each entry in `tlds` is a dict with keys:
          tld (str), priority (int|None), planned_position (int), planned_phase (str)
        """
        if not tlds:
            return
        now = datetime.now(timezone.utc)
        rows = [
            {
                "cycle_id": str(cycle_id),
                "source": source,
                "tld": t["tld"],
                "priority": t.get("priority"),
                "planned_position": t.get("planned_position"),
                "planned_phase": t.get("planned_phase", "full_run"),
                "execution_status": "planned",
            }
            for t in tlds
        ]
        # Use INSERT … ON CONFLICT DO NOTHING so a retry doesn't blow up
        self.db.execute(
            text("""
                INSERT INTO ingestion_cycle_tld
                    (cycle_id, source, tld, priority, planned_position,
                     planned_phase, execution_status)
                VALUES
                    (:cycle_id, :source, :tld, :priority, :planned_position,
                     :planned_phase, :execution_status)
                ON CONFLICT (cycle_id, source, tld) DO NOTHING
            """),
            rows,
        )
        self.db.flush()

    def mark_running(
        self,
        cycle_id: uuid.UUID | str,
        source: str,
        tld: str,
        *,
        r2_run_id: uuid.UUID | None = None,
        pg_run_id: uuid.UUID | None = None,
    ) -> None:
        self.db.execute(
            text("""
                UPDATE ingestion_cycle_tld
                SET execution_status = 'running',
                    started_at       = :now,
                    r2_run_id        = COALESCE(:r2_run_id, r2_run_id),
                    pg_run_id        = COALESCE(:pg_run_id, pg_run_id)
                WHERE cycle_id = :cycle_id::uuid
                  AND source   = :source
                  AND tld      = :tld
            """),
            {
                "cycle_id": str(cycle_id),
                "source": source,
                "tld": tld,
                "now": datetime.now(timezone.utc),
                "r2_run_id": str(r2_run_id) if r2_run_id else None,
                "pg_run_id": str(pg_run_id) if pg_run_id else None,
            },
        )
        self.db.flush()

    def mark_finished(
        self,
        cycle_id: uuid.UUID | str,
        source: str,
        tld: str,
        *,
        execution_status: str,
        reason_code: str | None = None,
        error_message: str | None = None,
        snapshot_date: str | None = None,
        r2_marker_date: str | None = None,
        r2_run_id: uuid.UUID | None = None,
        pg_run_id: uuid.UUID | None = None,
        databricks_run_id: int | None = None,
        databricks_run_url: str | None = None,
        databricks_result_state: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        self.db.execute(
            text("""
                UPDATE ingestion_cycle_tld
                SET execution_status        = :execution_status,
                    reason_code             = :reason_code,
                    error_message           = :error_message,
                    snapshot_date           = :snapshot_date,
                    r2_marker_date          = :r2_marker_date,
                    r2_run_id               = COALESCE(:r2_run_id,    r2_run_id),
                    pg_run_id               = COALESCE(:pg_run_id,    pg_run_id),
                    databricks_run_id       = COALESCE(:db_run_id,    databricks_run_id),
                    databricks_run_url      = COALESCE(:db_run_url,   databricks_run_url),
                    databricks_result_state = COALESCE(:db_result,    databricks_result_state),
                    finished_at             = :now,
                    duration_seconds        = CASE
                        WHEN started_at IS NOT NULL
                        THEN EXTRACT(EPOCH FROM (:now - started_at))::INT
                        ELSE NULL END
                WHERE cycle_id = :cycle_id::uuid
                  AND source   = :source
                  AND tld      = :tld
            """),
            {
                "cycle_id": str(cycle_id),
                "source": source,
                "tld": tld,
                "execution_status": execution_status,
                "reason_code": reason_code,
                "error_message": error_message,
                "snapshot_date": snapshot_date,
                "r2_marker_date": r2_marker_date,
                "r2_run_id": str(r2_run_id) if r2_run_id else None,
                "pg_run_id": str(pg_run_id) if pg_run_id else None,
                "db_run_id": databricks_run_id,
                "db_run_url": databricks_run_url,
                "db_result": databricks_result_state,
                "now": now,
            },
        )
        self.db.flush()

    def close_pending_as_not_reached(
        self,
        cycle_id: uuid.UUID | str,
        *,
        reason_code: str = "not_reached",
    ) -> int:
        """Mark all 'planned' or 'running' rows for a cycle as 'not_reached'.

        Returns the number of rows updated.
        """
        result = self.db.execute(
            text("""
                UPDATE ingestion_cycle_tld
                SET execution_status = 'not_reached',
                    reason_code      = :reason_code,
                    finished_at      = now()
                WHERE cycle_id = :cycle_id::uuid
                  AND execution_status IN ('planned', 'running')
            """),
            {"cycle_id": str(cycle_id), "reason_code": reason_code},
        )
        self.db.flush()
        return result.rowcount

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_for_cycle(
        self,
        cycle_id: uuid.UUID | str,
        *,
        source: str | None = None,
        execution_status: str | None = None,
    ) -> list[IngestionCycleTld]:
        query = self.db.query(IngestionCycleTld).filter(
            IngestionCycleTld.cycle_id == str(cycle_id)
        )
        if source:
            query = query.filter(IngestionCycleTld.source == source)
        if execution_status:
            query = query.filter(IngestionCycleTld.execution_status == execution_status)
        return query.order_by(IngestionCycleTld.planned_position).all()

    def count_by_status(self, cycle_id: uuid.UUID | str) -> dict[str, int]:
        """Return a dict of {execution_status: count} for a given cycle."""
        rows = self.db.execute(
            text("""
                SELECT execution_status, count(*) AS n
                FROM ingestion_cycle_tld
                WHERE cycle_id = :cycle_id::uuid
                GROUP BY execution_status
            """),
            {"cycle_id": str(cycle_id)},
        ).fetchall()
        return {r.execution_status: r.n for r in rows}
