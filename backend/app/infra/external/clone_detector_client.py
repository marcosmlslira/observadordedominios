"""Website clone detection: visual, textual, and structural comparison.

Compares a target site against a reference site using:
  - Visual similarity: perceptual hash (pHash) of screenshots
  - Textual similarity: cosine similarity of visible text content
  - Structural similarity: DOM tag frequency fingerprint
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Score weights
VISUAL_WEIGHT = 0.40
TEXT_WEIGHT = 0.35
STRUCTURAL_WEIGHT = 0.25


def _fetch_page(url: str) -> tuple[str, bytes]:
    """Fetch a page and return (html_text, raw_bytes)."""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (compatible; ObsBot/1.0)"})
        r.raise_for_status()
        return r.text, r.content
    except Exception:
        # Fallback to HTTP
        url_http = url.replace("https://", "http://", 1)
        r = httpx.get(url_http, timeout=15, follow_redirects=True,
                      headers={"User-Agent": "Mozilla/5.0 (compatible; ObsBot/1.0)"})
        r.raise_for_status()
        return r.text, r.content


def _extract_text(html: str) -> str:
    """Extract visible text from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove script and style elements
    for tag in soup(["script", "style", "meta", "link", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    # Normalize whitespace
    return re.sub(r"\s+", " ", text).lower()


def _dom_fingerprint(html: str) -> dict[str, int]:
    """Create a DOM structure fingerprint: tag → count."""
    soup = BeautifulSoup(html, "html.parser")
    tags = [tag.name for tag in soup.find_all() if tag.name]
    return dict(Counter(tags))


def _text_similarity(text1: str, text2: str) -> float:
    """Compute cosine similarity between two text strings using word n-grams."""
    if not text1 or not text2:
        return 0.0

    def to_ngrams(text: str, n: int = 2) -> Counter:
        words = text.split()
        return Counter(zip(*[words[i:] for i in range(n)])) if len(words) >= n else Counter(words)

    vec1 = to_ngrams(text1)
    vec2 = to_ngrams(text2)

    intersection = set(vec1.keys()) & set(vec2.keys())
    if not intersection:
        return 0.0

    dot = sum(vec1[k] * vec2[k] for k in intersection)
    mag1 = sum(v ** 2 for v in vec1.values()) ** 0.5
    mag2 = sum(v ** 2 for v in vec2.values()) ** 0.5

    if mag1 == 0 or mag2 == 0:
        return 0.0
    return round(dot / (mag1 * mag2), 4)


def _structural_similarity(fp1: dict[str, int], fp2: dict[str, int]) -> float:
    """Cosine similarity between two DOM fingerprints."""
    all_tags = set(fp1.keys()) | set(fp2.keys())
    if not all_tags:
        return 0.0

    dot = sum(fp1.get(t, 0) * fp2.get(t, 0) for t in all_tags)
    mag1 = sum(v ** 2 for v in fp1.values()) ** 0.5
    mag2 = sum(v ** 2 for v in fp2.values()) ** 0.5

    if mag1 == 0 or mag2 == 0:
        return 0.0
    return round(dot / (mag1 * mag2), 4)


def _phash_similarity(img_bytes1: bytes, img_bytes2: bytes) -> float:
    """Compute perceptual hash similarity between two images.

    Falls back to a simple byte-hash comparison if imagehash/Pillow not available.
    """
    try:
        import io
        import imagehash
        from PIL import Image

        img1 = Image.open(io.BytesIO(img_bytes1))
        img2 = Image.open(io.BytesIO(img_bytes2))

        hash1 = imagehash.phash(img1)
        hash2 = imagehash.phash(img2)
        # Hamming distance: 0 = identical, 64 = completely different
        distance = hash1 - hash2
        similarity = round(1.0 - (distance / 64.0), 4)
        return max(0.0, similarity)

    except ImportError:
        # Fallback: compare MD5 hashes (exact match only)
        h1 = hashlib.md5(img_bytes1).hexdigest()
        h2 = hashlib.md5(img_bytes2).hexdigest()
        return 1.0 if h1 == h2 else 0.0
    except Exception as exc:
        logger.debug("pHash comparison failed: %s", exc)
        return 0.0


def _take_screenshot_bytes(domain: str) -> bytes | None:
    """Take a screenshot using playwright and return raw PNG bytes."""
    try:
        from playwright.sync_api import sync_playwright

        url = f"https://{domain}" if not domain.startswith("http") else domain
        with sync_playwright() as p:
            browser = p.chromium.launch(
                args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
                headless=True,
            )
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto(url, wait_until="networkidle", timeout=20000)
            png_bytes = page.screenshot(full_page=False)
            browser.close()
            return png_bytes
    except Exception as exc:
        logger.warning("Screenshot failed for %s: %s", domain, exc)
        return None


def compare_websites(target: str, reference: str) -> dict:
    """Compare target website against a reference website.

    Returns similarity scores for visual, textual, and structural dimensions,
    plus a weighted overall score.
    """
    errors: list[str] = []

    # Fetch both pages
    target_html, target_bytes = None, None
    reference_html, reference_bytes = None, None

    try:
        target_html, target_bytes = _fetch_page(target)
    except Exception as exc:
        errors.append(f"Failed to fetch target: {exc}")

    try:
        reference_html, reference_bytes = _fetch_page(reference)
    except Exception as exc:
        errors.append(f"Failed to fetch reference: {exc}")

    if not target_html or not reference_html:
        return {
            "target": target,
            "reference": reference,
            "overall_score": 0.0,
            "visual_score": None,
            "text_score": None,
            "structural_score": None,
            "verdict": "error",
            "errors": errors,
        }

    # Text similarity
    target_text = _extract_text(target_html)
    reference_text = _extract_text(reference_html)
    text_score = _text_similarity(target_text, reference_text)

    # Structural similarity
    target_fp = _dom_fingerprint(target_html)
    reference_fp = _dom_fingerprint(reference_html)
    structural_score = _structural_similarity(target_fp, reference_fp)

    # Visual similarity (screenshots)
    visual_score: float | None = None
    target_screenshot = _take_screenshot_bytes(target)
    reference_screenshot = _take_screenshot_bytes(reference)

    if target_screenshot and reference_screenshot:
        visual_score = _phash_similarity(target_screenshot, reference_screenshot)

    # Weighted overall score
    if visual_score is not None:
        overall = (
            visual_score * VISUAL_WEIGHT
            + text_score * TEXT_WEIGHT
            + structural_score * STRUCTURAL_WEIGHT
        )
    else:
        # Without visual, rebalance: text 60%, structural 40%
        overall = text_score * 0.60 + structural_score * 0.40
        errors.append("Visual comparison unavailable (screenshot failed)")

    overall = round(overall, 4)

    # Verdict
    if overall >= 0.75:
        verdict = "likely_clone"
    elif overall >= 0.50:
        verdict = "suspicious"
    elif overall >= 0.25:
        verdict = "low_similarity"
    else:
        verdict = "not_similar"

    return {
        "target": target,
        "reference": reference,
        "overall_score": overall,
        "visual_score": visual_score,
        "text_score": text_score,
        "structural_score": structural_score,
        "verdict": verdict,
        "errors": errors if errors else None,
    }
