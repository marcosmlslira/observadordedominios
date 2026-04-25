from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized == "today":
        return date.today()
    return date.fromisoformat(value.strip())


@dataclass(frozen=True)
class R2Config:
    account_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    region: str = "auto"
    prefix: str = "lake/domain_ingestion_nospark"

    @property
    def endpoint(self) -> str:
        return f"https://{self.account_id}.r2.cloudflarestorage.com"


@dataclass(frozen=True)
class CZDSConfig:
    username: str
    password: str
    base_url: str = "https://czds-api.icann.org"
    auth_url: str = "https://account-api.icann.org/api/authenticate"
    tlds: str = "all"
    exclude_tlds: str = ""
    max_tlds: int = 0
    start_date: date | None = None
    snapshot_date_override: date | None = None


@dataclass(frozen=True)
class OpenIntelConfig:
    tlds: str = "ac,br,uk,de,fr,se,nu,ch,li,sk,ee"
    max_tlds: int = 0
    mode: Literal["auto", "zonefile", "cctld-web"] = "auto"
    start_date: date | None = None
    snapshot_date_override: date | None = None
    max_lookback_days: int = 14
    max_scan_days: int = 365

    zonefile_bucket: str = "openintel-public"
    zonefile_prefix: str = "fdns/basis=zonefile/"
    zonefile_endpoint: str = "https://object.openintel.nl"
    zonefile_region: str = "us-east-1"
    zonefile_qname_column: str = "query_name"
    zonefile_tlds: str = "ch,ee,fed.us,fr,gov,li,nu,root,se,sk"

    web_base: str = "https://openintel.nl/download/domain-lists/cctlds"
    web_files_base: str = "https://object.openintel.nl/seeseetld/lists"
    web_cookie_name: str = "openintel-data-agreement-accepted"
    web_cookie_value: str = "true"


@dataclass(frozen=True)
class RuntimeConfig:
    run_czds: bool = True
    run_openintel: bool = True
    raw_retention_days: int = 5
    max_files_per_step: int = 5000
    max_domains_safety_limit: int = 50_000_000
    save_full_snapshot_on_first_run: bool = True
    # current method: shard-based CZDS processing
    use_sharded_czds: bool = True
    shard_count: int = 128
    ingest_chunk_rows: int = 300_000
    cleanup_stage_after_success: bool = True
    enforce_all_tlds_success: bool = False


@dataclass(frozen=True)
class PipelineConfig:
    r2: R2Config
    runtime: RuntimeConfig
    czds: CZDSConfig
    openintel: OpenIntelConfig
