# Spec: Impact Analysis - Databricks Orchestration + New Partitioned Domain Model

## 1. Objective

Map impacted resources for migration to:
1. Databricks-based processing,
2. granular partition control (`source+tld+snapshot_date`),
3. incremental load into new PostgreSQL model,
4. separated similarity execution state per partition run.

Focus:
- what changes,
- what can break,
- who must adapt,
- mitigation before cutover.

---

## 2. Scope analyzed

1. New backend orchestration module for Databricks.
2. New ingestion control tables.
3. New domain storage strategy (`domain_delta_added`, `domain_delta_removed`, `domain_current`).
4. Similarity state moved to dedicated run table (`domain_similarity_partition_run`).
5. Legacy `domain` table deprecation after cutover window.

---

## 3. Key model decisions reflected in impact

1. `source` is `TEXT` with constrained values (no `source_code SMALLINT`).
2. `domain_raw_b64` removed from persistence model.
3. `domain_ingestion_partition` contains ingestion state only.
4. Similarity state is tracked in separate table.
5. `domain_current` is partitioned by TLD.
6. Trigram index on `domain_current.domain_norm` is mandatory.

---

## 4. Impact matrix by resource

## 4.1 Backend API / services

### Impacted resources
1. `backend/app/api/v1/routers/ingestion.py`
2. `backend/app/api/v1/routers/czds_ingestion.py`
3. `backend/app/services` (new orchestration and loader services)

### Impact level
- High

### Required changes
1. Add Databricks trigger/status/cancel flow.
2. Add partition reconciliation using R2 markers.
3. Add partition replay endpoint/flow.
4. Add operational read APIs for run and partition status.

### Main risk
- Duplicate loads on retries.

### Mitigation
- Natural keys + strict idempotency and replay guard.

---

## 4.2 Database schema and migrations

### Impacted resources
1. `backend/alembic/versions/*` (new migrations)
2. `backend/app/models/domain.py` (legacy to be isolated/deprecated)
3. New models for ingestion and partitioned domain storage.

### Impact level
- High

### Required changes
1. Create tables:
- `domain_ingestion_run`
- `domain_ingestion_partition`
- `domain_similarity_partition_run`
- `domain_delta_added`
- `domain_delta_removed`
- `domain_current`
2. Partition `domain_current` by TLD.
3. Partition delta tables by `snapshot_date`.
4. Create trigram index and supporting indexes.

### Main risk
- Query plan degradation under high volume.

### Mitigation
- Performance validation in staging with `.net` and `.com` canary.

---

## 4.3 Similarity pipeline

### Impacted resources
1. `backend/app/repositories/similarity_repository.py`
2. `backend/app/services/similarity_scan_jobs.py`
3. `backend/app/services/use_cases/run_similarity_scan.py`
4. `backend/app/models/similarity_scan_job.py`
5. `backend/app/models/similarity_scan_cursor.py`
6. `backend/app/worker/similarity_worker.py`

### Impact level
- High

### Required changes
1. Replace ingestion-coupled `similarity_status` usage with dedicated similarity run table.
2. Ensure worker reads only pending partition runs.
3. Ensure re-runs generate new run rows without changing ingestion completion state.
4. Keep compatibility with current brand-level cursor/job semantics.

### Main risk
- Missed or duplicated similarity scans.

### Mitigation
- Transactional state transitions and unique execution guard per run id.

---

## 4.4 Domain repositories and read path

### Impacted resources
1. `backend/app/repositories/domain_repository.py`
2. Any query currently bound to legacy `domain` shape.

### Impact level
- High

### Required changes
1. Adapt read queries to `domain_current`.
2. Preserve behavior for active/inactive semantics.
3. Validate fuzzy/similarity related queries against trigram index.

### Main risk
- Functional mismatch during cutover.

### Mitigation
- Dual-read shadow mode with parity checks.

---

## 4.5 Databricks integration

