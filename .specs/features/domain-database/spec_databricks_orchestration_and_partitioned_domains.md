# Spec: Databricks Orchestration + Partitioned Domain Model

## 1. Context

Domain ingestion is moving to a model based on:
1. heavy processing in Databricks (download + diff),
2. R2 as data lake for exchange and control artifacts,
3. incremental backend ingestion into PostgreSQL,
4. similarity execution only on new partitions.

Spec version date: 2026-04-22

---

## 2. Goal

Implement a backend module that:
1. Triggers Databricks jobs per source.
2. Tracks granular status by `source + tld + snapshot_date`.
3. Reconciles readiness through R2 control artifacts.
4. Loads final deltas into a new partitioned domain model.
5. Feeds incremental similarity only with newly added domains.
6. Supports safe cutover from legacy `domain` table.

---

## 3. Scope

### 3.1 In scope
1. Backend orchestration for Databricks runs.
2. Partition control tables (`source+tld+snapshot_date`).
3. New domain data model (`domain_delta_added`, `domain_delta_removed`, `domain_current`).
4. Idempotent incremental load from R2 to PostgreSQL.
5. Similarity queue/run control separated from ingestion partition state.
6. Cutover with dual-read, canary and rollback window.

### 3.2 Out of scope in this phase (explicit PRD gaps)
1. DNS snapshots (A, AAAA, NS, MX, TXT).
2. `registered_at_best` and confidence scoring model.
3. CT Logs ingestion as first class source in this pipeline.
4. pDNS ingestion as first class source in this pipeline.
5. Paid external feeds ingestion.
6. Product/UI expansion beyond operational visibility.

---

## 4. Functional requirements

1. Backend must create and monitor Databricks runs.
2. Backend must persist partition status by `source+tld+snapshot_date`.
3. Backend must use R2 markers as the primary readiness signal.
4. Backend must load `new_domains` and `removed_domains` idempotently.
5. Backend must keep `domain_current` synchronized per source+tld.
6. Backend must enqueue similarity work only for successful new partitions.
7. Backend must support manual replay per partition.

---

## 5. Non-functional requirements

1. Strong idempotency per partition.
2. Partial failure isolation by TLD.
3. Compatibility with current similarity behavior.
4. Scalability for high volume TLDs (`.com`) using shard/chunk strategy.
5. Full observability by run and partition.

---

## 6. Proposed architecture

### 6.1 Backend components
1. `DatabricksJobClient`
2. `IngestionControlService`
3. `R2IngestionManifestReader`
4. `DomainDeltaLoader`
5. `SimilarityPartitionScheduler`
6. `IngestionMonitoring`

### 6.2 High-level flow
1. Backend submits Databricks job.
2. Databricks writes deltas + control files into R2.
3. Backend reconciles completed partitions based on `markers/.../success.json`.
4. Backend loads data into PostgreSQL tables.
5. Backend creates similarity run records for new partitions.

---

## 7. Data model (application)

## 7.1 Source contract
Use `source TEXT` (not numeric source code) with check constraint.

Allowed values in this phase:
- `czds`
- `openintel`

Constraint example:
```sql
CHECK (source IN ('czds', 'openintel'))
```

## 7.2 Run control
Table: `domain_ingestion_run`
- `id UUID PK`
- `source TEXT NOT NULL`
- `snapshot_date DATE NOT NULL`
- `databricks_run_id BIGINT`
- `status TEXT` (`queued`, `running`, `success`, `failed`, `partial`)
- `started_at TIMESTAMPTZ`
- `finished_at TIMESTAMPTZ`
- `error TEXT`
- `metadata_json JSONB`

Indexes:
- `(source, snapshot_date)`
- `(databricks_run_id)`

## 7.3 Partition control (ingestion state only)
Table: `domain_ingestion_partition`
- `id UUID PK`
- `run_id UUID REFERENCES domain_ingestion_run(id)`
- `source TEXT NOT NULL`
- `tld TEXT NOT NULL`
- `snapshot_date DATE NOT NULL`
- `status TEXT` (`queued`, `running`, `success`, `failed`, `partial`)
- `added_count BIGINT`
- `removed_count BIGINT`
- `loaded_to_app_at TIMESTAMPTZ`
- `error TEXT`
- `metadata_json JSONB`

Unique constraint:
- `(source, tld, snapshot_date)`

