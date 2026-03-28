"""Test enrichment pipeline including llm_assessment hook.

Usage:
    docker exec -it <similarity_worker> python app/debug_scripts/test_enrich_pipeline.py
"""
import sys
sys.path.insert(0, '/app')

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.models.similarity_match import SimilarityMatch
from app.models.monitored_brand import MonitoredBrand
from app.services.use_cases.enrich_similarity_match import enrich_similarity_match
from sqlalchemy import text

db = SessionLocal()

# Find a high-risk match to enrich
row = db.execute(text("""
    SELECT sm.*
    FROM similarity_match sm
    JOIN monitored_brand mb ON mb.id = sm.brand_id
    WHERE mb.brand_name = 'Bradesco'
      AND sm.risk_level IN ('high','critical')
      AND sm.score_final >= 0.7
    ORDER BY sm.score_final DESC LIMIT 1
""")).mappings().first()

if not row:
    print("No high-risk Bradesco match found")
    sys.exit(1)

brand = db.query(MonitoredBrand).filter(MonitoredBrand.id == row['brand_id']).first()
match = dict(row)
domain_full = f"{match['domain_name']}.{match['tld']}"
print(f"Enriching: {domain_full} (risk={match['risk_level']} score={match['score_final']:.3f})")
print(f"OPENROUTER_API_KEY set: {bool(settings.OPENROUTER_API_KEY)}")

result = enrich_similarity_match(db, brand, match)

print(f"\n--- Enrichment Result ---")
print(f"attention_bucket:   {result.get('attention_bucket')}")
print(f"actionability_score:{result.get('actionability_score')}")
print(f"disposition:        {result.get('disposition')}")
print(f"llm_assessment:     {result.get('llm_assessment')}")
print(f"\nAll keys returned: {sorted(result.keys())}")

if result.get('llm_assessment'):
    import json
    print(f"\n--- LLM Assessment ---")
    print(json.dumps(result['llm_assessment'], ensure_ascii=False, indent=2))
else:
    if not settings.OPENROUTER_API_KEY:
        print("\n[INFO] llm_assessment=null expected: OPENROUTER_API_KEY not configured")
    else:
        print("\n[WARN] llm_assessment=null but API key IS set — check logs")

db.close()
print("\n[OK] Pipeline test complete")
