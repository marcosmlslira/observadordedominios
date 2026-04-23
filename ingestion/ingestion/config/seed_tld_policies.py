"""Seed script — populate ingestion_tld_policy from CZDS API + OpenINTEL catalog.

Usage:
    python -m ingestion seed-policies            # seeds both sources
    python -m ingestion seed-policies --source czds
    python -m ingestion seed-policies --source openintel
    python -m ingestion seed-policies --dry-run  # print what would be inserted

Priority rules:
  - OpenINTEL: ccTLDs under 5M domains get priority 100–200; larger ones 300–400
  - CZDS: .com = priority 999 (always last); other large TLDs (net, org, etc.) = 800;
           small TLDs = priority 500 + alphabetical offset
  - Both: .com / .net / .org kept as-is across sources when applicable
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

from ingestion.config.settings import get_settings
from ingestion.sources.czds.client import CZDSClient

log = logging.getLogger(__name__)


# ── OpenINTEL known ccTLD catalog ────────────────────────────────────────────
# Source: https://openintel.nl/download/domain-lists/cctlds + zonefile S3 TLDs
# Separated into three tiers for priority assignment.
# Tier 1 (priority 100) — zonefile-based, < 5M domains, fast
_OPENINTEL_ZONEFILE_TLDS: list[str] = [
    "ch", "ee", "fed.us", "fr", "gov", "li", "nu", "root", "se", "sk",
]

# Tier 2 (priority 200) — cctld-web, medium size
_OPENINTEL_WEB_SMALL: list[str] = [
    "ac", "ae", "af", "ag", "ai", "al", "am", "an", "ao", "aq", "ar", "as",
    "at", "aw", "ax", "az", "ba", "bb", "bd", "be", "bf", "bg", "bh", "bi",
    "bj", "bl", "bm", "bn", "bo", "bq", "bs", "bt", "bv", "bw", "by", "bz",
    "ca", "cc", "cd", "cf", "cg", "ci", "ck", "cl", "cm", "cn", "co", "cr",
    "cu", "cv", "cw", "cx", "cy", "cz", "dj", "dk", "dm", "do", "dz", "ec",
    "eg", "eh", "er", "es", "et", "eu", "fi", "fj", "fk", "fm", "fo", "ga",
    "gb", "gd", "ge", "gf", "gg", "gh", "gi", "gl", "gm", "gn", "gp", "gq",
    "gr", "gs", "gt", "gu", "gw", "gy", "hk", "hm", "hn", "hr", "ht", "hu",
    "id", "ie", "il", "im", "in", "io", "iq", "ir", "is", "it", "je", "jm",
    "jo", "ke", "kg", "kh", "ki", "km", "kn", "kp", "kr", "kw", "ky", "kz",
    "la", "lb", "lc", "lk", "lr", "ls", "lt", "lu", "lv", "ly", "ma", "mc",
    "md", "me", "mf", "mg", "mh", "mk", "ml", "mm", "mn", "mo", "mp", "mq",
    "mr", "ms", "mt", "mu", "mv", "mw", "mx", "my", "mz", "na", "nc", "ne",
    "nf", "ng", "ni", "nl", "no", "np", "nr", "nz", "om", "pa", "pe", "pf",
    "pg", "ph", "pk", "pl", "pm", "pn", "pr", "ps", "pt", "pw", "py", "qa",
    "re", "ro", "rs", "ru", "rw", "sa", "sb", "sc", "sd", "sg", "sh", "si",
    "sj", "sl", "sm", "sn", "so", "sr", "ss", "st", "sv", "sx", "sy", "sz",
    "tc", "td", "tf", "tg", "th", "tj", "tk", "tl", "tm", "tn", "to", "tr",
    "tt", "tv", "tw", "tz", "ua", "ug", "uk", "um", "us", "uy", "uz", "va",
    "vc", "ve", "vg", "vi", "vn", "vu", "wf", "ws", "ye", "yt", "za", "zm",
    "zw",
]

# Tier 3 (priority 350) — large ccTLDs (> 5M domains each)
_OPENINTEL_WEB_LARGE: list[str] = [
    "br", "de",
]

# ── CZDS large TLDs (non-.com) that map to Databricks batch ──────────────────
_CZDS_DATABRICKS_TLDS: frozenset[str] = frozenset(["net", "org", "info", "biz", "mobi", "name"])


def _openintel_priority(tld: str) -> int:
    if tld in _OPENINTEL_ZONEFILE_TLDS:
        return 100
    if tld in _OPENINTEL_WEB_LARGE:
        return 350
    return 200


def _czds_priority(tld: str) -> int:
    if tld == "com":
        return 999
    if tld in _CZDS_DATABRICKS_TLDS:
        return 800
    return 500


def seed_openintel(conn: "psycopg2.connection", *, dry_run: bool = False) -> int:
    """Upsert all OpenINTEL TLDs into ingestion_tld_policy."""
    all_tlds = (
        [(t, _openintel_priority(t)) for t in _OPENINTEL_ZONEFILE_TLDS]
        + [(t, _openintel_priority(t)) for t in _OPENINTEL_WEB_SMALL]
        + [(t, _openintel_priority(t)) for t in _OPENINTEL_WEB_LARGE]
    )
    # Deduplicate (zonefile TLDs may overlap with web lists in practice)
    seen: set[str] = set()
    deduped = []
    for tld, priority in all_tlds:
        if tld not in seen:
            seen.add(tld)
            deduped.append((tld, priority))

    now = datetime.now(tz=timezone.utc)
    records = [
        ("openintel", tld, True, priority, now, now)
        for tld, priority in sorted(deduped, key=lambda x: x[1])
    ]

    log.info("openintel seed: %d TLDs to upsert", len(records))
    if dry_run:
        for r in records:
            print(f"  openintel/{r[1]} priority={r[3]}")
        return len(records)

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO ingestion_tld_policy (source, tld, is_enabled, priority, created_at, updated_at)
            VALUES %s
            ON CONFLICT (source, tld) DO UPDATE
              SET is_enabled = EXCLUDED.is_enabled,
                  priority   = EXCLUDED.priority,
                  updated_at = EXCLUDED.updated_at
            """,
            records,
            template="(%s, %s, %s, %s, %s, %s)",
        )
    conn.commit()
    log.info("openintel seed done: %d rows upserted", len(records))
    return len(records)


