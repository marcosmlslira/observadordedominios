# CT Logs Ingestion — Design & Status

## Status: OPERATIONAL (2026-03-23)

- CertStream real-time ingestion: **ACTIVE** via self-hosted certstream-server-go
- crt.sh daily sync: **SCHEDULED** (05:00 UTC daily)
- Historical bulk load: **SCRIPT READY** (run manually when crt.sh is available)
- ~37K+ `.br` domains ingested and growing (~200 unique/30s)

---

## Architecture (Final)

```
certstream-server-go (self-hosted, Docker)
         │ monitors 37+ CT logs
         │ ~1000 entries/5s
         ▼
CertStreamClient (WebSocket ws://certstream_server:8080/)
         │ filter .br only
         ▼
CTBuffer (in-memory set, thread-safe)
         │ flush (5K domains or 30s)
         │
crt.sh (HTTP, cron 05:00 UTC) ──────┤
         │                           │
crt.sh (HTTP, one-time bulk) ───────┤
                                     │
                         domain_normalizer (tldextract)
                                     │
                         ingest_ct_batch (shared pipeline)
                                     │
                         bulk_upsert_multi_tld()
                                     │
               domain_com_br / domain_net_br / domain_org_br / ...
                                     │
                         similarity_worker (auto delta scan)
```

---

## Key Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| CertStream server | Self-hosted certstream-server-go | CaliDog public server is dead since ~2025 |
| Storage | Direct into `domain` table | Partitioned by TLD; upsert idempotent; similarity worker consumes automatically |
| Worker | Single `ct_ingestor` container | CertStream + crt.sh share pipeline; .br volume is low |
| Historical load | crt.sh HTTP API with prefix chunking | PostgreSQL replica too unstable (recovery conflicts) |
| TLD scope | .br and sub-TLDs only | CZDS covers gTLDs; focus on the real gap |

---

## Components

### Self-hosted CertStream Server
- **Image:** `0rickyy0/certstream-server-go:latest`
- **Config:** `infra/certstream-config.yaml` (custom buffer sizes: ws=2000, ctlog=2000, broadcast=50000)
- Monitors 37+ CT logs from Google's log list
- Internal endpoint: `ws://certstream_server:8080/`

### CT Ingestor Worker (`python -m app.worker.ct_ingestor`)
- **CertStream** (real-time): WebSocket → CTBuffer → flush every 30s → ingest_ct_batch
- **crt.sh** (daily): APScheduler cron → sync_crtsh_tld → ingest_ct_batch
- Graceful shutdown: SIGTERM → final flush → finalize ingestion_run

### Historical Bulk Loader (`python -m app.debug_scripts.run_crtsh_bulk_load`)
- Strategy: HTTP API per sub-TLD, prefix-split for com.br (a%.com.br, b%.com.br, ...)
- Checkpoint: `/tmp/crtsh_bulk_checkpoint.json` for resume
- Env vars: `BULK_SUBTLDS`, `BULK_YEARS`, `BULK_DRY_RUN`

---

## Files

| File | Purpose |
|------|---------|
| `infra/certstream-config.yaml` | CertStream server config |
| `backend/app/worker/ct_ingestor.py` | Worker entry point |
| `backend/app/infra/external/certstream_client.py` | WebSocket client with auto-reconnect |
| `backend/app/infra/external/crtsh_client.py` | HTTP client with retry/backoff |
| `backend/app/services/domain_normalizer.py` | tldextract normalization |
| `backend/app/services/use_cases/ingest_ct_batch.py` | Shared batch pipeline |
| `backend/app/services/use_cases/sync_crtsh.py` | Daily crt.sh orchestration |
| `backend/app/services/use_cases/bulk_load_crtsh.py` | Historical bulk loader |
| `backend/alembic/versions/007_ct_br_partitions.py` | Migration: 11 .br partitions |

---

## Configuration

```python
CT_CERTSTREAM_URL: str = "ws://certstream_server:8080/"
CT_CERTSTREAM_ENABLED: bool = True
CT_CERTSTREAM_RECONNECT_MAX_BACKOFF: int = 60
CT_BUFFER_FLUSH_SIZE: int = 5000
CT_BUFFER_FLUSH_SECONDS: int = 30
CT_CRTSH_ENABLED: bool = True
CT_CRTSH_SYNC_CRON: str = "0 5 * * *"
CT_CRTSH_COOLDOWN_HOURS: int = 20
CT_CRTSH_QUERY_OVERLAP_HOURS: int = 25
CT_BR_SUBTLDS: str = "br,com.br,net.br,org.br,gov.br,edu.br,mil.br,app.br,dev.br,log.br,ong.br"
```

---

## Throughput

- CertStream: ~150-250 unique .br domains per 30s flush
- crt.sh daily: ~3,500 domains per cycle (25h overlap window)
- Bulk load: ~8K domains per small sub-TLD query

---

## Known Issues

1. **CaliDog public CertStream is dead** → solved with self-hosted server
2. **crt.sh has intermittent 502/503 outages** → bulk loader has retry + checkpoint
3. **crt.sh PostgreSQL replica has recovery conflicts** → use HTTP API instead
4. **certstream-server-go initial catch-up** causes high volume → custom buffer sizes prevent overflow
