"""Scoring engine for domain similarity analysis.

Computes a composite score from multiple signals: trigram, Levenshtein,
brand containment, keyword risk, and homograph detection.
"""

from __future__ import annotations

import re
import unicodedata

# ── Homograph / Confusable Maps ────────────────────────────────

# Characters commonly used in homograph attacks (leet speak + unicode confusables)
HOMOGRAPH_MAP: dict[str, str] = {
    # Leet speak
    "0": "o", "1": "l", "3": "e", "4": "a", "5": "s",
    "7": "t", "8": "b", "@": "a", "$": "s",
    # Cyrillic confusables
    "\u0430": "a",  # а
    "\u0435": "e",  # е
    "\u043e": "o",  # о
    "\u0440": "p",  # р
    "\u0441": "c",  # с
    "\u0443": "y",  # у
    "\u0445": "x",  # х
    "\u0456": "i",  # і
    # Greek confusables
    "\u03bf": "o",  # ο (omicron)
    "\u03b1": "a",  # α
    "\u03b5": "e",  # ε
    "\u03b9": "i",  # ι
    # Common visual confusables
    "\u0131": "i",  # ı (dotless i)
    "\u0142": "l",  # ł
}

# Reverse map: ascii char → list of confusable variants
HOMOGRAPH_REVERSE: dict[str, list[str]] = {}
for _variant, _ascii in HOMOGRAPH_MAP.items():
    HOMOGRAPH_REVERSE.setdefault(_ascii, []).append(_variant)


# ── Risk Keywords ──────────────────────────────────────────────

RISK_KEYWORDS = frozenset({
    "login", "secure", "verify", "update", "account",
    "bank", "password", "confirm", "auth", "signin",
    "support", "help", "official", "alert", "recover",
    "payment", "billing", "wallet", "transfer", "reset",
})


# ── QWERTY Adjacent Keys ──────────────────────────────────────

QWERTY_ADJACENT: dict[str, str] = {
    "a": "sqwz", "b": "vghn", "c": "xdfv", "d": "sfcxer",
    "e": "wrsdf", "f": "dgcvrt", "g": "fhbvty", "h": "gjbnyu",
    "i": "ujko", "j": "hknuim", "k": "jlmio", "l": "kop",
    "m": "njk", "n": "bhjm", "o": "iklp", "p": "ol",
    "q": "wa", "r": "edft", "s": "awedxz", "t": "rfgy",
    "u": "yhji", "v": "cfgb", "w": "qase", "x": "zsdc",
    "y": "tghu", "z": "asx",
}


# ── Normalization ──────────────────────────────────────────────

def normalize_homograph(label: str) -> str:
    """Normalize a domain label by replacing confusable characters."""
    # First: NFKD unicode normalization (handles ligatures, accents)
    normalized = unicodedata.normalize("NFKD", label)
    # Strip combining marks (accents)
    normalized = "".join(
        c for c in normalized if not unicodedata.combining(c)
    )
    # Apply homograph substitutions
    return "".join(HOMOGRAPH_MAP.get(c, c) for c in normalized.lower())


# ── Typosquatting Candidate Generation ─────────────────────────

def generate_typo_candidates(brand_label: str) -> set[str]:
    """Generate plausible typosquatting variants of a brand label."""
    candidates: set[str] = set()
    n = len(brand_label)

    # 1. Character omission
    for i in range(n):
        candidates.add(brand_label[:i] + brand_label[i + 1:])

    # 2. Character duplication
    for i in range(n):
        candidates.add(brand_label[:i] + brand_label[i] + brand_label[i:])

    # 3. Adjacent character swap
    for i in range(n - 1):
        candidates.add(
            brand_label[:i] + brand_label[i + 1] + brand_label[i] + brand_label[i + 2:]
        )

    # 4. QWERTY adjacent key substitution
    for i, c in enumerate(brand_label):
        for adj in QWERTY_ADJACENT.get(c, ""):
            candidates.add(brand_label[:i] + adj + brand_label[i + 1:])

    # 5. Homograph substitutions
    for i, c in enumerate(brand_label):
        for variant in HOMOGRAPH_REVERSE.get(c, []):
            candidates.add(brand_label[:i] + variant + brand_label[i + 1:])

    # Remove the original brand itself
    candidates.discard(brand_label)

    return candidates


# ── Scoring ────────────────────────────────────────────────────