### Impacted resources
1. Databricks client module (new)
2. Scheduling/runner integration module (new or existing scheduler)

### Impact level
- Medium-High

### Required changes
1. Persist `databricks_run_id` per business run.
2. Polling with timeout/backoff for auxiliary visibility.
3. Marker-driven completion as source of truth.

### Main risk
- Long-running run without clear terminal signal.

### Mitigation
- SLA timeout + cancel path + marker reconciliation.

---

## 4.6 R2 / data lake contract

### Impacted resources
1. R2 reader/manifest module (new)
2. Existing ingestion path assumptions in scripts/services

### Impact level
- High

### Required changes
1. Freeze path contract for `new_domains`, `removed_domains`, `domains_current`, `ingestion_runs`, `markers`.
2. Validate partition only after success marker.
3. Keep retention policy enforced by lifecycle jobs.

### Main risk
- Partial object sets interpreted as complete data.

### Mitigation
- Atomic marker policy (marker written only after all files are complete).

---

## 4.7 Operations / support / observability

### Impacted resources
1. Dashboards and alerts
2. Runbooks and incident procedures

### Impact level
- Medium

### Required changes
1. Add run/partition/similarity backlog dashboards.
2. Add alerts for stuck runs and marker absence.
3. Add replay runbook and rollback runbook.

### Main risk
- Low visibility on partial failures.

### Mitigation
- Partition-level dashboards and SLO-based alerts.

---

## 4.8 Security and compliance

### Impacted resources
1. Secret management for Databricks/R2/CZDS/OpenINTEL
2. CI scanning and logging redaction

### Impact level
- Medium

### Required changes
1. No credentials hardcoded in code/notebooks/spec examples.
2. Least-privilege roles for Databricks, R2, DB.
3. Secret rotation and audit.

### Main risk
- Credential leakage.

### Mitigation
- Secret manager + rotation + scanning in CI.

---

## 5. Cutover impact and safeguards

1. Canary sequence by TLD (`.museum`/`.net` first, `.com` after SLO pass).
2. Dual-read shadow mode before switching primary read path.
3. Similarity parity validation against legacy behavior.
4. Rollback window: keep legacy table for at least 30 days.
5. Only after stable period, archive and truncate legacy data.

---

## 6. Retention and cost impact

1. `domain_delta_*`: 90 days default retention.
2. Ingestion control tables: 180 days default retention.
3. R2 `snapshot_stage`: 5 days retention.
4. R2 control artifacts: 180 days retention.

Expected cost impacts:
1. Databricks compute grows with volume and cadence.
2. R2 PUT/LIST/GET grows with shard fan-out.
3. PostgreSQL storage controlled by retention and partition pruning.

---

## 7. Backpressure impact

Operational limits to avoid overload:
1. Max concurrent partition DB loads: 4.
2. Similarity pending queue soft cap: 200.
3. Alert if ingestion backlog age > 6h.
4. Alert if similarity backlog age > 12h.

Impacted components:
1. Scheduler concurrency settings.
2. Worker throughput configuration.
3. Monitoring thresholds.

---

## 8. Readiness checklist

1. New schema deployed and indexed (including trigram).
2. Marker-driven reconciliation validated.
3. Normalization contract validation implemented.
4. Similarity repository/use cases migrated and tested.
5. Dual-read shadow tests passed.
6. Canary passed for low and high volume TLD.
7. Rollback procedures validated.

---

## 9. Blockers (must close before production cutover)

1. Trigram index not present on `domain_current.domain_norm`.
2. Similarity state still coupled to ingestion partition table.
3. Missing mapping updates in `similarity_repository.py` and related use cases.
4. Missing explicit out-of-scope alignment with PRD.
5. Missing dual-read/canary/rollback execution evidence.

---

## 10. Recommended decision

Proceed with phased rollout after blockers are closed.
This architecture is viable and scalable for CZDS/OpenINTEL, with lower operational risk only if cutover safeguards and similarity mapping changes are completed first.