"""Manage crt.sh bulk jobs from inside the backend container.

Usage from Docker:
  docker exec -it <backend_container> python -m app.debug_scripts.run_crtsh_bulk_load

Options (via env vars):
  BULK_ACTION=start|resume|cancel|list
  BULK_DRY_RUN=true
  BULK_SUBTLDS=com.br,io,de
  BULK_JOB_ID=<uuid>
"""

from __future__ import annotations

import logging
import os
from uuid import UUID

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from app.services.use_cases.bulk_load_crtsh import (  # noqa: E402
    cancel_bulk_job,
    list_bulk_jobs,
    resume_bulk_job,
    run_bulk_job,
    run_bulk_load,
)


def _parse_subtlds() -> list[str] | None:
    raw = os.environ.get("BULK_SUBTLDS", "")
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


def main() -> None:
    action = os.environ.get("BULK_ACTION", "start").strip().lower()
    dry_run = os.environ.get("BULK_DRY_RUN", "").lower() in ("true", "1", "yes")
    subtlds = _parse_subtlds()
    job_id_raw = os.environ.get("BULK_JOB_ID", "").strip()

    if action == "start":
        run_bulk_load(subtlds=subtlds, dry_run=dry_run)
        return

    if action == "list":
        for job in list_bulk_jobs():
            print(
                f"{job.id} status={job.status} resolved={job.resolved_tlds} "
                f"chunks={job.done_chunks}/{job.total_chunks} errors={job.error_chunks}"
            )
        return

    if not job_id_raw:
        raise SystemExit("BULK_JOB_ID is required for resume/cancel.")

    job_id = UUID(job_id_raw)
    if action == "resume":
        job = resume_bulk_job(job_id)
        run_bulk_job(job.id)
        return
    if action == "cancel":
        cancel_bulk_job(job_id)
        return

    raise SystemExit(f"Unsupported BULK_ACTION={action}")


if __name__ == "__main__":
    main()
