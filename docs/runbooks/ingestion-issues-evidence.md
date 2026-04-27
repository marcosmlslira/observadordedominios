# Ingestion Issues Evidence Report
**Period investigated:** April 22–27 UTC 2026  
**Investigated on:** April 27 2026 (session TODO-011 production validation)  
**Container at investigation:** `6fb1902efa62` (`ghcr.io/marcosmlslira/observador-ingestion:latest`, deployed 2026-04-27 20:30 UTC)

---

## Executive Summary

| Issue | Impact | Status |
|---|---|---|
| P1 — OpenINTEL `duplicate key` (61 TLDs) | ~21% of OpenINTEL TLDs failed to load on April 27 | ✅ Fix deployed (`b5cba56`) |
| P2 — CZDS HTTP 429 rate limiting (261 failures) | April 24 CZDS cycle 37% failure rate | ⚠️ Needs auth throttling |
| P3 — CZDS 3-day silence (April 25–27) | Zero CZDS records for 3 days | ⚠️ Needs investigation |
| P4 — `ch` TLD timeout loop | `ch` consistently times out OpenINTEL (62m+ per run) | ⚠️ Needs investigation |
| P5 — Catalog corruption errors (13 TLDs) | DDL-in-hot-path race conditions on April 27 ~13:56 UTC | ✅ Mitigated by b5cba56 |
| P6 — `xn--y9a3aq` OID corruption | 4 consecutive "could not find tuple for parent" failures | 🔴 Needs Postgres recovery |
| P7 — OOM container kill (`xn--p1ai`) | At least one TLD killed the worker process via OOM | ✅ Memory limits deployed |

---

## Run History: April 22–27

```
run_date   | source    | total | success | failed | running | skipped
-----------+-----------+-------+---------+--------+---------+---------
2026-04-23 | czds      |   172 |     148 |     24 |       0 |       0
2026-04-23 | openintel |    63 |      62 |      1 |       0 |       0
2026-04-24 | czds      |   708 |     447 |    261 |       0 |       0
2026-04-24 | openintel |     3 |       0 |      3 |       0 |       0  ← crash loop starts
2026-04-25 | openintel |     3 |       0 |      3 |       0 |       0  ← 0 CZDS
2026-04-26 | openintel |     3 |       0 |      3 |       0 |       0  ← 0 CZDS
2026-04-27 | openintel |   141 |      59 |     81 |       1 |       0  ← 0 CZDS (after fix)
```

**Observation:** CZDS ran only on April 23 and 24. Three consecutive days (Apr 25–27) have zero CZDS records despite 1125 enabled TLDs in the policy table.

---

## P1 — OpenINTEL Duplicate Key Constraint Violation

### Description
61 OpenINTEL TLDs failed on April 27 with `duplicate key value violates unique constraint "domain_<tld>_pkey"`.

### Root Cause
The `LOAD_ONLY` phase used direct `COPY domain_<tld> FROM STDIN` with no deduplication. When R2 data overlaps with existing DB records, a `duplicate key` error aborts the entire COPY batch for that TLD.

### Error example (from `ingestion_run.error_message`)
```
duplicate key value violates unique constraint "domain_com_pkey"
DETAIL: Key (id)=(12345678) already exists.
CONTEXT: COPY domain_com, line 1: ...
```

### Affected TLDs (60 confirmed)
All `xn--*` IDN TLDs plus common TLDs in the OpenINTEL dataset. Exact list available via:
```sql
SELECT tld FROM ingestion_run
WHERE source='openintel' AND status='failed' AND started_at >= '2026-04-27'
  AND error_message LIKE '%duplicate key%';
```

### Fix
Commit `b5cba56` (`feat(ingestion): resilience hardening Sprint 2+3`) introduces a staging table approach in `ingestion/ingestion/loader/delta_loader.py` lines 136–161:
1. COPY data into `_staging_domain_<tld>` (temp table)
2. `INSERT INTO domain_<tld> SELECT ... FROM staging ON CONFLICT DO NOTHING`
3. Drop temp table

Fix is **confirmed present** in the running container:
```bash
docker exec 6fb1902efa62 grep -n "ON CONFLICT" /app/ingestion/loader/delta_loader.py
# Line 153: ON CONFLICT DO NOTHING
```

