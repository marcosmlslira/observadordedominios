"""Repository for similarity scan operations — candidate queries and match persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.similarity_match import SimilarityMatch
from app.models.similarity_scan_cursor import SimilarityScanCursor


class SimilarityRepository:
    """Handles candidate fetching from domain table and match CRUD."""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Candidate Queries ──────────────────────────────────────

    def fetch_candidates(
        self,
        brand_label: str,
        tld: str,
        typo_candidates: list[str],
        *,
        watermark_at: datetime | None = None,
        limit: int = 5000,
    ) -> list[dict]:
        """Unified candidate query: trigram + substring + typo exact match.

        Returns dicts with: name, tld, label, first_seen_at, sim_trigram, edit_dist.
        """
        brand_like = f"%{brand_label}%"

        # Build watermark filter
        wm_filter = ""
        params: dict = {
            "brand_label": brand_label,
            "brand_like": brand_like,
            "tld": tld,
            "limit": limit,
        }

        if watermark_at:
            wm_filter = "AND first_seen_at > :watermark_at"
            params["watermark_at"] = watermark_at

        # Typo candidates sub-query (only if we have candidates)
        typo_union = ""
        if typo_candidates:
            params["typo_candidates"] = typo_candidates
            typo_union = f"""
                UNION

                SELECT DISTINCT name, tld, label, first_seen_at,
                       similarity(label, :brand_label) AS sim_trigram,
                       levenshtein(label, :brand_label) AS edit_dist
                FROM domain
                WHERE tld = :tld
                  AND label = ANY(:typo_candidates)
                  {wm_filter}
            """

        # Dynamic threshold: short brands (<=5 chars) need higher similarity
        # to avoid excessive false positives from trigram matching
        sim_threshold = 0.5 if len(brand_label) <= 5 else 0.3
        self.db.execute(
            text("SET pg_trgm.similarity_threshold = :t"),
            {"t": sim_threshold},
        )

        sql = f"""
            WITH candidates AS (
                -- Trigram similarity (GIN index scan via % operator)
                SELECT DISTINCT name, tld, label, first_seen_at,
                       similarity(label, :brand_label) AS sim_trigram,
                       levenshtein(label, :brand_label) AS edit_dist
                FROM domain
                WHERE tld = :tld
                  AND label % :brand_label
                  {wm_filter}

                UNION

                -- Substring / brand containment
                SELECT DISTINCT name, tld, label, first_seen_at,
                       similarity(label, :brand_label) AS sim_trigram,
                       levenshtein(label, :brand_label) AS edit_dist
                FROM domain
                WHERE tld = :tld
                  AND label LIKE :brand_like
                  {wm_filter}

                {typo_union}
            )
            SELECT * FROM candidates
            ORDER BY sim_trigram DESC
            LIMIT :limit
        """

        rows = self.db.execute(text(sql), params).fetchall()
        return [
            {
                "name": r.name,
                "tld": r.tld,
                "label": r.label,
                "first_seen_at": r.first_seen_at,
                "sim_trigram": float(r.sim_trigram),
                "edit_dist": int(r.edit_dist),
            }
            for r in rows
        ]

    # ── Cursor Operations ──────────────────────────────────────

    def get_or_create_cursor(
        self, brand_id: uuid.UUID, tld: str,
    ) -> SimilarityScanCursor:
        cursor = self.db.get(SimilarityScanCursor, (brand_id, tld))
        if cursor:
            return cursor

        cursor = SimilarityScanCursor(
            brand_id=brand_id,
            tld=tld,
            scan_phase="initial",
            status="pending",
            domains_scanned=0,
            domains_matched=0,
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(cursor)
        self.db.flush()
        return cursor

    def start_scan(self, cursor: SimilarityScanCursor) -> None:
        now = datetime.now(timezone.utc)
        cursor.status = "running"
        cursor.started_at = now
        cursor.error_message = None
        cursor.updated_at = now
        self.db.flush()

    def finish_scan(
        self,
        cursor: SimilarityScanCursor,
        *,
        status: str,
        watermark_at: datetime | None = None,
        domains_scanned: int = 0,
        domains_matched: int = 0,
        error_message: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        cursor.status = status
        cursor.finished_at = now
        cursor.updated_at = now
        cursor.error_message = error_message

        if status == "complete":
            cursor.domains_scanned += domains_scanned
            cursor.domains_matched += domains_matched
            if watermark_at:
                cursor.watermark_at = watermark_at
            # After initial scan completes, switch to delta mode
            if cursor.scan_phase == "initial":
                cursor.scan_phase = "delta"
        self.db.flush()

    # ── Match Operations ───────────────────────────────────────

    def upsert_matches(self, matches: list[dict]) -> int:
        """Bulk upsert similarity matches. Returns count upserted."""
        if not matches:
            return 0

        for m in matches:
            self.db.execute(text("""
                INSERT INTO similarity_match (
                    id, brand_id, domain_name, tld, label,
                    score_final, score_trigram, score_levenshtein,
                    score_brand_hit, score_keyword, score_homograph,
                    reasons, risk_level, first_detected_at, domain_first_seen,
                    status
                ) VALUES (
                    gen_random_uuid(), :brand_id, :domain_name, :tld, :label,
                    :score_final, :score_trigram, :score_levenshtein,
                    :score_brand_hit, :score_keyword, :score_homograph,
                    :reasons, :risk_level, :first_detected_at, :domain_first_seen,
                    'new'
                )
                ON CONFLICT (brand_id, domain_name) DO UPDATE SET
                    score_final = EXCLUDED.score_final,
                    score_trigram = EXCLUDED.score_trigram,
                    score_levenshtein = EXCLUDED.score_levenshtein,
                    score_brand_hit = EXCLUDED.score_brand_hit,
                    score_keyword = EXCLUDED.score_keyword,
                    score_homograph = EXCLUDED.score_homograph,
                    reasons = EXCLUDED.reasons,
                    risk_level = EXCLUDED.risk_level
            """), m)

        return len(matches)

    def list_matches(
        self,
        brand_id: uuid.UUID,
        *,
        status: str | None = None,
        risk_level: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SimilarityMatch]:
        q = self.db.query(SimilarityMatch).filter(
            SimilarityMatch.brand_id == brand_id,
        )
        if status:
            q = q.filter(SimilarityMatch.status == status)
        if risk_level:
            q = q.filter(SimilarityMatch.risk_level == risk_level)
        return (
            q.order_by(SimilarityMatch.score_final.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    def get_match(self, match_id: uuid.UUID) -> SimilarityMatch | None:
        return self.db.get(SimilarityMatch, match_id)

    def update_match_status(
        self,
        match: SimilarityMatch,
        *,
        status: str,
        reviewed_by: uuid.UUID | None = None,
        notes: str | None = None,
    ) -> SimilarityMatch:
        match.status = status
        if reviewed_by:
            match.reviewed_by = reviewed_by
            match.reviewed_at = datetime.now(timezone.utc)
        if notes is not None:
            match.notes = notes
        self.db.flush()
        return match

    def count_matches(
        self,
        brand_id: uuid.UUID,
        status: str | None = None,
        risk_level: str | None = None,
    ) -> int:
        q = self.db.query(SimilarityMatch).filter(
            SimilarityMatch.brand_id == brand_id,
        )
        if status:
            q = q.filter(SimilarityMatch.status == status)
        if risk_level:
            q = q.filter(SimilarityMatch.risk_level == risk_level)
        return q.count()
