"""Test quick analysis endpoint via internal call."""
import sys
import time
import uuid

sys.path.insert(0, "/app")

from app.api.v1.routers.tools import _tool_services, PLACEHOLDER_ORG_ID
from app.infra.db.session import SessionLocal
from app.schemas.tools import QuickAnalysisToolResult

tools_to_test = ["dns_lookup", "whois", "ssl_check", "http_headers"]
target = "example.com"

db = SessionLocal()
quick_id = uuid.uuid4()
results = {}
start = time.monotonic()

for tool_type in tools_to_test:
    service = _tool_services.get(tool_type)
    if not service:
        print(f"  {tool_type}: NOT REGISTERED")
        continue

    t0 = time.monotonic()
    try:
        resp = service.run(db, PLACEHOLDER_ORG_ID, target, triggered_by="test", quick_analysis_id=quick_id)
        elapsed = int((time.monotonic() - t0) * 1000)
        print(f"  {tool_type}: {resp.status} ({elapsed}ms) cached={resp.cached}")
        results[tool_type] = resp.status
    except Exception as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        print(f"  {tool_type}: ERROR ({elapsed}ms) {e}")

db.commit()
db.close()
total = int((time.monotonic() - start) * 1000)
print(f"\nTotal: {total}ms | {sum(1 for s in results.values() if s=='completed')}/{len(tools_to_test)} completed")
