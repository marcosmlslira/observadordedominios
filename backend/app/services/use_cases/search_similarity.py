"""Synchronous similarity search over the ingested domain corpus."""

from __future__ import annotations

from collections import deque
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
)
from app.services.registrable_domain import InvalidDomainError, parse_registrable_domain
from app.services.use_cases.compute_actionability import STRATEGIC_DEFENSIVE_TLDS
from app.services.use_cases.compute_similarity import (
    compute_scores,
    generate_typo_candidates,
)

_LATENCY_WINDOW_MS: deque[float] = deque(maxlen=50)


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
    candidates = repo.search_candidates(
        query_label=label,
        typo_candidates=typo_candidates,
        tld_allowlist=payload.tld_allowlist,
        include_subdomains=payload.include_subdomains,
        use_fuzzy=_should_use_fuzzy(payload.algorithms),
        use_typo=_should_use_typo(payload.algorithms),
        limit=payload.max_results + 1,
        offset=payload.offset,
    )

    results: list[SimilaritySearchResultResponse] = []
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

        observed_at = candidate["last_seen_at"] or candidate["first_seen_at"]
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

    has_more = len(results) > payload.max_results
    trimmed_results = results[:payload.max_results]
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
            returned=len(trimmed_results),
            has_more=has_more,
        ),
        results=trimmed_results,
    )


def get_similarity_search_health() -> SimilarityHealthResponse:
    """Lightweight health view for the synchronous search endpoint."""
    samples = len(_LATENCY_WINDOW_MS)
    average_latency_ms = round(fmean(_LATENCY_WINDOW_MS), 2) if samples else 0.0
    return SimilarityHealthResponse(
        status="ok",
        version="v1",
        average_search_latency_ms=average_latency_ms,
        samples=samples,
        vector_enabled=False,
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


def _record_latency_ms(started_at: float) -> None:
    _LATENCY_WINDOW_MS.append((perf_counter() - started_at) * 1000)


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