### Expected resolution
Next 04:00 UTC cycle (April 28) should see 0 duplicate key failures for these TLDs.

---

## P2 — CZDS HTTP 429 Rate Limiting (ICANN Auth API)

### Description
261 out of 708 CZDS runs on April 24 failed with HTTP 429 from ICANN's authentication endpoint.

### Error breakdown (April 23–27)
```
error_category                                    | cnt
-------------------------------------------------+-----
HTTP 429 Rate Limit (ICANN auth)                 | 281
Automatically marked failed: no progress 210m    |   2
Automatically marked failed: no progress 722m    |   1
server closed the connection unexpectedly        |   1
```

### Error message
```
429 Client Error: for url: https://account-api.icann.org/api/authenticate
```

### Root Cause
ICANN's CZDS authentication API (`account-api.icann.org`) applies rate limiting. When the ingestion worker attempts to authenticate hundreds of TLDs in rapid sequence, the API begins returning 429 for subsequent requests.

All 261/281 failed before writing any data (`snapshot_date = NULL`).

### Context
On April 24, 708 CZDS runs were attempted (vs. 172 on April 23). The jump likely reflects a backfill attempt after the container crash loop began. The 3.7× increase in requests triggered the rate limit.

### Recommended fix
- Implement exponential backoff with jitter in `czds_runner.py` `authenticate()` method
- Add per-TLD delay of 1–2s between CZDS auth attempts
- Consider sharing a single auth token session across all CZDS TLDs within a cycle instead of authenticating per-TLD

---

## P3 — CZDS 3-Day Silence (April 25–27)

### Description
Zero CZDS `ingestion_run` records on April 25, 26, and 27 UTC, despite 1125 enabled CZDS TLDs.

### CZDS TLD coverage analysis (as of April 27)
```
Category                                    | Count
--------------------------------------------+------
Had success within last 7 days (SKIP-eligible) | 595
Outdated > 7 days (needs LOAD_ONLY / FULL_RUN) | 419
Never successfully loaded (needs FULL_RUN)     | 111
Total enabled                               | 1125
```

Expected runs per cycle: 419 + 111 = **530 TLDs** (those needing LOAD_ONLY or FULL_RUN).

### Root cause: `_stop_event` set before CZDS phase

The scheduler runs in sequence:
```python
# scheduler.py lines 260-297
await _run_source(openintel_pipeline)  # runs first
if not _stop_event.is_set():           # CZDS only if not interrupted
    await _run_source(czds_pipeline)
```

**April 25–26:** Container crash loop. Only 3 OpenINTEL TLDs ran per day, all failing. Evidence:
- Watchdog recovery records show `xn--p1ai | stale: container restarted (OOM)` on April 27
- April 24: OpenINTEL had only 3 runs (0 success), signaling crash loop start
- Container killed by OOM → Docker restart → new container at 04:00 UTC starts fresh cycle → OpenINTEL crashes again after a few TLDs → `_stop_event` set on crash

**April 27:** 141 OpenINTEL TLDs processed (59 success), then 0 CZDS. The `_stop_event` was set before the CZDS phase began. Most likely cause: SIGTERM from Docker service update (our `docker service update` was at ~20:00 UTC but the cycle was at 04:00 UTC), OR the old container (before memory limit increase) OOM-killed during OpenINTEL phase at ~13:56 UTC (timestamp of the catalog corruption errors).

### Impact
- 419 TLDs now have zone data > 7 days stale
- 111 TLDs have NEVER been successfully loaded
- Total gap: 530 TLDs need FULL_RUN or LOAD_ONLY on next available cycle

### Recommended fix
- Add CZDS as independent second daily cycle (separate scheduler job at 08:00 UTC)
- Or: if `_stop_event` set during OpenINTEL, still run CZDS (remove the early exit guard for CZDS)
- Emergency backfill: `curl -X POST http://localhost:8080/run-now -H "Authorization: Bearer <token>"` after confirming CZDS is enabled

---

## P4 — `ch` TLD Repeated Timeouts

