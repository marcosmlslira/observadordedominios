"""Bulk-load historical .br domains from crt.sh HTTP API.

Uses the public JSON API with prefix-based chunking for large sub-TLDs.

Strategy:
  - Small sub-TLDs: single query per sub-TLD (%.net.br)
  - Large sub-TLDs (com.br): split by first-letter prefix (a%.com.br, b%.com.br, ...)
  - Checkpoint progress to disk for resume on failure
  - Feeds batches through domain_normalizer → ingest_ct_batch
"""

from __future__ import annotations

import json
import logging
import string
import time
from pathlib import Path

import httpx

from app.infra.db.session import SessionLocal
from app.services.use_cases.ingest_ct_batch import ingest_ct_batch

logger = logging.getLogger(__name__)

CRTSH_URL = "https://crt.sh/"
HTTP_TIMEOUT = 300  # 5 min — large queries can be slow
MAX_RETRIES = 3
RETRY_BACKOFF = [60, 120, 300]
BATCH_UPSERT_SIZE = 10_000

# Sub-TLDs that need prefix splitting (too many certs for a single query)
LARGE_SUBTLDS = {"com.br"}

# Prefixes for splitting large sub-TLDs
PREFIXES = list(string.ascii_lowercase) + list(string.digits)

# All sub-TLDs to load
BR_SUBTLDS = [
    "com.br", "net.br", "org.br", "edu.br", "gov.br",
    "app.br", "dev.br", "log.br", "ong.br", "mil.br",
    "adv.br", "ind.br", "tec.br", "inf.br", "eng.br",
    "art.br", "eco.br", "med.br", "srv.br", "tur.br",
    "pro.br", "arq.br", "bet.br", "blog.br", "ia.br",
    "leg.br", "eti.br", "seg.br", "tv.br", "agr.br",
]

CHECKPOINT_FILE = Path("/tmp/crtsh_bulk_checkpoint.json")


def _load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_checkpoint(cp: dict) -> None:
    CHECKPOINT_FILE.write_text(json.dumps(cp, indent=2))


def _query_crtsh(query_pattern: str) -> list[str] | None:
    """Query crt.sh HTTP API and extract domain names from response.

    Returns list of raw domain names, or None on total failure.
    """
    params = {"q": query_pattern, "output": "json"}

    with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        for attempt in range(MAX_RETRIES):
            try:
                resp = client.get(CRTSH_URL, params=params)
                resp.raise_for_status()
                data = resp.json()

                domains = []
                for entry in data:
                    name_value = entry.get("name_value", "")
                    if name_value:
                        for name in name_value.split("\n"):
                            name = name.strip()
                            if name:
                                domains.append(name)

                logger.info(
                    "    crt.sh %s: %d entries → %d raw domains",
                    query_pattern, len(data), len(domains),
                )
                return domains

            except httpx.TimeoutException:
                logger.warning(
                    "    crt.sh timeout (attempt %d/%d): %s",
                    attempt + 1, MAX_RETRIES, query_pattern,
                )
            except httpx.HTTPStatusError as e:
                logger.warning(
                    "    crt.sh HTTP %d (attempt %d/%d): %s",
                    e.response.status_code, attempt + 1, MAX_RETRIES, query_pattern,
                )
            except Exception:
                logger.exception(
                    "    crt.sh error (attempt %d/%d): %s",
                    attempt + 1, MAX_RETRIES, query_pattern,
                )

            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BACKOFF[attempt]
                logger.info("    Retrying in %ds...", wait)
                time.sleep(wait)

    logger.error("    crt.sh query failed after retries: %s", query_pattern)
    return None


def _flush_domains(domains: list[str]) -> int:
    """Normalize and upsert a batch of raw domains."""
    db = SessionLocal()
    try:
        result = ingest_ct_batch(db, domains, source="crtsh-bulk", run_id=None)
        db.commit()
        return result.get("domains_inserted", 0)
    except Exception:
        logger.exception("    Upsert failed")
        db.rollback()
        return 0
    finally:
        db.close()


def _load_chunk(
    subtld: str,
    query_pattern: str,
    chunk_key: str,
    checkpoint: dict,
    *,
    dry_run: bool = False,
) -> dict:
    """Load a single chunk (one crt.sh query) and ingest results."""
    if checkpoint.get(chunk_key, {}).get("status") == "done":
        logger.info("    [SKIP] %s — already done", chunk_key)
        return {"raw_domains": 0, "domains_inserted": 0}

    raw_domains = _query_crtsh(query_pattern)
    if raw_domains is None:
        checkpoint[chunk_key] = {"status": "error"}
        _save_checkpoint(checkpoint)
        return {"raw_domains": 0, "domains_inserted": 0}

    metrics = {"raw_domains": len(raw_domains), "domains_inserted": 0}

    if dry_run:
        logger.info("    [DRY] %s: %d raw domains", chunk_key, len(raw_domains))
    elif raw_domains:
        # Ingest in sub-batches
        for i in range(0, len(raw_domains), BATCH_UPSERT_SIZE):
            batch = raw_domains[i:i + BATCH_UPSERT_SIZE]
            inserted = _flush_domains(batch)
            metrics["domains_inserted"] += inserted

        logger.info(
            "    %s: %d raw → %d inserted",
            chunk_key, len(raw_domains), metrics["domains_inserted"],
        )

    checkpoint[chunk_key] = {"status": "done", "raw": len(raw_domains), "inserted": metrics["domains_inserted"]}
    _save_checkpoint(checkpoint)
    return metrics


def run_bulk_load(
    *,
    subtlds: list[str] | None = None,
    years: list[int] | None = None,  # ignored for HTTP approach, kept for interface compat
    dry_run: bool = False,
) -> None:
    """Run full bulk load from crt.sh HTTP API."""
    target_subtlds = subtlds or BR_SUBTLDS
    checkpoint = _load_checkpoint()

    # Build list of chunks
    chunks: list[tuple[str, str, str]] = []  # (subtld, query_pattern, chunk_key)
    for subtld in target_subtlds:
        if subtld in LARGE_SUBTLDS:
            for prefix in PREFIXES:
                query = f"{prefix}%.{subtld}"
                key = f"{subtld}:prefix:{prefix}"
                chunks.append((subtld, query, key))
        else:
            query = f"%.{subtld}"
            key = f"{subtld}:all"
            chunks.append((subtld, query, key))

    done = sum(1 for _, _, k in chunks if checkpoint.get(k, {}).get("status") == "done")
    logger.info(
        "Bulk load: %d chunks total, %d already done, %d remaining (dry_run=%s)",
        len(chunks), done, len(chunks) - done, dry_run,
    )

    total = {"chunks": 0, "raw_domains": 0, "domains_inserted": 0}

    for subtld, query_pattern, chunk_key in chunks:
        logger.info("  Chunk: %s (%s)", chunk_key, query_pattern)
        m = _load_chunk(subtld, query_pattern, chunk_key, checkpoint, dry_run=dry_run)
        total["chunks"] += 1
        total["raw_domains"] += m["raw_domains"]
        total["domains_inserted"] += m["domains_inserted"]

        # Pause between queries to avoid overloading crt.sh
        if m["raw_domains"] > 0:
            time.sleep(15)

    logger.info(
        "Bulk load COMPLETE: chunks=%d raw=%d inserted=%d",
        total["chunks"], total["raw_domains"], total["domains_inserted"],
    )