def seed_czds(conn: "psycopg2.connection", cfg, *, dry_run: bool = False) -> int:
    """Fetch CZDS TLD list from the API and upsert into ingestion_tld_policy.

    Falls back to empty list (no error) if credentials are missing.
    """
    if not cfg.czds_username or not cfg.czds_password:
        log.warning("CZDS_USERNAME/CZDS_PASSWORD not set — skipping CZDS seed")
        return 0

    client = CZDSClient(cfg)
    try:
        token = client.authenticate()
        authorized = client.authorized_tlds(token)
        log.info("czds seed: %d authorized TLDs from API", len(authorized))
    except Exception as exc:
        log.error("failed to fetch CZDS TLD list: %s", exc)
        return 0

    now = datetime.now(tz=timezone.utc)
    records = [
        ("czds", tld, True, _czds_priority(tld), now, now)
        for tld in sorted(authorized)
    ]

    if dry_run:
        log.info("czds dry-run: %d TLDs", len(records))
        for r in records:
            print(f"  czds/{r[1]} priority={r[3]}")
        return len(records)

    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO ingestion_tld_policy (source, tld, is_enabled, priority, created_at, updated_at)
            VALUES %s
            ON CONFLICT (source, tld) DO UPDATE
              SET is_enabled = EXCLUDED.is_enabled,
                  priority   = EXCLUDED.priority,
                  updated_at = EXCLUDED.updated_at
            """,
            records,
            template="(%s, %s, %s, %s, %s, %s)",
        )
    conn.commit()
    log.info("czds seed done: %d rows upserted", len(records))
    return len(records)


def run_seed(
    source: str | None = None,
    *,
    dry_run: bool = False,
    db_url: str | None = None,
) -> None:
    """Entry point for the seed command.

    Args:
        source: "czds", "openintel", or None (both).
        dry_run: If True, print what would be seeded without writing to DB.
        db_url: Override DATABASE_URL from environment.
    """
    import logging as _logging
    _logging.basicConfig(
        level=_logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    cfg = get_settings()
    effective_db_url = db_url or cfg.database_url

    if not effective_db_url and not dry_run:
        raise RuntimeError("DATABASE_URL is required for seed (or use --dry-run)")

    conn = None if dry_run else psycopg2.connect(effective_db_url)

    try:
        total = 0
        if source in (None, "openintel"):
            total += seed_openintel(conn, dry_run=dry_run)
        if source in (None, "czds"):
            total += seed_czds(conn, cfg, dry_run=dry_run)
        log.info("seed complete: %d total rows upserted", total)
    finally:
        if conn:
            conn.close()
