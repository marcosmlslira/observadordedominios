"""Domain similarity / typosquatting variant generator.

Generates registration-plausible variations of a domain name using:
  - Character omission
  - Character duplication
  - Adjacent key transpositions (QWERTY)
  - Character insertion (adjacent keys)
  - Homoglyph substitutions
  - Common prefix/suffix additions
  - TLD variations
  - Hyphen insertion/removal
  - Vowel swap
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

import dns.resolver

logger = logging.getLogger(__name__)

# QWERTY adjacent key map
QWERTY: dict[str, str] = {
    "a": "sqwz", "b": "vghn", "c": "xdfv", "d": "sfcxer",
    "e": "wrsdf", "f": "dgcvrt", "g": "fhbvty", "h": "gjbnyu",
    "i": "ujklo", "j": "hknimu", "k": "jlmiop", "l": "kop",
    "m": "njk", "n": "bhjm", "o": "iklp", "p": "ol",
    "q": "wa", "r": "edft", "s": "awdxze", "t": "ryfg",
    "u": "yhji", "v": "cfgb", "w": "qase", "x": "zsdc",
    "y": "tghu", "z": "asx",
}

# Homoglyph map (character → visually-similar alternatives)
HOMOGLYPHS: dict[str, list[str]] = {
    "a": ["à", "á", "â", "ä", "å", "ą", "4", "@"],
    "e": ["è", "é", "ê", "ë", "3"],
    "i": ["í", "ì", "î", "ï", "1", "l", "!"],
    "o": ["ò", "ó", "ô", "ö", "0"],
    "u": ["ù", "ú", "û", "ü"],
    "c": ["ç"],
    "n": ["ñ"],
    "l": ["1", "i"],
    "0": ["o"],
    "1": ["l", "i"],
}

# Popular TLDs for variation generation
POPULAR_TLDS = [
    "com", "net", "org", "io", "co", "app", "dev", "info",
    "biz", "shop", "store", "online", "site", "tech", "us",
]

# Common phishing prefixes/suffixes
COMMON_AFFIXES = [
    "secure", "login", "my", "official", "support", "help",
    "service", "account", "verify", "confirm", "update",
    "get", "go", "app", "web",
]


def _split_domain(domain: str) -> tuple[str, str]:
    """Split 'example.com' into ('example', 'com')."""
    parts = domain.rsplit(".", 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return domain, ""


def _omission(name: str) -> set[str]:
    """Remove one character at a time."""
    return {name[:i] + name[i + 1:] for i in range(len(name)) if len(name) > 2}


def _duplication(name: str) -> set[str]:
    """Duplicate one character."""
    return {name[:i] + name[i] + name[i:] for i in range(len(name))}


def _transposition(name: str) -> set[str]:
    """Swap adjacent characters."""
    result = set()
    for i in range(len(name) - 1):
        swapped = list(name)
        swapped[i], swapped[i + 1] = swapped[i + 1], swapped[i]
        result.add("".join(swapped))
    return result


def _adjacent_key_substitution(name: str) -> set[str]:
    """Substitute characters with adjacent keyboard keys."""
    result = set()
    for i, ch in enumerate(name):
        for replacement in QWERTY.get(ch, ""):
            result.add(name[:i] + replacement + name[i + 1:])
    return result


def _adjacent_key_insertion(name: str) -> set[str]:
    """Insert an adjacent key character at each position."""
    result = set()
    for i, ch in enumerate(name):
        for replacement in QWERTY.get(ch, ""):
            result.add(name[:i] + replacement + name[i:])
            result.add(name[:i + 1] + replacement + name[i + 1:])
    return result


def _homoglyph_substitution(name: str) -> set[str]:
    """Replace characters with common homoglyphs."""
    result = set()
    for i, ch in enumerate(name):
        for glyph in HOMOGLYPHS.get(ch.lower(), []):
            result.add(name[:i] + glyph + name[i + 1:])
    return result


def _vowel_swap(name: str) -> set[str]:
    """Swap each vowel with other vowels."""
    vowels = "aeiou"
    result = set()
    for i, ch in enumerate(name):
        if ch in vowels:
            for v in vowels:
                if v != ch:
                    result.add(name[:i] + v + name[i + 1:])
    return result


def _hyphen_variants(name: str) -> set[str]:
    """Add/remove hyphens."""
    result = set()
    # Insert hyphen at each position
    for i in range(1, len(name)):
        if name[i - 1] != "-" and name[i] != "-":
            result.add(name[:i] + "-" + name[i:])
    # Remove hyphens
    if "-" in name:
        result.add(name.replace("-", ""))
    return result


def _tld_variations(name: str, original_tld: str) -> list[dict]:
    """Generate same name with different TLDs."""
    result = []
    for tld in POPULAR_TLDS:
        if tld != original_tld:
            result.append({"domain": f"{name}.{tld}", "type": "tld_variation"})
    return result


def _affix_variants(name: str, tld: str) -> list[dict]:
    """Add common prefixes/suffixes to the domain name."""
    result = []
    for affix in COMMON_AFFIXES:
        result.append({"domain": f"{affix}{name}.{tld}", "type": "prefix"})
        result.append({"domain": f"{name}{affix}.{tld}", "type": "suffix"})
        result.append({"domain": f"{affix}-{name}.{tld}", "type": "prefix_hyphen"})
        result.append({"domain": f"{name}-{affix}.{tld}", "type": "suffix_hyphen"})
    return result


def _check_registered(domain: str) -> bool:
    """Check if a domain has DNS A/NS records (i.e., is registered/active)."""
    for rtype in ("A", "NS"):
        try:
            dns.resolver.resolve(domain, rtype, lifetime=3)
            return True
        except dns.resolver.NXDOMAIN:
            return False
        except Exception:
            continue
    return False


def generate_variants(domain: str, check_registration: bool = True) -> dict:
    """Generate typosquatting variants and optionally check registration."""
    name, tld = _split_domain(domain)
    if not name:
        return {"domain": domain, "variants": [], "registered": [], "total_generated": 0}

    # Collect all name-level variants
    name_variants: set[str] = set()
    name_variants |= _omission(name)
    name_variants |= _duplication(name)
    name_variants |= _transposition(name)
    name_variants |= _adjacent_key_substitution(name)
    name_variants |= _adjacent_key_insertion(name)
    name_variants |= _homoglyph_substitution(name)
    name_variants |= _vowel_swap(name)
    name_variants |= _hyphen_variants(name)

    # Remove the original and empty strings
    name_variants.discard(name)
    name_variants.discard("")
    name_variants = {v for v in name_variants if 2 <= len(v) <= 63}

    # Build full domain variants with original TLD
    typed_variants: list[dict] = []
    for v in name_variants:
        vtype = "unknown"
        if len(v) == len(name) - 1:
            vtype = "omission"
        elif len(v) == len(name) + 1 and v.count("-") > name.count("-"):
            vtype = "hyphen"
        elif len(v) == len(name) + 1:
            vtype = "duplication_or_insertion"
        elif len(v) == len(name):
            vtype = "substitution"
        typed_variants.append({"domain": f"{v}.{tld}", "type": vtype})

    # Add TLD variations (original name, different TLD)
    typed_variants.extend(_tld_variations(name, tld))

    # Add affix variants (limit to avoid explosion)
    typed_variants.extend(_affix_variants(name, tld)[:40])

    # Deduplicate and remove the original
    seen: set[str] = {domain}
    unique_variants: list[dict] = []
    for v in typed_variants:
        d = v["domain"]
        if d not in seen and d:
            seen.add(d)
            unique_variants.append(v)

    total_generated = len(unique_variants)

    registered: list[dict] = []
    if check_registration and unique_variants:
        # Check in parallel (limit concurrency to avoid DNS flooding)
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = {
                executor.submit(_check_registered, v["domain"]): v
                for v in unique_variants
            }
            for future in as_completed(futures):
                variant = futures[future]
                try:
                    if future.result():
                        registered.append(variant)
                except Exception:
                    pass

    # Sort variants alphabetically for consistent output
    unique_variants.sort(key=lambda x: x["domain"])
    registered.sort(key=lambda x: x["domain"])

    return {
        "domain": domain,
        "variants": unique_variants,
        "registered": registered,
        "registered_count": len(registered),
        "total_generated": total_generated,
    }
