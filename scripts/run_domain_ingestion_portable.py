from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from domain_ingestion_portable.config import (
    CZDSConfig,
    OpenIntelConfig,
    PipelineConfig,
    R2Config,
    RuntimeConfig,
    parse_date,
)
from domain_ingestion_portable.runner import run_pipeline
from domain_ingestion_portable.runner_sharded import run_pipeline_sharded


# ===== SIMPLE VARIABLES (EDIT HERE) =====

# ---------- R2 ----------
R2_ACCOUNT_ID = "c7d69182e6ae8686a3edc7bdd6eae9f8"
R2_ACCESS_KEY_ID = "de77bf7b6c20ebce5b86115bb2c6d67f"
R2_SECRET_ACCESS_KEY = "5e76101a6903df86bf1bc273acb7bea65650b9be6cc1035523fc9d2eea6d95d1"
R2_BUCKET = "observadordedominios"
R2_REGION = "auto"
R2_PREFIX = "lake/domain_ingestion_nospark_portable"

# ---------- Execution ----------
RUN_CZDS = True
RUN_OPENINTEL = True
RAW_RETENTION_DAYS = 5
MAX_FILES_PER_STEP = 5000
MAX_DOMAINS_SAFETY_LIMIT = 50_000_000
SAVE_FULL_SNAPSHOT_ON_FIRST_RUN = True
INGEST_CHUNK_ROWS = 1_500_000
ENFORCE_ALL_TLDS_SUCCESS = True

# ---------- CZDS ----------
CZDS_USERNAME = "marcosmlslira@gmail.com"
CZDS_PASSWORD = "mls1509TI@,,2099"
CZDS_TLDS = "all"
CZDS_EXCLUDE_TLDS = ""
CZDS_MAX_TLDS = 0
CZDS_START_DATE = None  # "2026-04-01" or None
CZDS_SNAPSHOT_DATE_OVERRIDE = "today"  # "2026-04-22" | "today" | None

# ---------- OpenINTEL ----------
OPENINTEL_TLDS = "ac,br,uk,de,fr,se,nu,ch,li,sk,ee"
OPENINTEL_MAX_TLDS = 0
OPENINTEL_MODE = "auto"  # auto|zonefile|cctld-web
OPENINTEL_START_DATE = None  # "2026-04-01" or None
OPENINTEL_SNAPSHOT_DATE_OVERRIDE = "today"  # "2026-04-22" | "today" | None
OPENINTEL_MAX_LOOKBACK_DAYS = 14
OPENINTEL_MAX_SCAN_DAYS = 365

# ---------- Method ----------
# "sharded" (current) | "legacy"
PIPELINE_METHOD = "sharded"


def build_config() -> PipelineConfig:
    return PipelineConfig(
        r2=R2Config(
            account_id=R2_ACCOUNT_ID,
            access_key_id=R2_ACCESS_KEY_ID,
            secret_access_key=R2_SECRET_ACCESS_KEY,
            bucket=R2_BUCKET,
            region=R2_REGION,
            prefix=R2_PREFIX,
        ),
        runtime=RuntimeConfig(
            run_czds=RUN_CZDS,
            run_openintel=RUN_OPENINTEL,
            raw_retention_days=RAW_RETENTION_DAYS,
            max_files_per_step=MAX_FILES_PER_STEP,
            max_domains_safety_limit=MAX_DOMAINS_SAFETY_LIMIT,
            save_full_snapshot_on_first_run=SAVE_FULL_SNAPSHOT_ON_FIRST_RUN,
            ingest_chunk_rows=INGEST_CHUNK_ROWS,
            enforce_all_tlds_success=ENFORCE_ALL_TLDS_SUCCESS,
        ),
        czds=CZDSConfig(
            username=CZDS_USERNAME,
            password=CZDS_PASSWORD,
            tlds=CZDS_TLDS,
            exclude_tlds=CZDS_EXCLUDE_TLDS,
            max_tlds=CZDS_MAX_TLDS,
            start_date=parse_date(CZDS_START_DATE),
            snapshot_date_override=parse_date(CZDS_SNAPSHOT_DATE_OVERRIDE),
        ),
        openintel=OpenIntelConfig(
            tlds=OPENINTEL_TLDS,
            max_tlds=OPENINTEL_MAX_TLDS,
            mode=OPENINTEL_MODE,
            start_date=parse_date(OPENINTEL_START_DATE),
            snapshot_date_override=parse_date(OPENINTEL_SNAPSHOT_DATE_OVERRIDE),
            max_lookback_days=OPENINTEL_MAX_LOOKBACK_DAYS,
            max_scan_days=OPENINTEL_MAX_SCAN_DAYS,
        ),
    )


if __name__ == "__main__":
    config = build_config()
    if PIPELINE_METHOD == "legacy":
        run_pipeline(config)
    else:
        run_pipeline_sharded(config)
