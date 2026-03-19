"""Repository for zone_file_artifact."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.zone_file_artifact import ZoneFileArtifact


class ZoneArtifactRepository:
    """Insert and query zone file artifact metadata."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def create_artifact(
        self,
        *,
        source: str,
        tld: str,
        bucket: str,
        object_key: str,
        etag: str | None,
        sha256: str,
        size_bytes: int,
        downloaded_at: datetime | None = None,
    ) -> ZoneFileArtifact:
        artifact = ZoneFileArtifact(
            id=uuid.uuid4(),
            source=source,
            tld=tld,
            bucket=bucket,
            object_key=object_key,
            etag=etag,
            sha256=sha256,
            size_bytes=size_bytes,
            downloaded_at=downloaded_at or datetime.now(timezone.utc),
        )
        self.db.add(artifact)
        self.db.flush()
        return artifact