# Default weights (configurable in future versions)
W_TRIGRAM = 0.30
W_LEVENSHTEIN = 0.25
W_BRAND_HIT = 0.20
W_KEYWORD = 0.15
W_HOMOGRAPH = 0.10

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def compute_scores(
    label: str,
    brand_label: str,
    brand_keywords: list[str],
    *,
    trigram_sim: float,
) -> dict:
    """Compute all similarity scores for a candidate domain label.

    Args:
        label: The candidate domain label (e.g. "g00gle-login").
        brand_label: The normalized brand label (e.g. "google").
        brand_keywords: Extra brand-specific keywords (e.g. ["search", "ads"]).
        trigram_sim: Pre-computed pg_trgm similarity (from SQL query).

    Returns:
        Dict with score_final, individual scores, risk_level, and reasons.
    """
    # 1. Trigram (already computed in SQL)
    score_trigram = trigram_sim

    # 2. Levenshtein normalized (0-1, higher = more similar)
    max_len = max(len(label), len(brand_label))
    if max_len == 0:
        score_levenshtein = 0.0
    else:
        edit_dist = _levenshtein(label, brand_label)
        score_levenshtein = 1.0 - (edit_dist / max_len)

    exact_match = label == brand_label

    # 3. Brand containment (boundary-aware to avoid cases like "authority" -> "itau")
    score_brand_hit = 1.0 if _has_brand_boundary_match(label, brand_label) else 0.0

    # 4. Keyword risk scoring
    label_lower = label.lower()
    residual_text = label_lower.replace(brand_label.lower(), " ")
    residual_tokens = _extract_tokens(residual_text)
    risk_hits = sum(
        1 for kw in RISK_KEYWORDS
        if _has_keyword_hit(residual_text, residual_tokens, kw)
    )
    brand_kw_hits = sum(
        1 for kw in brand_keywords
        if _has_keyword_hit(residual_text, residual_tokens, kw)
    )
    score_keyword = min(1.0, risk_hits * 0.3 + brand_kw_hits * 0.2)

    # 5. Homograph similarity
    norm_label = normalize_homograph(label)
    norm_brand = normalize_homograph(brand_label)
    if norm_label == norm_brand:
        score_homograph = 1.0
    else:
        # Use trigram as proxy for normalized similarity
        # (actual pg_trgm would need a DB call; approximate here)
        max_len_h = max(len(norm_label), len(norm_brand))
        if max_len_h == 0:
            score_homograph = 0.0
        else:
            dist_h = _levenshtein(norm_label, norm_brand)
            score_homograph = 1.0 - (dist_h / max_len_h)

    # Composite score
    score_final = (
        W_TRIGRAM * score_trigram
        + W_LEVENSHTEIN * score_levenshtein
        + W_BRAND_HIT * score_brand_hit
        + W_KEYWORD * score_keyword
        + W_HOMOGRAPH * score_homograph
    )

    # Risk level
    if exact_match and score_keyword == 0:
        risk_level = "high"
    elif (
        not exact_match
        and score_brand_hit == 1.0
        and score_keyword >= 0.3
        and score_final >= 0.55
    ) or score_final >= 0.9:
        risk_level = "critical"
    elif score_final >= 0.72:
        risk_level = "high"
    elif score_final >= 0.50:
        risk_level = "medium"
    else:
        risk_level = "low"

    # Reasons
    reasons = _detect_reasons(
        score_trigram, score_levenshtein, score_brand_hit,
        score_keyword, score_homograph, exact_match=exact_match,
    )

    return {
        "score_final": round(score_final, 4),
        "score_trigram": round(score_trigram, 4),
        "score_levenshtein": round(score_levenshtein, 4),
        "score_brand_hit": round(score_brand_hit, 4),
        "score_keyword": round(score_keyword, 4),
        "score_homograph": round(score_homograph, 4),
        "risk_level": risk_level,
        "reasons": reasons,
    }


def _detect_reasons(
    trigram: float,
    lev: float,
    brand: float,
    keyword: float,
    homograph: float,
    *,
    exact_match: bool,
) -> list[str]:
    reasons: list[str] = []
    if exact_match:
        reasons.append("exact_label_match")
    elif lev >= 0.75 and trigram >= 0.45:
        reasons.append("typosquatting")
    if brand >= 1.0 and not exact_match:
        reasons.append("brand_containment")
    if keyword > 0:
        reasons.append("risky_keywords")
    if not exact_match and homograph >= 0.95 and homograph > trigram:
        reasons.append("homograph_attack")
    if not reasons:
        reasons.append("lexical_similarity")
    return reasons


def _extract_tokens(text: str) -> set[str]:
    return {token for token in _TOKEN_RE.findall(text.lower()) if token}


def _has_keyword_hit(residual_text: str, residual_tokens: set[str], keyword: str) -> bool:
    normalized = keyword.lower().strip()
    if not normalized:
        return False

    if normalized in residual_tokens:
        return True

    # Short tokens create a lot of noise via substring matching ("auth" in "authority").
    if len(normalized) <= 4:
        return False

    return normalized in residual_text


def _has_brand_boundary_match(label: str, brand_label: str) -> bool:
    if not brand_label:
        return False

    if label == brand_label:
        return True

    start = 0
    while True:
        idx = label.find(brand_label, start)
        if idx == -1:
            return False

        end = idx + len(brand_label)
        prev_char = label[idx - 1] if idx > 0 else ""
        next_char = label[end] if end < len(label) else ""
        prev_is_letter = prev_char.isalpha()
        next_is_letter = next_char.isalpha()

        if not prev_is_letter or not next_is_letter:
            return True

        start = idx + 1


def _levenshtein(s1: str, s2: str) -> int:
    """Pure-Python Levenshtein distance (for scoring; DB uses fuzzystrmatch)."""
    if len(s1) < len(s2):
        return _levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            cost = 0 if c1 == c2 else 1
            curr_row.append(min(
                curr_row[j] + 1,
                prev_row[j + 1] + 1,
                prev_row[j] + cost,
            ))
        prev_row = curr_row
    return prev_row[-1]
