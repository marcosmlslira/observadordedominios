"""Domain Similarity Generator tool service."""

from __future__ import annotations

from sqlalchemy import text

from app.core.config import settings
from app.infra.db.session import SessionLocal
from app.infra.external.domain_similarity_generator import generate_variants
from app.services.use_cases.tools.base import BaseToolService


class DomainSimilarityService(BaseToolService):
    tool_type = "domain_similarity"
    cache_ttl_seconds = settings.TOOLS_CACHE_DOMAIN_SIMILARITY
    timeout_seconds = 60  # DNS check for many variants takes longer

    def _execute(self, target: str) -> dict:
        db = SessionLocal()
        try:
            rows = db.execute(text("SELECT tld FROM tld_domain_count_mv ORDER BY count DESC")).fetchall()
            corpus_tlds = [r[0] for r in rows]
        except Exception:
            corpus_tlds = []
        finally:
            db.close()
        return generate_variants(target, check_registration=True, extra_tlds=corpus_tlds)
