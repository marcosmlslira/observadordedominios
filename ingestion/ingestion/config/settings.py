"""Pydantic Settings — all ingestion configuration from environment variables."""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── R2 / S3-compatible storage ────────────────────────────────────────────
    r2_account_id: str = Field(default="", alias="R2_ACCOUNT_ID")
    r2_access_key_id: str = Field(default="", alias="R2_ACCESS_KEY_ID")
    r2_secret_access_key: str = Field(default="", alias="R2_SECRET_ACCESS_KEY")
    r2_bucket: str = Field(default="observadordedominios", alias="R2_BUCKET")
    r2_prefix: str = Field(default="lake/domain_ingestion", alias="R2_PREFIX")

    # ── CZDS (ICANN zone file access) ─────────────────────────────────────────
    czds_username: str = Field(default="", alias="CZDS_USERNAME")
    czds_password: str = Field(default="", alias="CZDS_PASSWORD")
    czds_tlds: str = Field(default="all", alias="CZDS_TLDS")
    czds_max_tlds: int = Field(default=0, alias="CZDS_MAX_TLDS")

    # ── OpenINTEL ─────────────────────────────────────────────────────────────
    openintel_tlds: str = Field(
        default="ac,br,uk,de,fr,se,nu,ch,li,sk,ee", alias="OPENINTEL_TLDS"
    )
    openintel_mode: str = Field(default="auto", alias="OPENINTEL_MODE")
    openintel_max_tlds: int = Field(default=0, alias="OPENINTEL_MAX_TLDS")
    openintel_max_lookback_days: int = Field(default=14, alias="OPENINTEL_MAX_LOOKBACK_DAYS")
    openintel_max_scan_days: int = Field(default=365, alias="OPENINTEL_MAX_SCAN_DAYS")
    openintel_snapshot_date_override: str = Field(default="", alias="OPENINTEL_SNAPSHOT_DATE_OVERRIDE")

    # OpenINTEL S3 (zonefile source)
    openintel_zonefile_bucket: str = Field(default="openintel-public", alias="OPENINTEL_ZONEFILE_BUCKET")
    openintel_zonefile_prefix: str = Field(default="fdns/basis=zonefile/", alias="OPENINTEL_ZONEFILE_PREFIX")
    openintel_zonefile_endpoint: str = Field(default="https://object.openintel.nl", alias="OPENINTEL_ZONEFILE_ENDPOINT")
    openintel_zonefile_region: str = Field(default="us-east-1", alias="OPENINTEL_ZONEFILE_REGION")
    openintel_zonefile_qname_column: str = Field(default="query_name", alias="OPENINTEL_ZONEFILE_QNAME_COLUMN")
    openintel_zonefile_tlds: str = Field(default="ch,ee,fed.us,fr,gov,li,nu,root,se,sk", alias="OPENINTEL_ZONEFILE_TLDS")
    # Snapshots whose total Parquet bytes meet/exceed this threshold are
    # processed via the streaming sharded stager (memory-bounded). Smaller
    # snapshots stay on the legacy in-memory path. Default: 200 MiB.
    openintel_shard_threshold_bytes: int = Field(
        default=200 * 1024 * 1024, alias="OPENINTEL_SHARD_THRESHOLD_BYTES"
    )

    # OpenINTEL web (cctld-web source)
    openintel_web_base: str = Field(default="https://openintel.nl/download/domain-lists/cctlds", alias="OPENINTEL_WEB_BASE")
    openintel_web_files_base: str = Field(default="https://object.openintel.nl/seeseetld/lists", alias="OPENINTEL_WEB_FILES_BASE")
    openintel_web_cookie_name: str = Field(default="openintel-data-agreement-accepted", alias="OPENINTEL_WEB_COOKIE_NAME")
    openintel_web_cookie_value: str = Field(default="true", alias="OPENINTEL_WEB_COOKIE_VALUE")

    # ── PostgreSQL ────────────────────────────────────────────────────────────
    database_url: str = Field(default="", alias="DATABASE_URL")

    # ── Databricks ────────────────────────────────────────────────────────────
    databricks_host: str = Field(default="", alias="DATABRICKS_HOST")
    databricks_token: str = Field(default="", alias="DATABRICKS_TOKEN")
    databricks_workspace_path: str = Field(
        default="/ingestion/notebooks", alias="DATABRICKS_WORKSPACE_PATH"
    )
    databricks_serverless_performance_target: str = Field(
        default="", alias="DATABRICKS_SERVERLESS_PERFORMANCE_TARGET"
    )
    ingestion_git_ref: str = Field(default="main", alias="INGESTION_GIT_REF")
    ingestion_stale_timeout_minutes: int = Field(default=45, alias="INGESTION_STALE_TIMEOUT_MINUTES")
    ingestion_execution_mode_openintel: str = Field(
        default="hybrid",
        alias="INGESTION_EXECUTION_MODE_OPENINTEL",
    )
    ingestion_execution_mode_czds: str = Field(
        default="hybrid",
        alias="INGESTION_EXECUTION_MODE_CZDS",
    )

    # Databricks batch sizes — limits TLDs per job to avoid OOM and rate-limit errors.
    # OpenINTEL: smaller batches to avoid serverless memory exhaustion.
    # CZDS: smaller batches to avoid ICANN authentication rate-limiting (429).
    databricks_batch_size_openintel: int = Field(
        default=50, alias="DATABRICKS_BATCH_SIZE_OPENINTEL"
    )
    databricks_batch_size_czds: int = Field(
        default=100, alias="DATABRICKS_BATCH_SIZE_CZDS"
    )

    # ── Runtime ───────────────────────────────────────────────────────────────
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="json", alias="LOG_FORMAT")
    manual_trigger_token: str = Field(default="", alias="INGESTION_MANUAL_TRIGGER_TOKEN")

    def czds_tld_list(self) -> list[str] | None:
        """Return explicit CZDS TLD list or None (meaning: fetch all from API)."""
        if not self.czds_tlds or self.czds_tlds.strip().lower() == "all":
            return None
        return [t.strip().lower() for t in self.czds_tlds.split(",") if t.strip()]

    def openintel_tld_list(self) -> list[str]:
        return [t.strip().lower() for t in self.openintel_tlds.split(",") if t.strip()]

    def execution_mode_for_source(self, source: str) -> str:
        if source == "openintel":
            mode = self.ingestion_execution_mode_openintel
        elif source == "czds":
            mode = self.ingestion_execution_mode_czds
        else:
            mode = "hybrid"
        normalized = (mode or "hybrid").strip().lower()
        return normalized if normalized in {"hybrid", "databricks_only"} else "hybrid"

    def databricks_batch_size_for_source(self, source: str) -> int:
        """Return the maximum number of TLDs per Databricks job for a source."""
        if source == "openintel":
            return max(1, self.databricks_batch_size_openintel)
        elif source == "czds":
            return max(1, self.databricks_batch_size_czds)
        return 50  # safe default


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_cache() -> None:
    """Clear the cached Settings instance — call before re-reading env vars in notebooks."""
    global _settings
    _settings = None
