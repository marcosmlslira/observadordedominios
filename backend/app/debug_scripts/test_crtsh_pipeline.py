"""Test crt.sh pipeline end-to-end: query, normalize, upsert."""
import logging
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("test_crtsh")

from app.infra.db.session import SessionLocal
from app.infra.external.crtsh_client import CrtShClient
from app.repositories.domain_repository import ensure_partition, list_partition_tlds
from app.services.domain_normalizer import normalize_ct_domains
from app.services.use_cases.ingest_ct_batch import ingest_ct_batch
from app.repositories.ingestion_run_repository import IngestionRunRepository

db = SessionLocal()

# 1. Check partitions
tlds = list_partition_tlds(db)
logger.info("Existing partitions: %s", tlds)

# 2. Query crt.sh for com.br (small test)
crtsh = CrtShClient(timeout=60)
min_not_before = datetime.now(timezone.utc) - timedelta(hours=48)
logger.info("Querying crt.sh for *.com.br (last 48h)...")

try:
    raw_domains = crtsh.query_br_domains("com.br", min_not_before=min_not_before)
    logger.info("Got %d raw domains from crt.sh", len(raw_domains))

    if raw_domains:
        # Show sample
        logger.info("Sample raw: %s", raw_domains[:10])

        # 3. Normalize
        normalized = normalize_ct_domains(raw_domains)
        logger.info("Normalized: %d domains", len(normalized))
        if normalized:
            logger.info("Sample normalized: %s", normalized[:5])

        # 4. Ingest via pipeline
        run_repo = IngestionRunRepository(db)
        run = run_repo.create_run(source="crtsh-test", tld="br")
        db.commit()

        metrics = ingest_ct_batch(db, raw_domains, source="crtsh-test", run_id=run.id)
        db.commit()
        logger.info("Ingestion metrics: %s", metrics)

        # 5. Verify data in DB
        from sqlalchemy import text
        result = db.execute(text(
            "SELECT tld, count(*) FROM domain WHERE tld LIKE '%%br' GROUP BY tld ORDER BY count DESC"
        )).fetchall()
        logger.info("Domain counts by .br TLD: %s", dict(result))

        # Finalize run
        run_repo.finish_run(run, status="success")
        run_repo.upsert_checkpoint("crtsh-test", "br", run)
        db.commit()
        logger.info("Test run finalized: %s", run.id)
    else:
        logger.warning("No domains returned from crt.sh — service may be slow")

except Exception:
    logger.exception("Test failed")
    db.rollback()
finally:
    db.close()
