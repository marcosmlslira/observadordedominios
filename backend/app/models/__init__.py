"""Models package — import all models so Alembic can detect them."""

from app.models.base import Base, TimestampMixin
from app.models.czds_tld_policy import CzdsTldPolicy
from app.models.domain import Domain
from app.models.domain_observation import DomainObservation
from app.models.ingestion_checkpoint import IngestionCheckpoint
from app.models.ingestion_run import IngestionRun
from app.models.zone_file_artifact import ZoneFileArtifact

__all__ = [
    "Base",
    "TimestampMixin",
    "CzdsTldPolicy",
    "Domain",
    "DomainObservation",
    "IngestionCheckpoint",
    "IngestionRun",
    "ZoneFileArtifact",
]
