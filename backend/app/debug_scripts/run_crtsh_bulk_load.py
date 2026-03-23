"""Run crt.sh historical bulk load for .br domains.

Usage from Docker:
  docker exec -it <backend_container> python -m app.debug_scripts.run_crtsh_bulk_load

Options (via env vars):
  BULK_DRY_RUN=true      — Test without writing to DB
  BULK_SUBTLDS=com.br    — Comma-separated list (default: all)
  BULK_YEARS=2024,2025   — Comma-separated list (default: 2015-2028)
"""

import logging
import os
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from app.services.use_cases.bulk_load_crtsh import run_bulk_load

dry_run = os.environ.get("BULK_DRY_RUN", "").lower() in ("true", "1", "yes")

subtlds = None
if os.environ.get("BULK_SUBTLDS"):
    subtlds = [s.strip() for s in os.environ["BULK_SUBTLDS"].split(",") if s.strip()]

years = None
if os.environ.get("BULK_YEARS"):
    years = [int(y.strip()) for y in os.environ["BULK_YEARS"].split(",") if y.strip()]

run_bulk_load(subtlds=subtlds, years=years, dry_run=dry_run)