## 7.4 Similarity queue/run (separated from ingestion partition)
Table: `domain_similarity_partition_run`
- `id UUID PK`
- `source TEXT NOT NULL`
- `tld TEXT NOT NULL`
- `snapshot_date DATE NOT NULL`
- `partition_id UUID REFERENCES domain_ingestion_partition(id)`
- `status TEXT` (`pending`, `running`, `done`, `failed`, `canceled`)
- `started_at TIMESTAMPTZ`
- `finished_at TIMESTAMPTZ`
- `error TEXT`
- `metadata_json JSONB`

Behavior:
1. Multiple runs allowed for same partition (re-run support).
2. Latest `done` run marks similarity completion for that partition.
3. Integration with existing `similarity_scan_job` and `similarity_scan_cursor` is preserved.

## 7.5 Added deltas
Table: `domain_delta_added`
- `source TEXT NOT NULL`
- `tld TEXT NOT NULL`
- `snapshot_date DATE NOT NULL`
- `domain_norm TEXT NOT NULL`
- `domain_raw TEXT NOT NULL`
- `run_id UUID NOT NULL`
- `loaded_at TIMESTAMPTZ NOT NULL`

Partitioning:
- RANGE by `snapshot_date`

Unique constraint:
- `(source, tld, snapshot_date, domain_norm)`

## 7.6 Removed deltas
Table: `domain_delta_removed`
- same columns as `domain_delta_added`

Partitioning:
- RANGE by `snapshot_date`

Unique constraint:
- `(source, tld, snapshot_date, domain_norm)`

## 7.7 Current state
Table: `domain_current`
- `source TEXT NOT NULL`
- `tld TEXT NOT NULL`
- `domain_norm TEXT NOT NULL`
- `domain_raw TEXT NOT NULL`
- `first_seen_date DATE NOT NULL`
- `last_seen_date DATE NOT NULL`
- `is_active BOOLEAN NOT NULL`
- `first_seen_run_id UUID`
- `last_seen_run_id UUID`
- `updated_at TIMESTAMPTZ NOT NULL`

Partitioning:
- LIST by `tld`

Unique constraint:
- `(source, tld, domain_norm)`

Required indexes:
```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX IF NOT EXISTS idx_domain_current_source_tld_active
  ON domain_current (source, tld, is_active);
CREATE INDEX IF NOT EXISTS idx_domain_current_domain_norm_trgm
  ON domain_current USING gin (domain_norm gin_trgm_ops);
```

Important:
- `domain_raw_b64` is intentionally removed from this model.

---

## 8. R2 contract

Backend depends on this path contract:
1. `new_domains/source={source}/snapshot_date={date}/tld={tld}/...`
2. `removed_domains/source={source}/snapshot_date={date}/tld={tld}/...`
3. `domains_current/source={source}/tld={tld}/...`
4. `ingestion_runs/source={source}/snapshot_date={date}/tld={tld}/...`
5. `markers/source={source}/tld={tld}/snapshot_date={date}/success.json`

Readiness rule:
- marker is definitive; run status is auxiliary.

---

## 9. Databricks orchestration

1. Create run by source and TLD window.
2. Store `domain_ingestion_run` in `queued/running`.
3. Poll Databricks with timeout/backoff only as auxiliary monitoring.
4. Reconcile completion by checking R2 markers.
5. Update each partition and start load for `success` partitions.

Optional future improvement:
- webhook/callback from Databricks, still validated by marker existence.

---

## 10. Incremental load

1. Read parquet from `new_domains` and `removed_domains`.
2. Upsert idempotently into delta tables.
3. Upsert `domain_current` by domain key.
4. Mark `loaded_to_app_at` when complete.
5. Replay only with explicit operator action.

---

## 11. Similarity integration

1. Create `domain_similarity_partition_run` entries for successful loaded partitions.
2. Similarity workers consume pending records.
3. Existing similarity pipeline keeps brand logic and ranking logic.
4. Re-runs do not mutate ingestion status; they create new similarity run rows.

Directly impacted backend resources (minimum):
1. `backend/app/repositories/similarity_repository.py`
2. `backend/app/services/similarity_scan_jobs.py`
3. `backend/app/services/use_cases/run_similarity_scan.py`
4. `backend/app/models/similarity_scan_job.py`
5. `backend/app/models/similarity_scan_cursor.py`

---

## 12. Normalization contract

Canonical rules for `domain_norm`:
1. Trim spaces.
2. Lowercase.
3. Remove trailing dot.
4. IDN converted to ASCII punycode.
5. Reject invalid FQDN labels.

Validation:
1. Backend performs sample validation per partition.
2. If violation rate exceeds threshold (default `0.1%`), mark partition as failed.
3. Violations and sample errors stored in `metadata_json`.

