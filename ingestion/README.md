# ingestion

Production-grade domain ingestion pipeline.

Downloads CZDS zone files and OpenINTEL snapshots, computes set diffs, writes
Parquet deltas to Cloudflare R2, and loads them incrementally into PostgreSQL.

## Usage

```bash
# CZDS zone files
python -m ingestion czds --tlds=museum,travel --snapshot-date=2026-04-23

# OpenINTEL ccTLD snapshots
python -m ingestion openintel --tlds=br,de,fr

# Load deltas from R2 into PostgreSQL
python -m ingestion load --source=czds --snapshot-date=2026-04-23 --tlds=museum
```

## Environment Variables

```env
# R2 (Cloudflare)
R2_ACCOUNT_ID=xxx
R2_ACCESS_KEY_ID=xxx
R2_SECRET_ACCESS_KEY=xxx
R2_BUCKET=observadordedominios
R2_PREFIX=lake/domain_ingestion

# CZDS (ICANN)
CZDS_USERNAME=user@example.com
CZDS_PASSWORD=xxx
CZDS_TLDS=all
CZDS_MAX_TLDS=0

# OpenINTEL
OPENINTEL_TLDS=ac,br,uk,de,fr,se,nu,ch,li,sk,ee
OPENINTEL_MODE=auto

# PostgreSQL (loader)
DATABASE_URL=postgresql://user:pass@host/db

# Runtime
LOG_LEVEL=INFO
LOG_FORMAT=json
```
