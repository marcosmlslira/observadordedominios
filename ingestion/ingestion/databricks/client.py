"""Databricks REST API client — adapted from scripts/databricks_remote_runner.py."""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import requests


class DatabricksClient:
    """Thin wrapper around the Databricks REST API."""

    def __init__(self, host: str, token: str) -> None:
        self.host = host.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            }
        )

    def _url(self, endpoint: str) -> str:
        return f"{self.host}{endpoint}"

    def request(
        self,
        method: str,
        endpoint: str,
        *,
        payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resp = self._session.request(
            method=method.upper(),
            url=self._url(endpoint),
            json=payload,
            params=params,
            timeout=90,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Databricks API error {resp.status_code} on {endpoint}: {resp.text[:1000]}"
            )
        return resp.json() if resp.text else {}

    # ── workspace ─────────────────────────────────────────────────────────────

    def workspace_mkdirs(self, path: str) -> None:
        self.request("POST", "/api/2.0/workspace/mkdirs", payload={"path": path})

    def workspace_import(self, *, local_file: Path, workspace_path: str) -> None:
        content = base64.b64encode(local_file.read_bytes()).decode("ascii")
        self.request(
            "POST",
            "/api/2.0/workspace/import",
            payload={
                "path": workspace_path,
                "format": "SOURCE",
                "language": "PYTHON",
                "content": content,
                "overwrite": True,
            },
        )

    # ── jobs/runs ─────────────────────────────────────────────────────────────

    def submit_notebook_run(
        self,
        *,
        run_name: str,
        notebook_path: str,
        base_parameters: dict[str, str] | None = None,
        serverless: bool = True,
        cluster_id: str | None = None,
        new_cluster: dict[str, Any] | None = None,
        timeout_seconds: int = 0,
    ) -> int:
        """Submit a notebook run and return the run_id."""
        if serverless:
            payload: dict[str, Any] = {
                "run_name": run_name,
                "tasks": [
                    {
                        "task_key": "main",
                        "notebook_task": {
                            "notebook_path": notebook_path,
                            "base_parameters": base_parameters or {},
                        },
                    }
                ],
            }
            if timeout_seconds:
                payload["timeout_seconds"] = timeout_seconds
        else:
            payload = {
                "run_name": run_name,
                "timeout_seconds": timeout_seconds,
                "notebook_task": {
                    "notebook_path": notebook_path,
                    "base_parameters": base_parameters or {},
                },
            }
            if cluster_id:
                payload["existing_cluster_id"] = cluster_id
            elif new_cluster:
                payload["new_cluster"] = new_cluster
            else:
                raise ValueError("Provide cluster_id/new_cluster or enable serverless=True")

        data = self.request("POST", "/api/2.1/jobs/runs/submit", payload=payload)
        run_id = data.get("run_id")
        if run_id is None:
            raise RuntimeError(f"runs/submit returned no run_id: {data}")
        return int(run_id)

    def run_get(self, run_id: int) -> dict[str, Any]:
        return self.request("GET", "/api/2.1/jobs/runs/get", params={"run_id": run_id})

    def run_get_output(self, run_id: int) -> dict[str, Any]:
        return self.request("GET", "/api/2.1/jobs/runs/get-output", params={"run_id": run_id})

    def wait(self, run_id: int, poll_seconds: int = 10) -> dict[str, Any]:
        """Poll until the run reaches a terminal state and return the final run object."""
        while True:
            run = self.run_get(run_id)
            state = run.get("state", {})
            lc = state.get("life_cycle_state")
            rs = state.get("result_state")
            msg = state.get("state_message", "")
            print(f"  run_id={run_id} lifecycle={lc} result={rs} {msg}")
            if lc in {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}:
                return run
            time.sleep(poll_seconds)

    # ── clusters (for non-serverless fallback) ────────────────────────────────

    def list_clusters(self) -> list[dict[str, Any]]:
        data = self.request("GET", "/api/2.0/clusters/list")
        return data.get("clusters", [])

    def pick_running_cluster(self) -> str | None:
        running = [c for c in self.list_clusters() if c.get("state") == "RUNNING"]
        return running[0]["cluster_id"] if running else None

    def pick_default_spark_version(self) -> str:
        versions = self.request("GET", "/api/2.0/clusters/spark-versions").get("versions", [])
        lts = [
            v["key"]
            for v in versions
            if v.get("key")
            and "LTS" in (v.get("name") or "").upper()
            and "ML" not in (v.get("name") or "").upper()
            and "GPU" not in (v.get("name") or "").upper()
        ]
        fallback = [v["key"] for v in versions if v.get("key")]
        choice = lts or fallback
        if not choice:
            raise RuntimeError("No spark version available")
        return choice[0]

    def pick_default_node_type(self, min_memory_mb: int = 16000) -> str:
        node_types = self.request("GET", "/api/2.0/clusters/list-node-types").get("node_types", [])
        candidates = [
            (int(nt.get("memory_mb") or 0), float(nt.get("num_cores") or 0), nt["node_type_id"])
            for nt in node_types
            if nt.get("node_type_id")
            and not nt.get("is_hidden")
            and not nt.get("is_deprecated")
            and not nt.get("disabled")
            and int(nt.get("memory_mb") or 0) >= min_memory_mb
        ]
        if not candidates:
            raise RuntimeError(f"No node type with >= {min_memory_mb} MB memory")
        return sorted(candidates)[0][2]

    # ── identity ──────────────────────────────────────────────────────────────

    def current_user(self) -> dict[str, Any]:
        return self.request("GET", "/api/2.0/preview/scim/v2/Me")
