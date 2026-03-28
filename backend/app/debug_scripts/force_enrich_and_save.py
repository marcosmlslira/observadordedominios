"""Force-enrich a high-risk match and persist llm_assessment to the DB.

Usage:
    docker exec -it <similarity_worker> sh -c "cd /app && python app/debug_scripts/force_enrich_and_save.py"
"""
import sys
sys.path.insert(0, '/app')

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.models.similarity_match import SimilarityMatch
from app.models.monitored_brand import MonitoredBrand
from app.services.use_cases.enrich_similarity_match import enrich_similarity_match
from sqlalchemy import text
import json

db = SessionLocal()

# Find a high-risk match that hasn't been enriched yet
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
    print("No match found")
    sys.exit(1)

match = dict(row)
domain_full = f"{match['domain_name']}.{match['tld']}"
print(f"Enriching: {domain_full}")

brand = db.query(MonitoredBrand).filter(MonitoredBrand.id == row['brand_id']).first()
result = enrich_similarity_match(db, brand, match)

# Persist to DB
sm = db.query(SimilarityMatch).filter(SimilarityMatch.id == match['id']).first()
for key, value in result.items():
    if hasattr(sm, key):
        setattr(sm, key, value)

db.commit()
db.refresh(sm)

print(f"\n✅ Saved to DB")
print(f"  match_id:        {sm.id}")
print(f"  domain:          {sm.domain_name}.{sm.tld}")
print(f"  bucket:          {sm.attention_bucket}")
print(f"  enrichment:      {sm.enrichment_status}")
print(f"  llm_assessment:  {'PRESENT' if sm.llm_assessment else 'null'}")

if sm.llm_assessment:
    print(f"\n--- Parecer ---")
    print(f"  risco_score:      {sm.llm_assessment.get('risco_score')}")
    print(f"  categoria:        {sm.llm_assessment.get('categoria')}")
    print(f"  recomendacao:     {sm.llm_assessment.get('recomendacao_acao')}")
    print(f"  confianca:        {sm.llm_assessment.get('confianca')}%")
    print(f"  parecer_resumido: {sm.llm_assessment.get('parecer_resumido','')[:120]}...")

db.close()
