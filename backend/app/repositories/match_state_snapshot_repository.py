# backend/app/repositories/match_state_snapshot_repository.py
"""Repository for match_state_snapshot — upsert and query derived match state."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.match_state_snapshot import MatchStateSnapshot


class MatchStateSnapshotRepository:
    """Upsert-only writes, rich reads for match state snapshots."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(
        self,
        *,
        match_id: UUID,
        brand_id: UUID,
        organization_id: UUID,
        derived_score: float,
        derived_bucket: str,
        derived_risk: str,
        active_signals: list[dict],
        signal_codes: list[str],
        state_fingerprint: str,
        last_derived_at: datetime,
        derived_disposition: str | None = None,
        llm_assessment: dict | None = None,
        llm_event_id: UUID | None = None,
        llm_source_fingerprint: str | None = None,
        events_hash: str | None = None,
    ) -> MatchStateSnapshot:
        """Upsert snapshot for a match. Caller must commit."""
        now = datetime.now(timezone.utc)
        values = dict(
            match_id=match_id,
            brand_id=brand_id,
            organization_id=organization_id,
            derived_score=derived_score,
            derived_bucket=derived_bucket,
            derived_risk=derived_risk,
            derived_disposition=derived_disposition,
            active_signals=active_signals,
            signal_codes=signal_codes,
            state_fingerprint=state_fingerprint,
            last_derived_at=last_derived_at,
            events_hash=events_hash,
            updated_at=now,
        )
        if llm_assessment is not None:
            values["llm_assessment"] = llm_assessment
        if llm_event_id is not None:
            values["llm_event_id"] = llm_event_id
        if llm_source_fingerprint is not None:
            values["llm_source_fingerprint"] = llm_source_fingerprint

        insert_values = {**values, "id": uuid.uuid4(), "created_at": now}
        update_values = {k: v for k, v in values.items()}

        stmt = insert(MatchStateSnapshot).values(
            **insert_values
        ).on_conflict_do_update(
            index_elements=["match_id"],
            set_=update_values,
        ).returning(MatchStateSnapshot)

        result = self.db.execute(stmt)
        self.db.flush()
        return result.scalar_one()

    def get_by_match(self, match_id: UUID) -> MatchStateSnapshot | None:
        return (
            self.db.query(MatchStateSnapshot)
            .filter(MatchStateSnapshot.match_id == match_id)
            .first()
        )

    def list_for_brand(
        self,
        brand_id: UUID,
        *,
        bucket: str | None = None,
        exclude_auto_dismissed: bool = True,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MatchStateSnapshot]:
        """List snapshots for a brand, optionally filtered by bucket."""
        from app.models.similarity_match import SimilarityMatch

        q = (
            self.db.query(MatchStateSnapshot)
            .filter(MatchStateSnapshot.brand_id == brand_id)
        )
        if bucket:
            q = q.filter(MatchStateSnapshot.derived_bucket == bucket)
        if exclude_auto_dismissed:
            q = q.join(SimilarityMatch, MatchStateSnapshot.match_id == SimilarityMatch.id).filter(
                SimilarityMatch.auto_disposition.is_(None)
            )
        return (
            q.order_by(MatchStateSnapshot.derived_score.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def count_by_bucket_active(self, brand_id: UUID) -> dict[str, int]:
        """Return counts per bucket, excluding auto-dismissed matches."""
        from sqlalchemy import func
        from app.models.similarity_match import SimilarityMatch
        rows = (
            self.db.query(
                MatchStateSnapshot.derived_bucket,
                func.count(MatchStateSnapshot.id),
            )
            .join(SimilarityMatch, MatchStateSnapshot.match_id == SimilarityMatch.id)
            .filter(
                MatchStateSnapshot.brand_id == brand_id,
                SimilarityMatch.auto_disposition.is_(None),
            )
            .group_by(MatchStateSnapshot.derived_bucket)
            .all()
        )
        return {bucket: count for bucket, count in rows}

    def list_global(
        self,
        *,
        bucket: str | None = None,
        brand_id: UUID | None = None,
        exclude_auto_dismissed: bool = True,
        verified_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MatchStateSnapshot]:
        """List snapshots across all brands, optionally filtered by bucket/brand.

        When ``verified_only`` is True, returns only snapshots for matches that
        have been confirmed as company-owned (auto_disposition == "self_owned").
        """
        from app.models.similarity_match import SimilarityMatch

        q = self.db.query(MatchStateSnapshot)
        if brand_id:
            q = q.filter(MatchStateSnapshot.brand_id == brand_id)
        if bucket:
            q = q.filter(MatchStateSnapshot.derived_bucket == bucket)
        if verified_only:
            q = q.join(SimilarityMatch, MatchStateSnapshot.match_id == SimilarityMatch.id).filter(
                SimilarityMatch.auto_disposition == "self_owned"
            )
        elif exclude_auto_dismissed:
            q = q.join(SimilarityMatch, MatchStateSnapshot.match_id == SimilarityMatch.id).filter(
                SimilarityMatch.auto_disposition.is_(None)
            )
        return (
            q.order_by(MatchStateSnapshot.derived_score.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def count_global(
        self,
        *,
        bucket: str | None = None,
        brand_id: UUID | None = None,
        exclude_auto_dismissed: bool = True,
        verified_only: bool = False,
    ) -> int:
        """Count snapshots across all brands."""
        from app.models.similarity_match import SimilarityMatch

        q = self.db.query(MatchStateSnapshot)
        if brand_id:
            q = q.filter(MatchStateSnapshot.brand_id == brand_id)
        if bucket:
            q = q.filter(MatchStateSnapshot.derived_bucket == bucket)
        if verified_only:
            q = q.join(SimilarityMatch, MatchStateSnapshot.match_id == SimilarityMatch.id).filter(
                SimilarityMatch.auto_disposition == "self_owned"
            )
        elif exclude_auto_dismissed:
            q = q.join(SimilarityMatch, MatchStateSnapshot.match_id == SimilarityMatch.id).filter(
                SimilarityMatch.auto_disposition.is_(None)
            )
        return q.count()

    def list_self_owned_for_brand(
        self,
        brand_id: UUID,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[MatchStateSnapshot]:
        """Return snapshots for matches detected as company-owned (self_owned)."""
        from app.models.similarity_match import SimilarityMatch

        return (
            self.db.query(MatchStateSnapshot)
            .join(SimilarityMatch, MatchStateSnapshot.match_id == SimilarityMatch.id)
            .filter(
                MatchStateSnapshot.brand_id == brand_id,
                SimilarityMatch.auto_disposition == "self_owned",
            )
            .order_by(MatchStateSnapshot.derived_score.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

    def count_self_owned_for_brand(self, brand_id: UUID) -> int:
        """Count matches detected as company-owned for a brand."""
        from app.models.similarity_match import SimilarityMatch

        return (
            self.db.query(MatchStateSnapshot)
            .join(SimilarityMatch, MatchStateSnapshot.match_id == SimilarityMatch.id)
            .filter(
                MatchStateSnapshot.brand_id == brand_id,
                SimilarityMatch.auto_disposition == "self_owned",
            )
            .count()
        )

    def needs_llm_assessment(
        self,
        *,
        brand_id: UUID | None = None,
        limit: int = 10,
    ) -> list[MatchStateSnapshot]:
        """
        Return snapshots that need LLM assessment:
        1. fingerprint changed since last LLM assessment, or no LLM yet
        2. last assessment older than 7 days (TTL expiry)
        Only for immediate_attention or defensive_gap buckets.
        """
        from datetime import timedelta
        from sqlalchemy import func, or_
        from app.models.similarity_match import SimilarityMatch
        LLM_TTL_DAYS = 7
        TTL_TRIGGER = or_(
            MatchStateSnapshot.llm_assessment.is_(None),
            MatchStateSnapshot.llm_source_fingerprint != MatchStateSnapshot.state_fingerprint,
            MatchStateSnapshot.last_derived_at < func.now() - timedelta(days=LLM_TTL_DAYS),
        )
        q = self.db.query(MatchStateSnapshot).join(
            SimilarityMatch, SimilarityMatch.id == MatchStateSnapshot.match_id
        ).filter(
            MatchStateSnapshot.derived_bucket.in_(["immediate_attention", "defensive_gap"]),
            TTL_TRIGGER,
            SimilarityMatch.auto_disposition.is_(None),
        )
        if brand_id:
            q = q.filter(MatchStateSnapshot.brand_id == brand_id)
        return q.order_by(MatchStateSnapshot.derived_score.desc()).limit(limit).all()
