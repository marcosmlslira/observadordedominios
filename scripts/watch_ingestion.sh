#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-https://api.observadordedominios.com.br}"
EMAIL="${OBS_ADMIN_EMAIL:-}"
PASSWORD="${OBS_ADMIN_PASSWORD:-}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-15}"
ONCE="${ONCE:-0}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="$2"
      shift 2
      ;;
    --email)
      EMAIL="$2"
      shift 2
      ;;
    --password)
      PASSWORD="$2"
      shift 2
      ;;
    --interval)
      INTERVAL_SECONDS="$2"
      shift 2
      ;;
    --once)
      ONCE=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ -z "$EMAIL" ]]; then
  echo "Set --email or OBS_ADMIN_EMAIL." >&2
  exit 1
fi

if [[ -z "$PASSWORD" ]]; then
  echo "Set --password or OBS_ADMIN_PASSWORD." >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required." >&2
  exit 1
fi

while true; do
  clear

  token="$(curl -fsS -X POST "$BASE_URL/v1/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')"

  health="$(curl -fsS "$BASE_URL/health")"
  cycle_status="$(curl -fsS "$BASE_URL/v1/ingestion/cycle-status" -H "Authorization: Bearer $token")"
  summary="$(curl -fsS "$BASE_URL/v1/ingestion/summary" -H "Authorization: Bearer $token")"
  cycles="$(curl -fsS "$BASE_URL/v1/ingestion/cycles?limit=1" -H "Authorization: Bearer $token")"
  running_runs="$(curl -fsS "$BASE_URL/v1/ingestion/runs?status=running&limit=20" -H "Authorization: Bearer $token")"

  python3 - "$health" "$cycle_status" "$summary" "$cycles" "$running_runs" <<'PY'
import json
import sys
from datetime import datetime

health = json.loads(sys.argv[1])
cycle_status = json.loads(sys.argv[2])
summary = json.loads(sys.argv[3])
cycles = json.loads(sys.argv[4])
running_runs = json.loads(sys.argv[5])

def fmt(value):
    if not value:
        return "-"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S %z")
    except Exception:
        return value

def source(name):
    for item in summary:
        if item.get("source") == name:
            return item
    return {}

last_cycle = health.get("last_cycle") or {}
active_cycle = cycle_status.get("czds_cycle") or {}
latest_cycle = (cycles.get("items") or [{}])[0]
czds = source("czds")
openintel = source("openintel")
active_runs = [f"{item.get('source')}:{item.get('tld')}" for item in running_runs]
active_dbx = latest_cycle.get("active_databricks") or {}

total = active_cycle.get("total_tlds") or 0
done = (
    (active_cycle.get("completed_tlds") or 0)
    + (active_cycle.get("failed_tlds") or 0)
    + (active_cycle.get("skipped_tlds") or 0)
)
if total:
    progress = f"{done}/{total} ({(done / total) * 100:.2f}%)"
else:
    progress = "-"

print("Observador de Dominios - Ingestion Monitor")
print(f"Atualizado em: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}")
print()
print("Health")
print(f"  status:            {health.get('status')}")
print(f"  last_cycle_id:     {last_cycle.get('cycle_id')}")
print(f"  last_cycle_status: {last_cycle.get('status')}")
print(f"  started_at:        {fmt(last_cycle.get('started_at'))}")
print(f"  heartbeat_at:      {fmt(last_cycle.get('last_heartbeat_at'))}")
print()
print("Cycle Status")
print(f"  is_active:         {active_cycle.get('is_active')}")
print(f"  current_tld:       {active_cycle.get('current_tld') or '-'}")
print(f"  progress:          {progress}")
print(f"  avg_tld_seconds:   {active_cycle.get('avg_tld_duration_seconds') or '-'}")
print(f"  eta:               {fmt(active_cycle.get('estimated_completion_at'))}")
print()
print("Latest Cycle")
print(f"  cycle_id:          {latest_cycle.get('cycle_id')}")
print(f"  status:            {latest_cycle.get('status')}")
print(f"  triggered_by:      {latest_cycle.get('triggered_by')}")
print(f"  started_at:        {fmt(latest_cycle.get('started_at'))}")
print(f"  finished_at:       {fmt(latest_cycle.get('finished_at'))}")
if active_dbx:
    print(f"  dbx_source:        {active_dbx.get('source')}")
    print(f"  dbx_run_id:        {active_dbx.get('databricks_run_id')}")
    print(f"  dbx_state:         {active_dbx.get('databricks_result_state') or '-'}")
    print(f"  dbx_tld_count:     {active_dbx.get('tld_count') or 0}")
    preview = active_dbx.get('tlds_preview') or []
    print(f"  dbx_tlds_preview:  {', '.join(preview) if preview else '-'}")
    print(f"  dbx_url:           {active_dbx.get('databricks_run_url') or '-'}")
print()
print("Sources")
print(
    "  czds:              "
    f"running_now={czds.get('running_now')} "
    f"last_status={czds.get('last_status')} "
    f"last_run_at={fmt(czds.get('last_run_at'))}"
)
print(
    "  openintel:         "
    f"running_now={openintel.get('running_now')} "
    f"last_status={openintel.get('last_status')} "
    f"last_run_at={fmt(openintel.get('last_run_at'))}"
)
print(f"  running_runs:      {len(running_runs)}")
print(f"  active_runs:       {', '.join(active_runs) if active_runs else '-'}")
PY

  if [[ "$ONCE" == "1" ]]; then
    break
  fi

  sleep "$INTERVAL_SECONDS"
done
