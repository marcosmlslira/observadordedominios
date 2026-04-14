"""MonitoringQueryService — assembles monitoring dashboard data from multiple repositories."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories.monitoring_cycle_repository import MonitoringCycleRepository
from app.repositories.match_state_snapshot_repository import MatchStateSnapshotRepository
from app.repositories.brand_domain_health_repository import BrandDomainHealthRepository


class MonitoringQueryService:
    """
    Read-only aggregation service for the monitoring API layer.
    Composes data from cycle, snapshot, and health repositories.
    Route handlers call this instead of fanning out to 3 separate repos.
    """

    def __init__(self, db: Session) -> None:
        self.cycle_repo = MonitoringCycleRepository(db)
        self.snapshot_repo = MatchStateSnapshotRepository(db)
        self.health_repo = BrandDomainHealthRepository(db)

    def get_monitoring_summary(self, brand_id: UUID) -> dict:
        """
        Return dict with:
          latest_cycle: dict | None
          threat_counts: dict
          overall_health: str
        """
        # Threat counts from snapshots (source of truth)
        bucket_counts = self.snapshot_repo.count_by_bucket_active(brand_id)
        threat_counts = {
            "immediate_attention": bucket_counts.get("immediate_attention", 0),
            "defensive_gap": bucket_counts.get("defensive_gap", 0),
            "watchlist": bucket_counts.get("watchlist", 0),
        }
        active_threat_total = sum(threat_counts.values())

        # Latest cycle
        cycle = self.cycle_repo.get_latest_for_brand(brand_id)
        latest_cycle = None
        if cycle:
            latest_cycle = {
                "cycle_date": cycle.cycle_date,
                "health_status": cycle.health_status,
                "scan_status": cycle.scan_status,
                "enrichment_status": cycle.enrichment_status,
                "new_matches_count": cycle.new_matches_count or 0,
                # Use active snapshot count when cycle counter is stale (e.g. after backfill)
                "threats_detected": max(cycle.threats_detected or 0, active_threat_total),
                "dismissed_count": cycle.dismissed_count or 0,
            }

        # Overall health from domain health records (worst-case across all domains)
        health_records = self.health_repo.list_for_brand(brand_id)
        overall_health = _derive_overall_health(health_records)

        return {
            "latest_cycle": latest_cycle,
            "threat_counts": threat_counts,
            "overall_health": overall_health,
        }


def _derive_overall_health(health_records: list) -> str:
    """Aggregate overall_status from all brand domain health records. Worst-case wins."""
    if not health_records:
        return "unknown"
    STATUS_ORDER = {"critical": 3, "warning": 2, "healthy": 1, "unknown": 0}
    worst = max(
        (STATUS_ORDER.get(h.overall_status, 0) for h in health_records),
        default=0,
    )
    return {3: "critical", 2: "warning", 1: "healthy", 0: "unknown"}[worst]
