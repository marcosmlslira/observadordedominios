"""S3-compatible storage client (works with MinIO and AWS S3)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import boto3
from botocore.config import Config as BotoConfig

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_s3_client():
    """Create a boto3 S3 client configured for either MinIO or AWS."""
    extra: dict = {}
    if settings.S3_ENDPOINT_URL:
        extra["endpoint_url"] = settings.S3_ENDPOINT_URL

    return boto3.client(
        "s3",
        region_name=settings.S3_REGION,
        aws_access_key_id=settings.S3_ACCESS_KEY_ID,
        aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
        config=BotoConfig(s3={"addressing_style": "path"}) if settings.S3_FORCE_PATH_STYLE else None,
        **extra,
    )


class S3Storage:
    """Upload / download zone files to S3-compatible storage."""

    def __init__(self) -> None:
        self.client = _get_s3_client()
        self.bucket = settings.S3_BUCKET

    # ── Ensure bucket exists (dev convenience) ──────────────
    def ensure_bucket(self) -> None:
        """Create the bucket if it does not exist (useful for MinIO dev)."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            logger.info("Creating S3 bucket: %s", self.bucket)
            self.client.create_bucket(Bucket=self.bucket)

    # ── Key generation ──────────────────────────────────────
    @staticmethod
    def build_object_key(tld: str, run_id: UUID, now: datetime | None = None) -> str:
        """
        Build the standard key:
        zones/czds/{tld}/{yyyy}/{mm}/{dd}/{run_id}/{tld}.zone.gz
        """
        ts = now or datetime.now(timezone.utc)
        return (
            f"zones/czds/{tld}/{ts:%Y}/{ts:%m}/{ts:%d}/"
            f"{run_id}/{tld}.zone.gz"
        )

    # ── Upload ──────────────────────────────────────────────
    def upload_zone_file(
        self,
        local_path: Path,
        object_key: str,
        *,
        tld: str,
        run_id: UUID,
        sha256: str,
    ) -> str:
        """
        Upload *local_path* to S3 and return the ETag.
        """
        logger.info("Uploading %s → s3://%s/%s", local_path, self.bucket, object_key)
        metadata = {
            "source": "czds",
            "tld": tld,
            "run_id": str(run_id),
            "sha256": sha256,
        }
        resp = self.client.upload_file(
            str(local_path),
            self.bucket,
            object_key,
            ExtraArgs={"Metadata": metadata},
        )
        # Get ETag
        head = self.client.head_object(Bucket=self.bucket, Key=object_key)
        etag = head.get("ETag", "").strip('"')
        logger.info("Upload complete: ETag=%s", etag)
        return etag

    # ── Delete ─────────────────────────────────────────────
    def delete_object(self, object_key: str) -> None:
        """Delete a single object from S3."""
        logger.info("Deleting s3://%s/%s", self.bucket, object_key)
        self.client.delete_object(Bucket=self.bucket, Key=object_key)

    def download_object(self, object_key: str) -> tuple[bytes, str | None]:
        """Download object content and return bytes plus content type."""
        resp = self.client.get_object(Bucket=self.bucket, Key=object_key)
        body = resp["Body"].read()
        return body, resp.get("ContentType")
