"""PostgreSQL health probes — detect runaway autovacuum and excessive bloat.

Motivated by the 01/05/2026 incident: pg_catalog.pg_class corruption caused
the autovacuum worker to crash every ~60s for 5+ days without anyone noticing,
which in turn destabilised long-running connections and aborted CZDS ingest
runs. This service surfaces three early warning signals so we never repeat
that:

  1. Autovacuum stuck on the same relation for >N minutes (pg_stat_activity).
  2. Tables with very high dead-tuple ratios that haven't been vacuumed
     recently (pg_stat_user_tables).
  3. Long-lived idle-in-transaction sessions blocking vacuum.

Delivery of an actual alert (Resend, webhook, etc.) is intentionally left to
the caller — this module returns structured findings and logs them at WARNING/
ERROR; the cron job or scheduler hooks them into whatever notification channel
is appropriate. The companion script
``backend/app/debug_scripts/check_pg_autovacuum.sh`` covers the part that this
process cannot reach: scraping the postgres container logs for the specific
corruption error pattern.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

# Defaults chosen to err on the side of low noise. Tune via env in the caller.
DEFAULT_AUTOVACUUM_STUCK_MINUTES = 30
DEFAULT_DEAD_RATIO_WARN = 0.10  # 10% dead tuples
DEFAULT_DEAD_TUPLES_MIN = 100_000  # don't warn on tiny tables
DEFAULT_IDLE_IN_TX_MINUTES = 30


@dataclass
class PostgresHealthFindings:
    stuck_autovacuums: list[dict[str, Any]] = field(default_factory=list)
    bloated_tables: list[dict[str, Any]] = field(default_factory=list)
    idle_in_transactions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def has_alerts(self) -> bool:
        return bool(self.stuck_autovacuums or self.bloated_tables or self.idle_in_transactions)

    def to_summary(self) -> dict[str, Any]:
        return {
            "stuck_autovacuum_count": len(self.stuck_autovacuums),
            "bloated_table_count": len(self.bloated_tables),
            "idle_in_tx_count": len(self.idle_in_transactions),
            "has_alerts": self.has_alerts,
        }


def check_postgres_autovacuum_health(
    database_url: str,
    *,
    autovacuum_stuck_minutes: int = DEFAULT_AUTOVACUUM_STUCK_MINUTES,
    dead_ratio_warn: float = DEFAULT_DEAD_RATIO_WARN,
    dead_tuples_min: int = DEFAULT_DEAD_TUPLES_MIN,
    idle_in_tx_minutes: int = DEFAULT_IDLE_IN_TX_MINUTES,
) -> PostgresHealthFindings:
    """Run the three probes and return structured findings.

    Always closes its own connection. Never raises — a failed probe is logged
    and an empty findings object is returned (the caller treats that as
    "unknown", not "healthy").
    """
    findings = PostgresHealthFindings()
    try:
        conn = psycopg2.connect(database_url)
    except Exception as exc:  # noqa: BLE001
        logger.error("postgres_health: cannot connect for probe: %s", exc)
        return findings

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            # 1. Autovacuum running on the same relation for too long
            cur.execute(
                """
                SELECT pid,
                       query,
                       state,
                       backend_start,
                       xact_start,
                       query_start,
                       EXTRACT(EPOCH FROM (now() - query_start))::int AS seconds_running
                  FROM pg_stat_activity
                 WHERE backend_type = 'autovacuum worker'
                   AND query_start < now() - (%s || ' minutes')::interval
                """,
                (autovacuum_stuck_minutes,),
            )
            findings.stuck_autovacuums = [dict(r) for r in cur.fetchall()]

            # 2. Tables with high dead-tuple ratios
            cur.execute(
                """
                SELECT relname,
                       schemaname,
                       n_live_tup,
                       n_dead_tup,
                       last_vacuum,
                       last_autovacuum,
                       CASE WHEN n_live_tup > 0
                            THEN n_dead_tup::float / n_live_tup
                            ELSE NULL
                       END AS dead_ratio
                  FROM pg_stat_user_tables
                 WHERE n_dead_tup >= %s
                   AND n_live_tup > 0
                   AND (n_dead_tup::float / n_live_tup) >= %s
                 ORDER BY n_dead_tup DESC
                 LIMIT 25
                """,
                (dead_tuples_min, dead_ratio_warn),
            )
            findings.bloated_tables = [dict(r) for r in cur.fetchall()]

            # 3. Idle-in-transaction sessions older than threshold
            cur.execute(
                """
                SELECT pid,
                       usename,
                       application_name,
                       state,
                       xact_start,
                       EXTRACT(EPOCH FROM (now() - xact_start))::int AS seconds_in_tx,
                       query
                  FROM pg_stat_activity
                 WHERE state = 'idle in transaction'
                   AND xact_start < now() - (%s || ' minutes')::interval
                """,
                (idle_in_tx_minutes,),
            )
            findings.idle_in_transactions = [dict(r) for r in cur.fetchall()]
    except Exception as exc:  # noqa: BLE001
        logger.error("postgres_health: probe query failed: %s", exc)
        return findings
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass

    if findings.stuck_autovacuums:
        for row in findings.stuck_autovacuums:
            logger.error(
                "postgres_health STUCK_AUTOVACUUM pid=%s seconds=%d query=%.200s",
                row.get("pid"), row.get("seconds_running"), row.get("query"),
            )
    if findings.bloated_tables:
        for row in findings.bloated_tables:
            logger.warning(
                "postgres_health BLOAT relation=%s.%s live=%d dead=%d ratio=%.2f last_autovacuum=%s",
                row.get("schemaname"), row.get("relname"),
                row.get("n_live_tup"), row.get("n_dead_tup"),
                row.get("dead_ratio") or 0.0, row.get("last_autovacuum"),
            )
    if findings.idle_in_transactions:
        for row in findings.idle_in_transactions:
            logger.warning(
                "postgres_health IDLE_IN_TX pid=%s app=%s seconds=%d",
                row.get("pid"), row.get("application_name"), row.get("seconds_in_tx"),
            )

    if not findings.has_alerts:
        logger.info("postgres_health: ok (no autovacuum or bloat alerts)")

    return findings
