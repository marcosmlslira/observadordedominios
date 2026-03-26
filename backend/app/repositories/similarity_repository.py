"""Repository for similarity scan operations — candidate queries and match persistence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import case, text
from sqlalchemy.orm import Session

from app.models.similarity_match import SimilarityMatch
from app.models.similarity_scan_cursor import SimilarityScanCursor
from app.models.similarity_scan_job import SimilarityScanJob


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
        include_subdomains: bool = False,
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

        subdomain_filter = "" if include_subdomains else "AND label NOT LIKE '%.%'"

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
                  {subdomain_filter}
                  {wm_filter}
            """

        # Dynamic threshold: short brands (<=5 chars) need higher similarity
        # to avoid excessive false positives from trigram matching
        sim_threshold = 0.5 if len(brand_label) <= 5 else 0.3
        self.db.execute(
            text("SET LOCAL pg_trgm.similarity_threshold = :t"),
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
                  {subdomain_filter}
                  {wm_filter}

                UNION

                -- Substring / brand containment
                SELECT DISTINCT name, tld, label, first_seen_at,
                       similarity(label, :brand_label) AS sim_trigram,
                       levenshtein(label, :brand_label) AS edit_dist
                FROM domain
                WHERE tld = :tld
                  AND label LIKE :brand_like
                  {subdomain_filter}
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
                "last_seen_at": getattr(r, "last_seen_at", None),
                "sim_trigram": float(r.sim_trigram),
                "edit_dist": int(r.edit_dist),
            }
            for r in rows
        ]

    def search_candidates(
        self,
        query_label: str,
        typo_candidates: list[str],
        *,
        tld_allowlist: list[str] | None = None,
        include_subdomains: bool = False,
        use_fuzzy: bool = True,
        use_typo: bool = True,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        """Search candidates across TLDs for the synchronous similarity API."""
        params: dict = {
            "brand_label": query_label,
            "brand_like": f"%{query_label}%",
            "limit": limit,
            "offset": offset,
        }

        base_filters: list[str] = []
        if tld_allowlist:
            params["tld_allowlist"] = tld_allowlist
            base_filters.append("tld = ANY(:tld_allowlist)")
        if not include_subdomains:
            base_filters.append("label NOT LIKE '%.%'")
        base_where = " AND ".join(base_filters) if base_filters else "TRUE"

        sim_threshold = 0.5 if len(query_label) <= 5 else 0.3
        self.db.execute(
            text("SET LOCAL pg_trgm.similarity_threshold = :t"),
            {"t": sim_threshold},
        )

        candidate_queries: list[str] = []
        if use_fuzzy:
            candidate_queries.extend(
                [
                    f"""
                    SELECT DISTINCT name, tld, label, first_seen_at, last_seen_at,
                           similarity(label, :brand_label) AS sim_trigram,
                           levenshtein(label, :brand_label) AS edit_dist
                    FROM domain
                    WHERE {base_where}
                      AND label % :brand_label
                    """,
                    f"""
                    SELECT DISTINCT name, tld, label, first_seen_at, last_seen_at,
                           similarity(label, :brand_label) AS sim_trigram,
                           levenshtein(label, :brand_label) AS edit_dist
                    FROM domain
                    WHERE {base_where}
                      AND label LIKE :brand_like
                    """,
                ]
            )

        if use_typo and typo_candidates:
            params["typo_candidates"] = typo_candidates
            candidate_queries.append(
                f"""
                SELECT DISTINCT name, tld, label, first_seen_at, last_seen_at,
                       similarity(label, :brand_label) AS sim_trigram,
                       levenshtein(label, :brand_label) AS edit_dist
                FROM domain
                WHERE {base_where}
                  AND label = ANY(:typo_candidates)
                """
            )

        if not candidate_queries:
            return []

        sql = f"""
            WITH candidates AS (
                {" UNION ".join(candidate_queries)}
            )
            SELECT * FROM candidates
            ORDER BY sim_trigram DESC, last_seen_at DESC, name ASC
            OFFSET :offset
            LIMIT :limit
        """

        rows = self.db.execute(text(sql), params).fetchall()
        return [
            {
                "name": r.name,
                "tld": r.tld,
                "label": r.label,
                "first_seen_at": r.first_seen_at,
                "last_seen_at": r.last_seen_at,
                "sim_trigram": float(r.sim_trigram),
                "edit_dist": int(r.edit_dist),
            }
            for r in rows
        ]

    def delete_matches_for_brand_tld(
        self,
        brand_id: uuid.UUID,
        tld: str,
        domain_names: list[str],
    ) -> int:
        """Delete persisted matches for a brand/TLD and a known set of domains."""
        if not domain_names:
            return 0

        result = self.db.execute(
            text("""
                DELETE FROM similarity_match
                WHERE brand_id = :brand_id
                  AND tld = :tld
                  AND domain_name = ANY(:domain_names)
            """),
            {
                "brand_id": brand_id,
                "tld": tld,
                "domain_names": domain_names,
            },
        )
        return result.rowcount or 0

    def reconcile_matches_for_brand_tld(
        self,
        brand_id: uuid.UUID,
        tld: str,
        keep_domain_names: list[str],
    ) -> int:
        """Replace the persisted set for a brand/TLD with the provided domains."""
        if keep_domain_names:
            result = self.db.execute(
                text("""
                    DELETE FROM similarity_match
                    WHERE brand_id = :brand_id
                      AND tld = :tld
                      AND NOT (domain_name = ANY(:keep_domain_names))
                """),
                {
                    "brand_id": brand_id,
                    "tld": tld,
                    "keep_domain_names": keep_domain_names,
                },
            )
        else:
            result = self.db.execute(
                text("""
                    DELETE FROM similarity_match
                    WHERE brand_id = :brand_id
                      AND tld = :tld
                """),
                {
                    "brand_id": brand_id,
                    "tld": tld,
                },
            )
        return result.rowcount or 0

    def delete_subdomain_matches(
        self,
        brand_id: uuid.UUID,
        tld: str,
    ) -> int:
        """Drop stored subdomain/hostname matches from the alert stream."""
        result = self.db.execute(
            text("""
                DELETE FROM similarity_match
                WHERE brand_id = :brand_id
                  AND tld = :tld
                  AND label LIKE '%.%'
            """),
            {
                "brand_id": brand_id,
                "tld": tld,
            },
        )
        return result.rowcount or 0

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

    # ── Manual Scan Job Queue ─────────────────────────────────

    def create_scan_job(
        self,
        *,
        brand_id: uuid.UUID,
        requested_tld: str | None,
        effective_tlds: list[str],
        force_full: bool,
        initiated_by: str | None,
    ) -> SimilarityScanJob:
        now = datetime.now(timezone.utc)
        job = SimilarityScanJob(
            id=uuid.uuid4(),
            brand_id=brand_id,
            requested_tld=requested_tld,
            effective_tlds=effective_tlds,
            tld_results={
                tld: {
                    "status": "queued",
                    "candidates": 0,
                    "matched": 0,
                    "removed": 0,
                    "error_message": None,
                    "started_at": None,
                    "finished_at": None,
                }
                for tld in effective_tlds
            },
            force_full=force_full,
            status="queued",
            initiated_by=initiated_by,
            queued_at=now,
            created_at=now,
            updated_at=now,
        )
        self.db.add(job)
        self.db.flush()
        return job

    def get_scan_job(self, job_id: uuid.UUID) -> SimilarityScanJob | None:
        return self.db.get(SimilarityScanJob, job_id)

    def get_active_scan_job_for_brand(self, brand_id: uuid.UUID) -> SimilarityScanJob | None:
        return (
            self.db.query(SimilarityScanJob)
            .filter(
                SimilarityScanJob.brand_id == brand_id,
                SimilarityScanJob.status.in_(("queued", "running")),
            )
            .order_by(SimilarityScanJob.queued_at.asc())
            .first()
        )

    def get_latest_scan_job_for_brand(self, brand_id: uuid.UUID) -> SimilarityScanJob | None:
        return (
            self.db.query(SimilarityScanJob)
            .filter(SimilarityScanJob.brand_id == brand_id)
            .order_by(SimilarityScanJob.created_at.desc())
            .first()
        )

    def claim_next_queued_scan_job(self) -> SimilarityScanJob | None:
        row = self.db.execute(
            text(
                """
                SELECT id
                FROM similarity_scan_job
                WHERE status = 'queued'
                ORDER BY queued_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
                """
            )
        ).first()
        if not row:
            return None
        job = self.db.get(SimilarityScanJob, row.id)
        if not job:
            return None
        self.start_scan_job(job)
        return job

    def start_scan_job(self, job: SimilarityScanJob) -> None:
        now = datetime.now(timezone.utc)
        job.status = "running"
        job.started_at = now
        job.last_heartbeat_at = now
        job.last_error = None
        job.updated_at = now
        self.db.flush()

    def heartbeat_scan_job(self, job: SimilarityScanJob) -> None:
        now = datetime.now(timezone.utc)
        job.last_heartbeat_at = now
        job.updated_at = now
        self.db.flush()

    def update_scan_job_tld(
        self,
        job: SimilarityScanJob,
        *,
        tld: str,
        status: str,
        candidates: int = 0,
        matched: int = 0,
        removed: int = 0,
        error_message: str | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        results = dict(job.tld_results or {})
        current = dict(results.get(tld) or {})
        current.update(
            {
                "status": status,
                "candidates": candidates,
                "matched": matched,
                "removed": removed,
                "error_message": error_message,
                "started_at": started_at.isoformat() if started_at else current.get("started_at"),
                "finished_at": finished_at.isoformat() if finished_at else current.get("finished_at"),
            }
        )
        results[tld] = current
        job.tld_results = results
        job.status = self._derive_scan_job_status(results)
        job.last_error = error_message if status == "failed" else job.last_error
        job.updated_at = datetime.now(timezone.utc)
        if job.status in {"completed", "partial", "failed"}:
            job.finished_at = datetime.now(timezone.utc)
        self.db.flush()

    def finalize_scan_job(self, job: SimilarityScanJob) -> None:
        job.status = self._derive_scan_job_status(job.tld_results or {})
        job.finished_at = datetime.now(timezone.utc)
        job.updated_at = datetime.now(timezone.utc)
        self.db.flush()

    @staticmethod
    def _derive_scan_job_status(results: dict) -> str:
        states = {str((payload or {}).get("status") or "queued") for payload in results.values()}
        if not states:
            return "failed"
        if states <= {"completed"}:
            return "completed"
        if states <= {"failed"}:
            return "failed"
        if "running" in states:
            return "running"
        if "queued" in states and states == {"queued"}:
            return "queued"
        if "failed" in states and "completed" in states:
            return "partial"
        if "failed" in states and "queued" in states:
            return "running"
        if "completed" in states and "queued" in states:
            return "running"
        return "partial"

    # ── Match Operations ───────────────────────────────────────

    def upsert_matches(self, matches: list[dict]) -> int:
        """Bulk upsert similarity matches. Returns count upserted."""
        if not matches:
            return 0

        BATCH_SIZE = 500
        insert_fields = [
            "brand_id",
            "domain_name",
            "tld",
            "label",
            "score_final",
            "score_trigram",
            "score_levenshtein",
            "score_brand_hit",
            "score_keyword",
            "score_homograph",
            "reasons",
            "risk_level",
            "actionability_score",
            "attention_bucket",
            "attention_reasons",
            "recommended_action",
            "enrichment_status",
            "enrichment_summary",
            "last_enriched_at",
            "ownership_classification",
            "self_owned",
            "disposition",
            "confidence",
            "delivery_risk",
            "first_detected_at",
            "domain_first_seen",
            "matched_channel",
            "matched_seed_id",
            "matched_seed_value",
            "matched_seed_type",
            "matched_rule",
            "source_stream",
        ]
        for i in range(0, len(matches), BATCH_SIZE):
            batch = matches[i : i + BATCH_SIZE]

            # Build VALUES placeholders with numbered suffixes
            values_clauses = []
            params: dict = {}
            for idx, m in enumerate(batch):
                suffix = f"_{idx}"
                values_clauses.append(
                    f"(gen_random_uuid(), :brand_id{suffix}, :domain_name{suffix}, "
                    f":tld{suffix}, :label{suffix}, :score_final{suffix}, "
                    f":score_trigram{suffix}, :score_levenshtein{suffix}, "
                    f":score_brand_hit{suffix}, :score_keyword{suffix}, "
                    f":score_homograph{suffix}, :reasons{suffix}, "
                    f":risk_level{suffix}, :actionability_score{suffix}, "
                    f":attention_bucket{suffix}, :attention_reasons{suffix}, "
                    f":recommended_action{suffix}, :enrichment_status{suffix}, "
                    f":enrichment_summary{suffix}, :last_enriched_at{suffix}, "
                    f":ownership_classification{suffix}, :self_owned{suffix}, "
                    f":disposition{suffix}, :confidence{suffix}, :delivery_risk{suffix}, "
                    f":first_detected_at{suffix}, :domain_first_seen{suffix}, "
                    f"'new', :matched_channel{suffix}, "
                    f":matched_seed_id{suffix}, :matched_seed_value{suffix}, "
                    f":matched_seed_type{suffix}, :matched_rule{suffix}, "
                    f":source_stream{suffix})"
                )
                for key in insert_fields:
                    params[f"{key}{suffix}"] = m.get(key)

            sql = f"""
                INSERT INTO similarity_match (
                    id, brand_id, domain_name, tld, label,
                    score_final, score_trigram, score_levenshtein,
                    score_brand_hit, score_keyword, score_homograph,
                    reasons, risk_level, actionability_score, attention_bucket,
                    attention_reasons, recommended_action, enrichment_status,
                    enrichment_summary, last_enriched_at, ownership_classification,
                    self_owned, disposition, confidence, delivery_risk, first_detected_at,
                    domain_first_seen, status, matched_channel, matched_seed_id,
                    matched_seed_value, matched_seed_type, matched_rule, source_stream
                ) VALUES {", ".join(values_clauses)}
                ON CONFLICT (brand_id, domain_name) DO UPDATE SET
                    score_final = EXCLUDED.score_final,
                    score_trigram = EXCLUDED.score_trigram,
                    score_levenshtein = EXCLUDED.score_levenshtein,
                    score_brand_hit = EXCLUDED.score_brand_hit,
                    score_keyword = EXCLUDED.score_keyword,
                    score_homograph = EXCLUDED.score_homograph,
                    reasons = EXCLUDED.reasons,
                    risk_level = EXCLUDED.risk_level,
                    actionability_score = EXCLUDED.actionability_score,
                    attention_bucket = EXCLUDED.attention_bucket,
                    attention_reasons = EXCLUDED.attention_reasons,
                    recommended_action = EXCLUDED.recommended_action,
                    enrichment_status = EXCLUDED.enrichment_status,
                    enrichment_summary = EXCLUDED.enrichment_summary,
                    last_enriched_at = EXCLUDED.last_enriched_at,
                    ownership_classification = EXCLUDED.ownership_classification,
                    self_owned = EXCLUDED.self_owned,
                    disposition = EXCLUDED.disposition,
                    confidence = EXCLUDED.confidence,
                    delivery_risk = EXCLUDED.delivery_risk,
                    matched_channel = EXCLUDED.matched_channel,
                    matched_seed_id = EXCLUDED.matched_seed_id,
                    matched_seed_value = EXCLUDED.matched_seed_value,
                    matched_seed_type = EXCLUDED.matched_seed_type,
                    matched_rule = EXCLUDED.matched_rule,
                    source_stream = EXCLUDED.source_stream
            """
            self.db.execute(text(sql), params)

        return len(matches)

    def list_matches(
        self,
        brand_id: uuid.UUID,
        *,
        status: str | None = None,
        risk_level: str | None = None,
        attention_bucket: str | None = None,
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
        if attention_bucket:
            q = q.filter(SimilarityMatch.attention_bucket == attention_bucket)
        bucket_priority = case(
            (SimilarityMatch.attention_bucket == "immediate_attention", 0),
            (SimilarityMatch.attention_bucket == "defensive_gap", 1),
            else_=2,
        )
        return (
            q.order_by(
                bucket_priority.asc(),
                SimilarityMatch.actionability_score.desc(),
                SimilarityMatch.score_final.desc(),
            )
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
        attention_bucket: str | None = None,
    ) -> int:
        q = self.db.query(SimilarityMatch).filter(
            SimilarityMatch.brand_id == brand_id,
        )
        if status:
            q = q.filter(SimilarityMatch.status == status)
        if risk_level:
            q = q.filter(SimilarityMatch.risk_level == risk_level)
        if attention_bucket:
            q = q.filter(SimilarityMatch.attention_bucket == attention_bucket)
        return q.count()
