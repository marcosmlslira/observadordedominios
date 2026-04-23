"""High-level ingestion job submitter for Databricks.

Uploads the thin notebook from the installed package to the Databricks workspace
and submits one notebook run per TLD.  Credentials are injected as base_parameters
so no secrets are ever hardcoded in the notebook source.
"""

from __future__ import annotations

import logging
import importlib.resources
from datetime import date
from pathlib import Path
from typing import Any

from ingestion.config.settings import Settings
from ingestion.databricks.client import DatabricksClient

log = logging.getLogger(__name__)

# TLDs that are too large for local execution and MUST run on Databricks.
LARGE_TLDS: frozenset[str] = frozenset(
    {
        "com", "net", "org", "de", "uk", "br", "info", "biz", "nl", "cn",
        "ru", "au", "fr", "it", "es", "pl", "ca", "jp", "in", "eu", "app",
    }
)


def _locate_notebook(source: str) -> Path:
    """Return the filesystem path of the packaged thin notebook."""
    pkg = importlib.resources.files("ingestion.databricks.notebooks")
    ref = pkg.joinpath(f"{source}_ingestion.py")
    # as_file extracts to a temp dir when running from a zip/wheel
    with importlib.resources.as_file(ref) as path:
        return Path(path)


def _build_base_parameters(cfg: Settings, tld: str, snapshot_date: str | None) -> dict[str, str]:
    """Build widget base_parameters — all credentials injected here, not in the notebook."""
    params: dict[str, str] = {
        "TARGET_TLD": tld,
        # R2 storage
        "R2_ACCOUNT_ID": cfg.r2_account_id,
        "R2_ACCESS_KEY_ID": cfg.r2_access_key_id,
        "R2_SECRET_ACCESS_KEY": cfg.r2_secret_access_key,
        "R2_BUCKET": cfg.r2_bucket,
        "R2_PREFIX": cfg.r2_prefix,
        # CZDS
        "CZDS_USERNAME": cfg.czds_username,
        "CZDS_PASSWORD": cfg.czds_password,
        # Git ref for pip install
        "INGESTION_GIT_REF": cfg.ingestion_git_ref,
        # Logging
        "LOG_FORMAT": "text",
    }
    if snapshot_date:
        params["SNAPSHOT_DATE_OVERRIDE"] = snapshot_date
    return params


class DatabricksSubmitter:
    """Uploads the correct notebook and submits one Databricks run per TLD."""

    def __init__(self, cfg: Settings) -> None:
        if not cfg.databricks_host or not cfg.databricks_token:
            raise ValueError(
                "DATABRICKS_HOST and DATABRICKS_TOKEN must be set to submit Databricks jobs"
            )
        self.cfg = cfg
        self.client = DatabricksClient(cfg.databricks_host, cfg.databricks_token)

    def submit_batch(
        self,
        source: str,
        tlds: list[str],
        *,
        snapshot_date: str | None = None,
        wait: bool = True,
        timeout_seconds: int = 14400,
        serverless: bool = True,
    ) -> dict[str, Any]:
        """Upload the notebook for *source* and submit ONE job run for a batch of TLDs.

        The notebook receives TLDS=tld1,tld2,... and loops with per-TLD isolation.
        TARGET_TLD is set to the first TLD for backward compatibility.

        Returns:
            dict with run_id, tlds, status, result_state
        """
        if not tlds:
            return {"run_id": None, "tlds": [], "status": "skipped"}

        notebook_local = _locate_notebook(source)
        workspace_path = self.cfg.databricks_workspace_path.rstrip("/")
        workspace_nb = f"{workspace_path}/{source}_ingestion"
        parent = workspace_nb.rsplit("/", 1)[0]

        self.client.workspace_mkdirs(parent)
        self.client.workspace_import(local_file=notebook_local, workspace_path=workspace_nb)
        log.info("databricks notebook uploaded: %s → %s", notebook_local.name, workspace_nb)

        # First TLD as TARGET_TLD for backward compat; TLDS drives the loop
        base_params = _build_base_parameters(self.cfg, tlds[0], snapshot_date)
        base_params["TLDS"] = ",".join(tlds)

        today = snapshot_date or date.today().isoformat()
        run_name = f"ingestion-{source}-batch-{len(tlds)}tlds-{today}"

        run_id = self.client.submit_notebook_run(
            run_name=run_name,
            notebook_path=workspace_nb,
            base_parameters=base_params,
            serverless=serverless,
            timeout_seconds=timeout_seconds,
        )
        log.info("databricks batch submitted: run_id=%d source=%s tlds=%s", run_id, source, tlds)

        if not wait:
            return {"run_id": run_id, "tlds": tlds, "status": "submitted"}

        run = self.client.wait(run_id)
        result_state = run.get("state", {}).get("result_state", "UNKNOWN")
        ok = result_state == "SUCCESS"
        return {
            "run_id": run_id,
            "tlds": tlds,
            "status": "ok" if ok else "error",
            "result_state": result_state,
        }

    def submit(
        self,
        source: str,
        tld: str,
        *,
        snapshot_date: str | None = None,
        wait: bool = True,
        timeout_seconds: int = 7200,
        serverless: bool = True,
    ) -> dict[str, Any]:
        """Upload the notebook for *source* and submit a single-TLD job run.

        Args:
            source: "czds" or "openintel"
            tld: target TLD without leading dot (e.g. "br")
            snapshot_date: ISO date override, or None for today
            wait: if True, poll until the run reaches a terminal state
            timeout_seconds: Databricks run timeout (0 = no limit)
            serverless: use serverless compute (default True)

        Returns:
            dict with run_id, tld, status, result_state
        """
        notebook_local = _locate_notebook(source)
        # Use posixpath-style string ops — never Path() — so slashes stay as '/' on Windows too
        workspace_path = self.cfg.databricks_workspace_path.rstrip("/")
        workspace_nb = f"{workspace_path}/{source}_ingestion"
        parent = workspace_nb.rsplit("/", 1)[0]

        # Ensure parent directory exists in the workspace
        self.client.workspace_mkdirs(parent)

        # Upload current notebook source
        self.client.workspace_import(local_file=notebook_local, workspace_path=workspace_nb)
        log.info("databricks notebook uploaded: %s → %s", notebook_local.name, workspace_nb)

        base_params = _build_base_parameters(self.cfg, tld, snapshot_date)
        today = snapshot_date or date.today().isoformat()
        run_name = f"ingestion-{source}-{tld}-{today}"

        run_id = self.client.submit_notebook_run(
            run_name=run_name,
            notebook_path=workspace_nb,
            base_parameters=base_params,
            serverless=serverless,
            timeout_seconds=timeout_seconds,
        )
        log.info("databricks run submitted: run_id=%d source=%s tld=%s", run_id, source, tld)

        if not wait:
            return {"run_id": run_id, "tld": tld, "status": "submitted"}

        run = self.client.wait(run_id)
        result_state = run.get("state", {}).get("result_state", "UNKNOWN")
        ok = result_state == "SUCCESS"
        return {
            "run_id": run_id,
            "tld": tld,
            "status": "ok" if ok else "error",
            "result_state": result_state,
        }