### Description
The `ch` (Switzerland) TLD consistently times out during OpenINTEL processing, generating stale run records recovered by the watchdog.

### Evidence
```
tld  | error_message                                          | started_at
-----+--------------------------------------------------------+------------
ch   | Automatically marked failed: no progress for 62m      | 2026-04-27 04:09:24 UTC
ch   | Container restarted - stale running record             | 2026-04-27
ch   | Run recovered automatically after stale timeout       | 2026-04-27 (×2)
```

### Current state
A `ch` run was left in `running` state from 2026-04-27 20:29:20 UTC (after our session's `/run-now` trigger), being recovered by the watchdog.

### Root Cause (unconfirmed)
`ch` is one of the largest TLDs in the OpenINTEL dataset. Processing may exceed the 60-minute watchdog threshold either due to:
- Network timeout downloading from R2 storage
- Memory pressure causing slow processing
- Corrupted OID reference (see P6 — `xn--y9a3aq` has concurrent OID errors nearby in time)

### Recommended fix
- Increase per-TLD timeout for known large TLDs, OR
- Add `ch` to exclusion list temporarily until root cause is found
- Profile `ch` TLD processing time in a debug run with `--only-tld ch`

---

## P5 — Catalog Corruption Errors (DDL Hot-Path Race)

### Description
13 TLDs failed at 2026-04-27 13:56–13:57 UTC with errors indicating concurrent DDL while queries were running.

### Error signatures
```
tld               | error_message
------------------+--------------------------------------------------
xn--qxa6a         | tuple concurrently deleted
xn--qxam          | tuple concurrently updated
xn--rvc1e0am3e    | tuple concurrently updated
xn--s9brj9c       | tuple concurrently updated
xn--wgbh1c        | "domain_xn__wgbh1c" is already a partition
xn--wgbl6a        | "domain_xn__wgbl6a" is already a partition
xn--xkc2al3hye2a  | "domain_xn__xkc2al3hye2a" is already a partition
xn--xkc2dl3a5ee0h | tuple concurrently deleted
xn--y9a3aq        | tuple concurrently deleted
xn--yfro4i67o     | pg_attribute catalog is missing 4 attribute(s) for relation OID 111607
xn--ygbi2ammx     | tuple concurrently deleted
```

### Root Cause
These errors occurred at ~13:56 UTC, the burst of `/run-now` API calls during our validation session. Two concurrent ingestion cycles (scheduled 04:00 UTC still running + `/run-now` triggered cycle) executed DDL (`CREATE TABLE IF NOT EXISTS domain_<tld>`, `ATTACH PARTITION`) while the other cycle was querying catalog tables. Classic DDL-in-hot-path scenario (root cause F1 from TODO-011).

### Mitigation
`b5cba56` (Sprint 2) isolates DDL with `pg_try_advisory_lock` and a `_ensure_partition` guard that skips DDL if partition already exists. This prevents the "is already a partition" class of errors. The `tuple concurrently deleted/updated` errors are mitigated by the advisory lock serializing DDL per-TLD.

---

## P6 — `xn--y9a3aq` OID Reference Corruption

### Description
`xn--y9a3aq` failed 4 times between 20:02 and 20:29 UTC on April 27 with a Postgres catalog OID reference error.

### Error
```
could not find tuple for parent of relation 111567
```

### Evidence
```
tld       | error_message                                    | started_at
----------+-------------------------------------------------+------------------------------
xn--y9a3aq| could not find tuple for parent of relation 111567 | 2026-04-27 20:02:48 UTC
xn--y9a3aq| could not find tuple for parent of relation 111567 | 2026-04-27 20:16:14 UTC
xn--y9a3aq| could not find tuple for parent of relation 111567 | 2026-04-27 20:20:09 UTC
xn--y9a3aq| could not find tuple for parent of relation 111567 | 2026-04-27 20:29:19 UTC
```

### Analysis
OID `111567` likely refers to the `domain_xn__y9a3aq` partition. The error "could not find tuple for parent" means the partition's parent reference in `pg_inherits` or `pg_class` is broken — a catalog-level inconsistency, not a data error. This was likely caused by the concurrent DDL in P5 (partition created then immediately dropped or partially created by a racing transaction).

### Recommended recovery
```sql
-- Identify the broken relation
SELECT oid, relname, relkind FROM pg_class WHERE oid = 111567;

-- If the partition table exists but catalog is corrupt:
-- Option A: DROP and recreate
DROP TABLE IF EXISTS domain_xn__y9a3aq;
-- Next ingestion cycle will recreate via CREATE TABLE IF NOT EXISTS

-- Option B: Run VACUUM ANALYZE to refresh catalog stats
VACUUM ANALYZE domain;
```

> ⚠️ **Run during a maintenance window.** Do not run concurrent ingestion while repairing.

---

## P7 — OOM Container Kill

### Description
At least one TLD (`xn--p1ai`) was marked stale with the message `stale: container restarted (OOM)`, confirming the worker was killed by the Linux OOM killer.

### Evidence from `ingestion_run` table
```
xn--p1ai | stale: container restarted (OOM) | 2026-04-27
```

### Context
This was the pre-TODO-011 container without memory limits. The OOM kill triggered Docker's `restart_policy: on-failure`, causing the crash loop on April 24–26.

### Resolution
TODO-011 Sprint 1 deployed:
- `ingestion_worker`: `limits.memory: 4G`, `reservations.memory: 2G`
- `postgres`: `limits.memory: 8G`, `reservations.memory: 4G`
- `restart_policy: condition: any, delay: 30s`

Deployed to production via `observador.yml` commit `4187c84`.

---

## Catalog of All `ingestion_run` Failures April 22–27

### OpenINTEL failure category summary (April 27)
```
error_category                              | count
--------------------------------------------+------
Duplicate Key (ON CONFLICT missing)         |    60
Stale/Recovery (container restart)          |     5
tuple concurrently deleted                  |     4
could not find tuple for parent of relation |     4
tuple concurrently updated                  |     3
pg_attribute catalog missing attribute(s)   |     1
is already a partition                      |     3
Automatically marked failed (>60m stale)    |     1
```

### CZDS failure category summary (April 23–27)
```
error_category                              | count
--------------------------------------------+------
HTTP 429 Rate Limit (ICANN auth)            |   281
Automatically marked failed (>210m stale)   |     2
Automatically marked failed (>722m stale)   |     1
server closed the connection unexpectedly   |     1
```

---

## Outstanding Issues Requiring Follow-up

| Priority | Issue | Next Action |
|---|---|---|
| 🔴 High | `xn--y9a3aq` OID corruption — 4 consecutive failures | Run catalog repair SQL in maintenance window |
| 🔴 High | CZDS 3-day silence — 530 TLDs need immediate backfill | Trigger `/run-now` when current `ch` run clears; verify CZDS runs April 28 04:00 UTC |
| 🟠 Medium | CZDS HTTP 429 rate limiting — will recur on next full cycle | Implement auth session reuse or per-TLD delay in `czds_runner.py` |
| 🟠 Medium | `ch` TLD repeated timeouts — blocks OpenINTEL cycles | Profile `ch` processing time; consider timeout increase |
| 🟡 Low | Validate April 28 04:00 UTC cycle resolves P1 (duplicate key) | Monitor `ingestion_run` at ~04:30 UTC April 28 |

---

## Verification Queries

```sql
-- Check April 28 04:00 UTC cycle results (run after 04:30 UTC)
SELECT source, status, COUNT(*) 
FROM ingestion_run
WHERE started_at >= CURRENT_DATE - INTERVAL '1 day'
GROUP BY 1, 2 ORDER BY 1, 2;

-- Confirm duplicate key errors resolved
SELECT COUNT(*) FROM ingestion_run
WHERE source='openintel' AND status='failed'
  AND started_at >= CURRENT_DATE - INTERVAL '1 day'
  AND error_message LIKE '%duplicate key%';

-- Check CZDS resumed
SELECT COUNT(*) FROM ingestion_run
WHERE source='czds' AND started_at >= CURRENT_DATE - INTERVAL '1 day';

-- Check xn--y9a3aq corruption
SELECT 1 FROM ingestion_run
WHERE tld='xn--y9a3aq' AND status='success'
  AND started_at >= CURRENT_DATE - INTERVAL '1 day';
```
