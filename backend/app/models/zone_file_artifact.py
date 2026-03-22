"""ZoneFileArtifact — metadata of a raw zone file stored in S3."""

import uuid

from sqlalchemy import BigInteger, Column, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, TimestampMixin


class ZoneFileArtifact(Base, TimestampMixin):
    __tablename__ = "zone_file_artifact"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source = Column(String(32), nullable=False)
    tld = Column(String(24), nullable=False)
    bucket = Column(String(128), nullable=False)
    object_key = Column(Text, nullable=False)
    etag = Column(String(128), nullable=True)
    sha256 = Column(String(64), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    downloaded_at = Column(DateTime(timezone=True), nullable=False)

    # ── Indexes ─────────────────────────────────────────────
    __table_args__ = (
        Index("ix_artifact_tld_downloaded", "tld", downloaded_at.desc()),
    )