---

## 13. Backpressure and concurrency

Operational limits (configurable):
1. Max concurrent partition loads to PostgreSQL: `4`.
2. Max pending similarity runs before throttle: `200`.
3. Alert when ingestion backlog age is above `6h`.
4. Alert when similarity backlog age is above `12h`.

---

## 14. Retention policy

1. `domain_delta_added` and `domain_delta_removed`: keep 90 days (default).
2. `domain_ingestion_run` and `domain_ingestion_partition`: keep 180 days.
3. R2 `snapshot_stage`: keep 5 days.
4. R2 control artifacts (`markers`, `ingestion_runs`): keep 180 days.

Retention must be configurable by environment.

---

## 15. Migration and cutover plan

1. Create new tables/indexes/partitions in parallel to legacy model.
2. Run initial load for selected canary TLDs (example: `.museum`, `.net`).
3. Enable dual-read shadow mode:
   - old reads remain primary,
   - new model read results are compared and logged.
4. Validate domain counts, random sampling, and similarity output parity.
5. Expand canary to high volume TLDs (`.com`) after target SLO.
6. Enable feature flag for new read path.
7. Keep legacy table for rollback window (minimum 30 days).
8. Only after rollback window and acceptance, archive/truncate legacy table.

---

## 16. Observability

Minimum metrics:
1. Runs by status (`source`, `snapshot_date`).
2. Partitions by status (`source`, `tld`, `snapshot_date`).
3. Load throughput and load failures.
4. Similarity queue depth and completion lag.
5. Normalization violation rate.

Alerts:
1. Run stuck without final status.
2. Partition without marker after expected SLA.
3. Mismatch between declared counts and loaded rows.
4. Similarity queue backlog above threshold.

---

## 17. Implementation phases

Phase 1: DDL and migration scaffolding.
Phase 2: Databricks orchestration and R2 reconciliation.
Phase 3: Incremental loader and idempotency.
Phase 4: Similarity queue integration.
Phase 5: Canary + dual-read + cutover.

---

## 18. Acceptance criteria

1. Query status by `source+tld+snapshot_date`.
2. Replay partition without duplicates.
3. Similarity consumes only new loaded partitions.
4. Works for both `czds` and `openintel`.
5. Trigram search performance remains within SLO.
6. Cutover finished with rollback window respected.

---

## 19. Reimplementation inputs

### 19.1 Secrets and environment variables
1. Databricks
- `DATABRICKS_HOST`
- `DATABRICKS_TOKEN`

2. Cloudflare R2
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET`
- `R2_REGION` (usually `auto`)
- `R2_PREFIX`

3. CZDS
- `CZDS_USERNAME`
- `CZDS_PASSWORD`

4. OpenINTEL (if endpoint/cookie required)
- `OPENINTEL_ZONEFILE_ENDPOINT`
- `OPENINTEL_ZONEFILE_BUCKET`
- `OPENINTEL_WEB_BASE`
- `OPENINTEL_WEB_FILES_BASE`
- `OPENINTEL_COOKIE_NAME`
- `OPENINTEL_COOKIE_VALUE`

### 19.2 External APIs
1. Databricks Jobs API:
- `POST /api/2.1/jobs/runs/submit`
- `GET /api/2.1/jobs/runs/get`
- `POST /api/2.1/jobs/runs/cancel`

2. CZDS:
- `POST https://account-api.icann.org/api/authenticate`
- `GET https://czds-api.icann.org/czds/downloads/links`
- `GET https://czds-api.icann.org/czds/downloads/{tld}.zone`

3. OpenINTEL:
- public object endpoints and/or web snapshot endpoints (config driven)

### 19.3 Minimal parquet schemas
1. `new_domains` / `removed_domains`
- `source` (string)
- `tld` (string)
- `snapshot_date` (date/string)
- `domain_norm` (string)
- `domain_raw` (string)
- `run_id` (string/uuid)
- `processed_at` (timestamp/string)

2. `domains_current`
- `source` (string)
- `tld` (string)
- `domain_norm` (string)
- `domain_raw` (string)
- `first_seen_date` (date)
- `last_seen_date` (date)
- `is_active` (boolean)
- `first_seen_run_id` (string/uuid)
- `last_seen_run_id` (string/uuid)
- `updated_at` (timestamp)

### 19.4 Idempotency rules
1. Partition is ready only when marker exists.
2. DB load uses natural keys + `ON CONFLICT`.
3. Manual replay requires explicit replay flag and operator audit.