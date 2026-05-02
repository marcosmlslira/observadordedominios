#!/usr/bin/env bash
# Detect repeated autovacuum failures on the same relation in the postgres
# container logs. Born out of the 01/05/2026 incident where a corruption in
# pg_catalog.pg_class went unnoticed for 5+ days because nothing was watching.
#
# Exit codes:
#   0 — below threshold (healthy)
#   2 — threshold exceeded (alert)
#   1 — could not run (container missing, no docker, etc.)
#
# Suggested cron line on the prod host (every 5 min):
#   */5 * * * * /opt/scripts/check_pg_autovacuum.sh observadordedominios_postgres 5 10 || \
#       curl -s -X POST "$ALERT_WEBHOOK_URL" -d '{"event":"pg_autovacuum_alert"}' >/dev/null
#
# Args:
#   $1 — container name or id (required)
#   $2 — error count threshold within the window (default 5)
#   $3 — window in minutes (default 10)

set -euo pipefail

container="${1:-}"
threshold="${2:-5}"
window_minutes="${3:-10}"

if [[ -z "$container" ]]; then
    echo "usage: $0 <container> [threshold] [window_minutes]" >&2
    exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
    echo "docker not available" >&2
    exit 1
fi

# Patterns that the 01/05 incident produced. Add more as new failure
# signatures appear in production.
readonly patterns='(found xmin .* from before relfrozenxid|automatic vacuum of table .* skip|could not access status of transaction|MultiXactId .* has not been created yet)'

since="${window_minutes}m"
count=$(docker logs --since "$since" "$container" 2>&1 | grep -E -c "$patterns" || true)

echo "pg_autovacuum_check container=$container window=${window_minutes}m matches=$count threshold=$threshold"

if (( count >= threshold )); then
    # Print the last 5 matching lines so the alert payload has context.
    echo "--- recent autovacuum errors ---"
    docker logs --since "$since" "$container" 2>&1 | grep -E "$patterns" | tail -5
    exit 2
fi
exit 0
