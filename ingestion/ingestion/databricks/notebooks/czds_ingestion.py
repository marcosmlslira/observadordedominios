# Databricks notebook source
# MAGIC %md
# MAGIC # CZDS Domain Ingestion — thin notebook
# MAGIC
# MAGIC Installs the `ingestion` package from the repository and delegates execution
# MAGIC to `run_czds_from_env()`.  All credentials are injected by the job submitter
# MAGIC via `base_parameters` — no secrets are hardcoded here.

# COMMAND ----------
# Cell 1: pip install — runs before restartPython so upgraded packages are available

import subprocess
import sys

dbutils.widgets.text("INGESTION_GIT_REF", "main", "Git ref usado no pip install")  # noqa: F821
_git_ref = dbutils.widgets.get("INGESTION_GIT_REF").strip() or "main"  # noqa: F821
_pkg_url = f"git+https://github.com/marcosmlslira/observadordedominios@{_git_ref}#subdirectory=ingestion"

# typing_extensions>=4.12.2 required by pydantic>=2.8 (Sentinel); upgrade first
_r1 = subprocess.run(
    [sys.executable, "-m", "pip", "--disable-pip-version-check", "install",
     "--upgrade", "typing_extensions>=4.12.2"],
    capture_output=True, text=True,
)
if _r1.returncode != 0:
    raise RuntimeError("TYPING_EXT_FAIL: " + _r1.stderr[-2000:])

_r2 = subprocess.run(
    [sys.executable, "-m", "pip", "--disable-pip-version-check", "install", _pkg_url],
    capture_output=True, text=True,
)
if _r2.returncode != 0:
    raise RuntimeError("PIP_FAIL: stdout=" + _r2.stdout[-1500:] + " stderr=" + _r2.stderr[-1500:])

# COMMAND ----------
# Cell 2: restart Python so the newly installed packages are picked up

dbutils.library.restartPython()  # noqa: F821

# COMMAND ----------
# Cell 3: re-declare all widgets (values survive restart), inject env, run ingestion

import os
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")

dbutils.widgets.text("TARGET_TLD", "museum", "TLD sem ponto")  # noqa: F821
dbutils.widgets.text("SNAPSHOT_DATE_OVERRIDE", "", "Data YYYY-MM-DD (vazio = hoje)")  # noqa: F821
dbutils.widgets.text("INGESTION_GIT_REF", "main", "Git ref usado no pip install")  # noqa: F821
dbutils.widgets.text("R2_ACCOUNT_ID", "", "R2 Account ID")  # noqa: F821
dbutils.widgets.text("R2_ACCESS_KEY_ID", "", "R2 Access Key ID")  # noqa: F821
dbutils.widgets.text("R2_SECRET_ACCESS_KEY", "", "R2 Secret Key")  # noqa: F821
dbutils.widgets.text("R2_BUCKET", "observadordedominios", "R2 Bucket")  # noqa: F821
dbutils.widgets.text("R2_PREFIX", "lake/domain_ingestion", "R2 Prefix")  # noqa: F821
dbutils.widgets.text("CZDS_USERNAME", "", "CZDS Username")  # noqa: F821
dbutils.widgets.text("CZDS_PASSWORD", "", "CZDS Password")  # noqa: F821
dbutils.widgets.text("LOG_FORMAT", "text", "Log format")  # noqa: F821

_CRED_WIDGETS = [
    "R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET", "R2_PREFIX", "CZDS_USERNAME", "CZDS_PASSWORD", "LOG_FORMAT",
]
for _key in _CRED_WIDGETS:
    _val = dbutils.widgets.get(_key).strip()  # noqa: F821
    if _val:
        os.environ[_key] = _val

TARGET_TLD = dbutils.widgets.get("TARGET_TLD").strip().lower()  # noqa: F821
SNAPSHOT_DATE_OVERRIDE = dbutils.widgets.get("SNAPSHOT_DATE_OVERRIDE").strip() or None  # noqa: F821

from ingestion.config.settings import reset_settings_cache
from ingestion.runners.czds_runner import run_czds_from_env

reset_settings_cache()

results = run_czds_from_env(tld=TARGET_TLD, snapshot_date=SNAPSHOT_DATE_OVERRIDE)

for r in results:
    print(json.dumps({
        "tld": r.run_key.tld,
        "status": r.status,
        "snapshot": r.snapshot_count,
        "added": r.added_count,
        "removed": r.removed_count,
        "error": r.error_message,
    }))

errors = [r for r in results if r.status == "error"]
if errors:
    msgs = [r.error_message or "unknown" for r in errors]
    raise RuntimeError(f"CZDS ingestion failed for TLD={TARGET_TLD}: {msgs}")

dbutils.notebook.exit("OK")  # noqa: F821
