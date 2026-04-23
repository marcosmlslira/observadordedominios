"""Synchronous similarity search over the ingested domain corpus."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from statistics import fmean
from time import perf_counter
from uuid import uuid4

from sqlalchemy.orm import Session

from app.repositories.similarity_repository import SimilarityRepository
from app.schemas.similarity import (
    SimilarityHealthResponse,
    SimilaritySearchPaginationResponse,
    SimilaritySearchQueryResponse,
    SimilaritySearchRequest,
    SimilaritySearchResponse,
    SimilaritySearchResultResponse,
    SimilaritySearchScoreResponse,
    SimilaritySearchTelemetryResponse,
)
from app.services.registrable_domain import InvalidDomainError, parse_registrable_domain
from app.services.use_cases.compute_actionability import STRATEGIC_DEFENSIVE_TLDS
from app.services.use_cases.compute_similarity import (
    compute_scores,
    generate_typo_candidates,
)

_LATENCY_WINDOW_MS: deque[float] = deque(maxlen=50)
_PUNYCODE_WINDOW: deque[int] = deque(maxlen=50)
_PUNYCODE_SCAN_LIMIT = 600


def _added_day_to_datetime(added_day: int | None) -> datetime | None:
    """Convert YYYYMMDD integer to UTC datetime, returns None on invalid input."""
    if not added_day:
        return None
    try:
        y = added_day // 10000
        m = (added_day % 10000) // 100
        d = added_day % 100
        return datetime(y, m, d, tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


class InvalidSimilarityQuery(ValueError):
    """Raised when the query domain cannot be normalized safely."""


def search_similarity_domains(
    db: Session,
    payload: SimilaritySearchRequest,
) -> SimilaritySearchResponse:
    """Run a synchronous lexical similarity search."""
    started = perf_counter()
    parsed = _normalize_domain(payload.query_domain)
    normalized_domain = parsed.registrable_domain
    label = parsed.registrable_label

    if payload.algorithms == ["vector"]:
        raise InvalidSimilarityQuery(
            "algorithm 'vector' is not available in the current deployment",
        )

    if payload.sources and "czds" not in payload.sources:
        _record_latency_ms(started)
        return SimilaritySearchResponse(
            query=SimilaritySearchQueryResponse(
                domain=payload.query_domain,
                normalized=normalized_domain,
                algorithms=payload.algorithms,
                min_score=payload.min_score,
            ),
            pagination=SimilaritySearchPaginationResponse(
                offset=payload.offset,
                limit=payload.max_results,
                returned=0,
                has_more=False,
            ),
            results=[],
        )

    typo_candidates = list(generate_typo_candidates(label))
    repo = SimilarityRepository(db)
    lexical_candidates = repo.search_candidates(
        query_label=label,
        typo_candidates=typo_candidates,
        tld_allowlist=payload.tld_allowlist,
        include_subdomains=payload.include_subdomains,
        use_fuzzy=_should_use_fuzzy(payload.algorithms),
        use_typo=_should_use_typo(payload.algorithms),
        limit=max(payload.max_results + payload.offset + 1, _PUNYCODE_SCAN_LIMIT),
        offset=0,
    )
    punycode_candidates = repo.search_punycode_candidates(
        query_label=label,
        tld_allowlist=payload.tld_allowlist,
        include_subdomains=payload.include_subdomains,
        limit=max(payload.max_results + payload.offset + 1, _PUNYCODE_SCAN_LIMIT),
    )
    candidates = _merge_candidates(lexical_candidates, punycode_candidates)

    results: list[SimilaritySearchResultResponse] = []
    punycode_candidates_matched = 0
    for candidate in candidates:
        is_official = candidate["name"] == parsed.registrable_domain
        if payload.exclude_official_domains and is_official:
            continue

        scores = compute_scores(
            label=candidate["label"],
            brand_label=label,
            trigram_sim=candidate["sim_trigram"],
            brand_keywords=[],
        )

        fuzzy_score = max(scores["score_trigram"], scores["score_brand_hit"])
        typo_score = max(scores["score_levenshtein"], scores["score_homograph"])
        vector_score = 0.0
        final_score = _select_final_score(payload.algorithms, scores["score_final"], fuzzy_score, typo_score)

        if final_score < payload.min_score:
            continue

        if candidate["label"].startswith("xn--"):
            punycode_candidates_matched += 1

        observed_at = _added_day_to_datetime(candidate.get("added_day"))
        disposition = _default_disposition(
            candidate["tld"],
            scores["reasons"],
            final_score,
            is_official=is_official,
        )
        results.append(
            SimilaritySearchResultResponse(
                domain=candidate["name"],
                tld=candidate["tld"],
                source="czds",
                status="active",
                score=round(final_score, 4),
                scores=SimilaritySearchScoreResponse(
                    fuzzy=round(fuzzy_score, 4),
                    typo=round(typo_score, 4),
                    vector=vector_score,
                ),
                reasons=scores["reasons"],
                observed_at=observed_at,
                ownership_classification="official" if is_official else "third_party_unknown",
                self_owned=is_official,
                disposition=disposition,
                confidence=round(final_score, 4),
            ),
        )

    results.sort(
        key=lambda item: (
            item.score,
            item.observed_at,
            item.domain,
        ),
        reverse=True,
    )
    paged_results = results[payload.offset : payload.offset + payload.max_results]
    has_more = len(results) > payload.offset + payload.max_results
    _record_latency_ms(
        started,
        punycode_candidates_evaluated=len(punycode_candidates),
    )

    return SimilaritySearchResponse(
        query=SimilaritySearchQueryResponse(
            domain=payload.query_domain,
            normalized=normalized_domain,
            algorithms=payload.algorithms,
            min_score=payload.min_score,
        ),
        pagination=SimilaritySearchPaginationResponse(
            offset=payload.offset,
            limit=payload.max_results,
            returned=len(paged_results),
            has_more=has_more,
        ),
        results=paged_results,
        telemetry=SimilaritySearchTelemetryResponse(
            punycode_candidates_evaluated=len(punycode_candidates),
            punycode_candidates_matched=punycode_candidates_matched,
            punycode_scan_enabled=True,
        ),
    )


def get_similarity_search_health() -> SimilarityHealthResponse:
    """Lightweight health view for the synchronous search endpoint."""
    samples = len(_LATENCY_WINDOW_MS)
    average_latency_ms = round(fmean(_LATENCY_WINDOW_MS), 2) if samples else 0.0
    punycode_samples = len(_PUNYCODE_WINDOW)
    average_punycode_candidates = round(fmean(_PUNYCODE_WINDOW), 2) if punycode_samples else 0.0
    return SimilarityHealthResponse(
        status="ok",
        version="v1",
        average_search_latency_ms=average_latency_ms,
        samples=samples,
        vector_enabled=False,
        average_punycode_candidates_evaluated=average_punycode_candidates,
        punycode_search_samples=punycode_samples,
    )


def _normalize_domain(raw_value: str):
    try:
        return parse_registrable_domain(raw_value)
    except InvalidDomainError as exc:
        raise InvalidSimilarityQuery(str(exc)) from exc


def _should_use_fuzzy(algorithms: list[str]) -> bool:
    return any(algorithm in {"fuzzy", "hybrid"} for algorithm in algorithms)


def _should_use_typo(algorithms: list[str]) -> bool:
    return any(algorithm in {"typo", "hybrid"} for algorithm in algorithms)


def _select_final_score(
    algorithms: list[str],
    hybrid_score: float,
    fuzzy_score: float,
    typo_score: float,
) -> float:
    if "hybrid" in algorithms:
        return hybrid_score
    if "fuzzy" in algorithms and "typo" in algorithms:
        return max(fuzzy_score, typo_score)
    if "fuzzy" in algorithms:
        return fuzzy_score
    if "typo" in algorithms:
        return typo_score
    return hybrid_score


def _record_latency_ms(started_at: float, *, punycode_candidates_evaluated: int = 0) -> None:
    _LATENCY_WINDOW_MS.append((perf_counter() - started_at) * 1000)
    _PUNYCODE_WINDOW.append(punycode_candidates_evaluated)


def build_similarity_error_detail(message: str) -> dict[str, str]:
    return {"message": message, "trace_id": str(uuid4())}


def _default_disposition(
    tld: str,
    reasons: list[str],
    final_score: float,
    *,
    is_official: bool,
) -> str:
    if is_official:
        return "official"
    if "exact_label_match" in reasons and tld in STRATEGIC_DEFENSIVE_TLDS:
        return "defensive_gap"
    if final_score >= 0.72:
        return "live_but_unknown"
    return "watchlist"


def _merge_candidates(lexical_candidates: list[dict], punycode_candidates: list[dict]) -> list[dict]:
    """Merge sync lexical search with Ring C punycode candidates."""
    best_by_name: dict[str, dict] = {}
    for candidate in [*lexical_candidates, *punycode_candidates]:
        existing = best_by_name.get(candidate["name"])
        if existing is None or (
            float(candidate["sim_trigram"]),
            candidate.get("added_day") or 0,
        ) > (
            float(existing["sim_trigram"]),
            existing.get("added_day") or 0,
        ):
            best_by_name[candidate["name"]] = candidate
    return list(best_by_name.values())
