"""Test LLM assessment on an existing production match (any medium+ risk).

Usage (inside production container):
    python app/debug_scripts/test_llm_prod.py [match_id]

If no match_id is given, finds the first medium+ risk match in the DB.
"""
import sys
sys.path.insert(0, "/app")

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.services.use_cases.generate_llm_assessment import (
    build_domain_summary,
    generate_llm_assessment,
    should_generate_assessment,
)
from sqlalchemy import text

db = SessionLocal()

try:
    match_id = sys.argv[1] if len(sys.argv) > 1 else None

    if match_id:
        sql = text("SELECT * FROM similarity_match WHERE id = :id")
        row = db.execute(sql, {"id": match_id}).mappings().first()
    else:
        sql = text("""
            SELECT sm.*, mb.brand_name
            FROM similarity_match sm
            JOIN monitored_brand mb ON mb.id = sm.brand_id
            WHERE sm.risk_level IN ('medium','high','critical')
            ORDER BY sm.score_final DESC LIMIT 1
        """)
        row = db.execute(sql).mappings().first()

    if not row:
        print("[SKIP] No medium+ risk match found.")
        sys.exit(0)

    match = dict(row)
    brand_name = match.pop("brand_name", "Unknown Brand")
    domain = f"{match['domain_name']}.{match['tld']}"
    print(f"Testing LLM on: {domain}  (risk={match.get('risk_level')})")

    print("\n=== API Key check ===")
    key = settings.OPENROUTER_API_KEY
    print(f"OPENROUTER_API_KEY: {'SET (' + key[:12] + '...)' if key else 'NOT SET'}")

    print("\n=== Gate check ===")
    gate = should_generate_assessment(match, key)
    print(f"should_generate_assessment: {gate}")

    if not gate:
        print("[SKIP] Match does not meet gate criteria or API key missing.")
        sys.exit(0)

    print("\n=== Calling LLM (may take 10-25s) ===")
    result = generate_llm_assessment(
        match=match,
        brand_name=brand_name,
        tool_results={},  # No pre-enrichment data — LLM works with what it has
        signals=[],
    )

    if result is None:
        print("[FAIL] generate_llm_assessment returned None — check logs above.")
        sys.exit(1)

    import json
    print("\n=== LLM Assessment ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n[OK] LLM working in production for {domain}")

finally:
    db.close()
