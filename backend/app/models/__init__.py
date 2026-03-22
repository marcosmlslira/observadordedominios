"""Models package — import all models so Alembic can detect them."""

from app.models.base import Base, TimestampMixin
from app.models.czds_tld_policy import CzdsTldPolicy
from app.models.domain import Domain
from app.models.ingestion_checkpoint import IngestionCheckpoint
from app.models.ingestion_run import IngestionRun
from app.models.monitored_brand import MonitoredBrand
from app.models.similarity_match import SimilarityMatch
from app.models.similarity_scan_cursor import SimilarityScanCursor
from app.models.zone_file_artifact import ZoneFileArtifact

__all__ = [
    "Base",
    "TimestampMixin",
    "CzdsTldPolicy",
    "Domain",
    "IngestionCheckpoint",
    "IngestionRun",
    "MonitoredBrand",
    "SimilarityMatch",
    "SimilarityScanCursor",
    "ZoneFileArtifact",
]
