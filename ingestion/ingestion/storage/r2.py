"""R2 storage client — thin boto3 wrapper for Cloudflare R2 (S3-compatible)."""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from typing import Iterable

import boto3
import polars as pl
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from ingestion.config.settings import Settings


class R2Storage:
    def __init__(self, cfg: Settings):
        self._bucket = cfg.r2_bucket
        endpoint = f"https://{cfg.r2_account_id}.r2.cloudflarestorage.com"
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=cfg.r2_access_key_id,
            aws_secret_access_key=cfg.r2_secret_access_key,
            region_name="auto",
            config=BotoConfig(
                s3={"addressing_style": "path"},
                retries={"max_attempts": 10, "mode": "standard"},
                connect_timeout=20,
                read_timeout=120,
            ),
        )

    # ── Probes ────────────────────────────────────────────────────────────────

    def probe_api(self) -> None:
        self.client.head_bucket(Bucket=self._bucket)

    # ── Key checks ────────────────────────────────────────────────────────────

    def key_exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def get_parquet_df_or_empty(self, key: str, columns: list[str]) -> pl.DataFrame:
        if not self.key_exists(key):
            return pl.DataFrame({c: pl.Series(name=c, values=[], dtype=pl.Utf8) for c in columns})
        raw = self.get_bytes(key)
        df = pl.read_parquet(io.BytesIO(raw))
        for c in columns:
            if c not in df.columns:
                df = df.with_columns(pl.lit(None).cast(pl.Utf8).alias(c))
        return df.select(columns)

    # ── Write ─────────────────────────────────────────────────────────────────

    def put_bytes(
        self, key: str, payload: bytes, content_type: str = "application/octet-stream"
    ) -> None:
        self.client.put_object(
            Bucket=self._bucket, Key=key, Body=payload, ContentType=content_type
        )

    def put_json(self, key: str, payload: dict | str) -> None:
        if isinstance(payload, str):
            data = payload.encode("utf-8")
        else:
            data = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.put_bytes(key, data, content_type="application/json")

    def put_parquet_df(self, key: str, df: pl.DataFrame) -> None:
        buf = io.BytesIO()
        df.write_parquet(buf, compression="zstd", statistics=True)
        self.put_bytes(key, buf.getvalue(), content_type="application/octet-stream")

    # ── List / Delete ─────────────────────────────────────────────────────────

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def delete_keys(self, keys: Iterable[str]) -> int:
        buffer: list[dict[str, str]] = []
        deleted = 0
        for key in keys:
            buffer.append({"Key": key})
            if len(buffer) == 1000:
                self.client.delete_objects(
                    Bucket=self._bucket, Delete={"Objects": buffer}
                )
                deleted += len(buffer)
                buffer.clear()
        if buffer:
            self.client.delete_objects(Bucket=self._bucket, Delete={"Objects": buffer})
            deleted += len(buffer)
        return deleted

    def delete_older_than(self, prefix: str, retention_days: int) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        paginator = self.client.get_paginator("list_objects_v2")
        victims: list[str] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                if obj["LastModified"] < cutoff:
                    victims.append(obj["Key"])
        return self.delete_keys(victims)
