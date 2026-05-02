"""Models package — import all models so Alembic can detect them."""

from app.models.base import Base, TimestampMixin
from app.models.brand_domain_health import BrandDomainHealth
from app.models.domain import Domain
from app.models.ingestion_checkpoint import IngestionCheckpoint
from app.models.ingestion_run import IngestionRun
from app.models.ingestion_shard_checkpoint import IngestionShardCheckpoint
from app.models.openintel_tld_status import OpenintelTldStatus
from app.models.match_state_snapshot import MatchStateSnapshot
from app.models.monitored_brand_alias import MonitoredBrandAlias
from app.models.monitored_brand import MonitoredBrand
from app.models.monitored_brand_domain import MonitoredBrandDomain
from app.models.monitored_brand_seed import MonitoredBrandSeed
from app.models.monitoring_cycle import MonitoringCycle
from app.models.monitoring_event import MonitoringEvent
from app.models.similarity_match import SimilarityMatch
from app.models.similarity_scan_cursor import SimilarityScanCursor
from app.models.similarity_scan_job import SimilarityScanJob
from app.models.tool_execution import ToolExecution

__all__ = [
    "Base",
    "TimestampMixin",
    "BrandDomainHealth",
    "Domain",
    "IngestionCheckpoint",
    "IngestionRun",
    "IngestionShardCheckpoint",
    "OpenintelTldStatus",
    "MatchStateSnapshot",
    "MonitoredBrandAlias",
    "MonitoredBrand",
    "MonitoredBrandDomain",
    "MonitoredBrandSeed",
    "MonitoringCycle",
    "MonitoringEvent",
    "SimilarityMatch",
    "SimilarityScanCursor",
    "SimilarityScanJob",
    "ToolExecution",
]
