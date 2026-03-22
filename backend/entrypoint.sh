#!/bin/bash
set -e

# Wait for postgres to be ready
echo "Waiting for postgres..."
while ! python -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(3)
try:
    s.connect(('postgres', 5432))
    s.close()
except Exception:
    raise SystemExit(1)
" 2>/dev/null; do
  sleep 2
done
echo "Postgres is ready."

echo "Running database migrations..."
alembic upgrade head

echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
