from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.infra.db.session import get_db

router = APIRouter()


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        row = db.execute(
            text("""
                SELECT
                    cycle_id::text,
                    started_at,
                    finished_at,
                    status,
                    triggered_by,
                    tld_total,
                    tld_success,
                    tld_failed,
                    tld_skipped,
                    last_heartbeat_at
                FROM ingestion_cycle
                ORDER BY started_at DESC
                LIMIT 1
            """)
        ).fetchone()
        last_cycle = (
            {
                "cycle_id": row.cycle_id,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "finished_at": row.finished_at.isoformat() if row.finished_at else None,
                "status": row.status,
                "triggered_by": row.triggered_by,
                "tld_total": row.tld_total,
                "tld_success": row.tld_success,
                "tld_failed": row.tld_failed,
                "tld_skipped": row.tld_skipped,
                "last_heartbeat_at": row.last_heartbeat_at.isoformat() if row.last_heartbeat_at else None,
            }
            if row
            else None
        )
    except Exception:
        last_cycle = None

    return {"status": "ok", "last_cycle": last_cycle}
