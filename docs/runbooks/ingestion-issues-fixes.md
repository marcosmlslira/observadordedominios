# Ingestion Issues — Fixes & Action Plan

**Companion to:** `docs/runbooks/ingestion-issues-evidence.md`
**Author:** TODO-011 follow-up — 2026-04-27
**Scope:** Solutions for P1–P7 from the evidence report, ordered by operational urgency.

> Rule of engagement: every fix below has (a) **what to change**, (b) **why this fix and not another**, (c) **how to verify**, (d) **rollback plan**. No fix ships without all four.

---

## ✅ Implementation status (2026-04-28)

The following fixes have been **implemented in code**:

| Issue | Status | File changed |
|-------|--------|-------------|
| P2 — CZDS 429 auth rate-limit | ✅ DONE | `ingestion/sources/czds/client.py` — exponential backoff (5 retries, 5–120 s, ±25% jitter) |
| P3 — CZDS 3-day silence | ✅ DONE | `ingestion/scheduler.py` + `observability/run_recorder.py` — `_run_czds_recovery` job at 08:00 UTC |
| P4 — `ch` TLD stale timeout | ✅ DONE | `docker-stack-infra/stacks/observador-ingestion.yml.draft` — `INGESTION_STALE_TIMEOUT_MINUTES=90` |
| P6 — `xn--y9a3aq` OID corruption | ⚠️ MANUAL | Must run DROP TABLE repair on production (see A1 below) |
| P1, P5, P7 | ✅ Already fixed | Prior sessions |

**Pending before deploy:**
1. Commit + push `observadordedominios` → triggers CI/CD image build for ingestion worker
2. Commit + push `docker-stack-infra` → applies P4 timeout env var when stack is activated
3. Run P6 manual DB repair during maintenance window (see A1)
4. Monitor 04:00 UTC + 08:00 UTC cycle on April 29+ for validation

---

## Action plan — ordered by urgency

| # | Action | Class | Estimated effort | Blocks |
|---|---|---|---|---|
| A1 | Catalog repair: `xn--y9a3aq` (P6) | Operacional / DBA | 30min, maintenance window | P1 verification on this TLD |
| A2 | CZDS backfill plan (P3) — 530 TLDs | Operacional | 2–4h supervisionada | New CZDS data |
| A3 | Scheduler refactor: isolar fontes (P3) | Code (medium) | 1 sprint | A2 sustentável |
| A4 | CZDS auth session reuse + backoff (P2) | Code (medium) | 2–3 dias | Recorrência de 429 |
| A5 | `ch` profiling + chunk streaming (P4) | Diag + Code | 1 sprint | OpenINTEL não-bloqueante |
| A6 | Generic partition repair script (P6 systemic) | Code (small) | 1 dia | Recovery automation |
| A7 | DDL contention monitoring (P5) | Observability | 4h | Early warning |
| A8 | OOM watchdog + memory budget alerts (P7) | Observability | 4h | Pre-failure detection |
| A9 | P1 verification dashboard query (P1) | Observability | 2h | Confirma o fix |

---

## A1 — Catalog repair: `xn--y9a3aq` (P6) 🔴

### What to change

Run a one-shot repair in a maintenance window using a generalized version of `backend/app/debug_scripts/repair_p14_xn_yfro4i67o.py` adapted for `xn--y9a3aq` (OID 111567).

**Pre-flight (read-only diagnosis):**
```sql
-- Confirm OID still exists and what it points to
SELECT oid, relname, relkind, relnamespace::regnamespace
FROM pg_class WHERE oid = 111567;

-- Check pg_inherits for orphan parent reference
SELECT inhrelid::regclass, inhparent::regclass
FROM pg_inherits WHERE inhrelid = 111567 OR inhparent = 111567;

-- Confirm partition table still has data we don't want to lose
SELECT count(*) FROM domain_xn__y9a3aq;
```

**Repair (after confirming no concurrent ingestion):**
```sql
BEGIN;
-- Stop the scheduler first via SIGTERM (graceful) — see verification below
-- Try clean DETACH first
ALTER TABLE domain DETACH PARTITION domain_xn__y9a3aq;
-- If DETACH fails with "could not find tuple", fallback to catalog-level cleanup:
-- DELETE FROM pg_inherits WHERE inhrelid = 111567;  -- requires allow_system_table_mods=on
-- (use the existing repair_p14 script as template — it handles this fallback)

DROP TABLE IF EXISTS domain_xn__y9a3aq;
COMMIT;

-- Refresh stats and validate catalog
VACUUM ANALYZE domain;
REINDEX TABLE pg_class;
REINDEX TABLE pg_inherits;
```

The next ingestion cycle will recreate `domain_xn__y9a3aq` via `_ensure_partition`.

### Why this fix and not another

- **Why DROP and not catalog patch:** the table likely has < 1MB of data (`xn--y9a3aq` is a small IDN). Recreating from R2 next cycle is faster and safer than mutating system catalogs in production.
- **Why during maintenance window:** any concurrent DDL during the repair re-creates the original race. The 30min window includes pausing `observador-ingestion` stack.

### How to verify

```bash
# 1. Pre-repair: count failures
ssh $SSH_HOST "docker exec \$(docker ps -qf name=observador_postgres | head -1) \
  psql -U obs -d obs -c \"SELECT count(*) FROM ingestion_run \
    WHERE tld='xn--y9a3aq' AND status='failed' \
    AND error_message LIKE '%could not find tuple%';\""
# Baseline: 4

# 2. Run repair (script-based)
ssh $SSH_HOST 'docker exec $(docker ps -qf name=observador_backend | head -1) \
  python -m app.debug_scripts.repair_partition --tld xn--y9a3aq --apply'

# 3. Post-repair: trigger ingestion of just this TLD
curl -X POST "$API_BASE/v1/ingestion/run-now" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -d '{"trigger":"validation_repair_y9a3aq","filter_tlds":["xn--y9a3aq"]}'

# 4. Validate success
ssh $SSH_HOST "docker exec \$(docker ps -qf name=observador_postgres | head -1) \
  psql -U obs -d obs -c \"SELECT status, started_at, finished_at FROM ingestion_run \
    WHERE tld='xn--y9a3aq' ORDER BY started_at DESC LIMIT 1;\""
# Expected: status=success
```

### Rollback

If repair causes broader catalog damage (errors in other partitions afterwards):
1. Restore `pg_class` and `pg_inherits` from the most recent base backup of postgres data dir (`/mnt/data/observador/postgres/base/`).
2. If no recent backup, this becomes a P0 incident — escalate.

**Mitigation:** snapshot `/mnt/data/observador/postgres` via `tar` before running the repair (5GB compressed estimate; <2min on local NVMe).

---

## A2 — CZDS backfill (P3) — 530 TLDs in deficit 🔴

### What to change

Two-phase backfill, **without competing with the 04:00 UTC scheduled cycle**.

**Phase 1 (immediate):** trigger a one-shot CZDS-only run via API (after A4 lands, ideally — but if urgency demands now, accept higher 429 rate as we re-attempt).

**Phase 2 (sustainable):** depends on A3 (scheduler refactor). After A3, the scheduler runs CZDS independently of OpenINTEL crash, so backfill becomes natural over 2–3 cycles.

### Phase 1 procedure

```bash
# 1. Confirm CZDS is enabled and no current CZDS run is active
ssh $SSH_HOST "docker exec \$(docker ps -qf name=observador_postgres | head -1) \
  psql -U obs -d obs -c \"SELECT count(*) FROM ingestion_run \
    WHERE source='czds' AND status='running';\""
# Required: 0

# 2. List TLDs needing backfill
ssh $SSH_HOST "docker exec \$(docker ps -qf name=observador_postgres | head -1) \
  psql -U obs -d obs -c \"\
    SELECT tld FROM ingestion_tld_policy \
    WHERE source='czds' AND enabled=true \
    AND tld NOT IN ( \
      SELECT DISTINCT tld FROM ingestion_run \
      WHERE source='czds' AND status='success' \
      AND finished_at >= NOW() - INTERVAL '7 days' \
    );\""
# Expected: ~530 rows

# 3. Trigger CZDS-only backfill via API (assumes filter_sources support exists)
curl -X POST "$API_BASE/v1/ingestion/run-now" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -d '{"trigger":"manual_czds_backfill","filter_sources":["czds"]}'

# 4. Monitor progress every 10min
watch -n 600 "ssh $SSH_HOST 'docker exec \$(docker ps -qf name=observador_postgres | head -1) \
  psql -U obs -d obs -At -c \"SELECT count(*) FILTER (WHERE status=\\\"success\\\") || \\\"/\\\" || count(*) \
    FROM ingestion_run WHERE source=\\\"czds\\\" AND started_at >= NOW() - INTERVAL \\\"6 hours\\\";\"'"
```

### Why this approach

- **Avoids restarting the worker** — restart cancels any in-progress run.
- **Filter on TLDs needing data** — re-running successful TLDs costs ICANN auth quota for nothing.
- **Phased**: get partial coverage now, structural fix (A3) makes it sustainable.

### Endpoint capability gap

Inspect whether `/run-now` already supports `filter_sources` and `filter_tlds`. If not, this becomes a code change in `backend/app/api/v1/routers/ingestion.py` and `ingestion/scheduler.py`:

```python
# In scheduler.py _run_cycle()
async def _run_cycle(filter_sources: list[str] | None = None,
                     filter_tlds: list[str] | None = None) -> dict:
    sources = [s for s in (openintel_pipeline, czds_pipeline)
               if filter_sources is None or s.source_name in filter_sources]
    for src in sources:
        await _run_source(src, filter_tlds=filter_tlds)
```

### Verification

After backfill completes:
```sql
-- Coverage gain
SELECT count(*) AS still_outdated FROM ingestion_tld_policy p
WHERE source='czds' AND enabled=true
AND NOT EXISTS (SELECT 1 FROM ingestion_run r
  WHERE r.source='czds' AND r.tld=p.tld AND r.status='success'
  AND r.finished_at >= NOW() - INTERVAL '7 days');
-- Goal: < 50 (some TLDs may legitimately have no zone data)
```

### Rollback

Backfill is read-from-CZDS / write-to-DB. If something goes wrong, individual run failures are isolated (one bad TLD doesn't poison others, post-A3). Cancel via SIGTERM on the worker — cycle marks as `interrupted`, but written data persists.

---

## A3 — Scheduler refactor: isolate sources as failure boundaries (P3 root) 🟠

### What to change

**Current (broken) pattern in `ingestion/scheduler.py` ~lines 260–297:**
```python
await _run_source(openintel_pipeline)
if not _stop_event.is_set():           # ← OpenINTEL crash kills CZDS
    await _run_source(czds_pipeline)
```

**Proposed pattern — sources run as parallel tasks with isolated stop events:**
```python
async def _run_cycle(...) -> dict:
    cycle_id = run_recorder.open_cycle(...)
    # SIGTERM still cascades, but per-source failure does NOT cancel the other
    cycle_stop = asyncio.Event()                # global cancel (SIGTERM)
    src_stops = {s.name: asyncio.Event() for s in SOURCES}

    async def _run_one(src):
        try:
            return await _run_source(src, stop_event=cycle_stop)
        except Exception as exc:
            log.exception("source %s crashed: %s", src.name, exc)
            src_stops[src.name].set()
            return {"source": src.name, "status": "failed", "error": str(exc)}

    results = await asyncio.gather(*[_run_one(s) for s in SOURCES],
                                   return_exceptions=False)
    run_recorder.close_cycle(cycle_id, results)
```

Key changes:
1. Use `asyncio.gather(..., return_exceptions=False)` with each task wrapped in its own try/except — exception in one source doesn't propagate to siblings.
2. Single `cycle_stop` event reacts to SIGTERM; per-source events are for internal cancellation only.
3. `close_cycle` aggregates per-source results — cycle status becomes `succeeded` if all succeed, `partial` if some failed but at least one succeeded, `failed` if all failed.

### Why this and not "remove the early-exit guard"

- Removing the `if not _stop_event.is_set()` guard fixes P3 but kills graceful shutdown semantics — SIGTERM during OpenINTEL would still launch CZDS, which is exactly wrong on a deploy.
- Running sources in parallel rather than sequential also reduces total cycle time (~30% expected: OpenINTEL ~30min, CZDS ~30min, parallel ~30min).
- **Risk of parallel:** doubles concurrent DB connections during peak. Need to validate `postgres.max_connections` is sized: current default 100, ingestion uses pool size 5/source × 2 sources = 10. Within budget.

### How to verify

Pre-deploy in staging (or with a feature flag in production):
```bash
# 1. Inject a synthetic crash into openintel_pipeline (test branch only)
# 2. Trigger cycle, expect:
#    - openintel run: status=failed
#    - czds runs: continue and succeed
#    - cycle: status=partial
```

Post-deploy in production:
```sql
-- Day-after check: cycles should be either succeeded or partial, never failed-only
SELECT status, count(*) FROM ingestion_cycle
WHERE started_at >= NOW() - INTERVAL '7 days' GROUP BY 1;
```

### Rollback

Feature-flag the parallel mode behind `INGESTION_PARALLEL_SOURCES=true` env var. If problems, set to `false` and redeploy via `deploy-ingestion.yml`. No DB schema change.

---

## A4 — CZDS auth: session reuse + exponential backoff (P2) 🟠

### What to change

**Current pattern:** `czds_runner.py` calls `authenticate()` per TLD → 1125 auth requests per cycle → 429 wall.

**Proposed:** auth once per cycle (or once per ~23h), cache JWT with `(token, expires_at)`, refresh on 401. Add per-request backoff for transient 429s on download endpoints.

```python
# ingestion/sources/czds_runner.py
from datetime import datetime, timedelta, timezone
import time, random

class CzdsAuthSession:
    """Single JWT cache shared across all TLD downloads in a cycle."""
    _token: str | None = None
    _expires_at: datetime | None = None
    _lock = asyncio.Lock()

    async def get_token(self) -> str:
        async with self._lock:
            if (self._token and self._expires_at
                and self._expires_at > datetime.now(timezone.utc) + timedelta(minutes=5)):
                return self._token
            self._token = await self._authenticate_with_backoff()
            # ICANN JWT validity is ~24h; assume 23h to leave margin
            self._expires_at = datetime.now(timezone.utc) + timedelta(hours=23)
            return self._token

    async def _authenticate_with_backoff(self, max_attempts: int = 5) -> str:
        for attempt in range(max_attempts):
            try:
                resp = await http.post(AUTH_URL, json={...})
                resp.raise_for_status()
                return resp.json()["accessToken"]
            except HttpStatusError as exc:
                if exc.status == 429 and attempt < max_attempts - 1:
                    # Exponential backoff with jitter: 2s, 4s, 8s, 16s + 0–1s jitter
                    delay = (2 ** (attempt + 1)) + random.random()
                    log.warning("CZDS auth 429, backing off %ds", delay)
                    await asyncio.sleep(delay)
                    continue
                raise
        raise RuntimeError("CZDS auth: max attempts exhausted")
```

Wire `CzdsAuthSession` as a cycle-scoped singleton; pass into `_process_tld_local` instead of authenticating inside it.

### Why session reuse, not just backoff

- Backoff alone reduces 429 rate but still issues 1125 auth requests/cycle. Even at 95% success it's 56 retries.
- Session reuse drops auth requests from 1125/cycle to **1/cycle** — algorithmic improvement, not constant-factor.
- Per-request pacing (1s sleep between download requests) is a separate, additional safeguard for the download endpoint (which has its own quota).

### How to verify

```bash
# Count auth requests per cycle from worker logs
ssh $SSH_HOST 'docker service logs observador-ingestion_ingestion_worker --since 24h 2>&1 \
  | grep -c "CZDS auth: token requested"'
# Pre-A4: expect ~1125
# Post-A4: expect 1
```

```sql
-- Count of 429 errors per cycle
SELECT date_trunc('day', started_at) AS day, count(*)
FROM ingestion_run
WHERE source='czds' AND error_message LIKE '%429%'
  AND started_at >= NOW() - INTERVAL '14 days'
GROUP BY 1 ORDER BY 1;
-- Expected: drops to 0 within 1 day of A4 deploy
```

### Rollback

Wrap the new code path behind `CZDS_SESSION_REUSE=true`. If ICANN's JWT semantics turn out to differ from documentation (e.g., shorter validity), set to `false` to revert to per-TLD auth.

---

## A5 — `ch` TLD: profile then fix (P4) 🟠

### What to change

**Phase 1 — Profile (no code change yet):** run `ch` in isolation, instrumented.

```bash
# Trigger ch only, watching mem and timing
TIMEFORMAT='%R seconds'
time curl -X POST "$API_BASE/v1/ingestion/run-now" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -d '{"trigger":"profile_ch","filter_tlds":["ch"],"filter_sources":["openintel"]}'

# In parallel terminal: stream worker memory
ssh $SSH_HOST 'docker stats --format "{{.Container}} {{.MemUsage}}" \
  $(docker ps -qf name=observador-ingestion_ingestion_worker | head -1)' &

# Capture worker logs filtered to ch:
ssh $SSH_HOST 'docker service logs observador-ingestion_ingestion_worker --follow 2>&1 \
  | grep -i " tld=ch "'
```

Profile output goes to `docs/incidents/2026-04-ch-tld-profile.md`. Look for:
- Total wall time
- RSS peak (`mem[end]` rss_kb)
- Time spent in download (R2) vs. parse vs. COPY
- Row count

**Phase 2 — Fix based on profile:**

| If profile shows... | Fix |
|---|---|
| Wall time > 60min, but `domains_inserted` keeps growing | Heartbeat-aware watchdog (only flag stale if `domains_inserted` unchanged for >60min) |
| Wall time > 60min, RSS > 3GB | Streaming chunks (Sprint 2.7) — split download into 100k-row batches |
| Network download > 30min | R2 prefetch / parallel range requests |
| Parse phase dominant | C-extension JSON parser (`orjson`) instead of stdlib |

### Why profile first

The current report has three competing hypotheses for `ch` (network, memory, OID corruption) without data. Each hypothesis has a different fix; deploying the wrong one wastes a sprint. Profile is cheap and disambiguates.

### How to verify (after Phase 2 fix)

```sql
SELECT status, finished_at - started_at AS duration
FROM ingestion_run
WHERE tld='ch' AND source='openintel'
  AND started_at >= NOW() - INTERVAL '7 days'
ORDER BY started_at DESC;
-- Goal: status=success, duration < 30min consistently
```

### Rollback

Phase 1 (profile) has no rollback — read-only. Phase 2 fixes are scoped per-TLD, can be feature-flagged.

---

## A6 — Generic partition repair script (P6 systemic) 🟠

### What to change

Generalize `backend/app/debug_scripts/repair_p14_xn_yfro4i67o.py` into:

```
backend/app/debug_scripts/repair_partition.py
  --tld <tld>           required
  --apply               default: dry-run
  --skip-data-backup    default: backup partition data to S3 before drop
  --reason <text>       written to ops log
```

Steps the script performs (idempotent):
1. Pre-flight: confirm TLD exists in `ingestion_tld_policy`, partition table exists in `pg_class`.
2. Take advisory lock on TLD-specific key to block concurrent DDL.
3. Backup data: `\COPY domain_<tld> TO 's3://.../repairs/domain_<tld>_<ts>.csv'`.
4. Try clean `ALTER TABLE domain DETACH PARTITION ...`.
5. On failure: catalog-level `DELETE FROM pg_inherits WHERE inhrelid=<oid>` (requires `allow_system_table_mods=on`).
6. `DROP TABLE IF EXISTS domain_<tld>`.
7. `REINDEX TABLE pg_class; REINDEX TABLE pg_inherits;`
8. Release advisory lock.
9. Trigger ingestion of just that TLD via internal API.
10. Verify next run succeeds.

### Why centralize this

- P14 (TODO 010) and P6 (this report) are the same class. Each took ~30min of bespoke SQL during incident response.
- Centralized + dry-run + backup makes this a 5-minute on-call action instead of a 30-minute investigation each time.

### How to verify

Run on `xn--y9a3aq` first (A1), then add to runbook `docs/runbooks/ingestion.md` as the canonical recovery path for catalog corruption.

---

## A7 — DDL contention monitoring (P5 early warning) 🟡

### What to change

Add three metrics to the worker (logged in structured format, parseable by anything that ingests log lines):

```python
# In ingestion/provisioning/provision_tld.py
log.info("metric ddl_lock_wait_ms tld=%s wait_ms=%d", tld, wait_ms)
log.info("metric ddl_lock_contention tld=%s contended=%s", tld, "true" if was_contended else "false")
log.info("metric ddl_partition_creation tld=%s phase=%s", tld, "created"/"existed")
```

Add a daily query to the runbook:
```sql
-- Cycles where DDL contention happened
SELECT date_trunc('day', started_at), count(*)
FROM ingestion_run
WHERE error_message LIKE '%tuple concurrently%'
   OR error_message LIKE '%is already a partition%'
GROUP BY 1 ORDER BY 1 DESC;
```

### Why metrics first, not more code defenses

The advisory lock from Sprint 2 should already serialize DDL. The 13 errors on April 27 happened because two cycles overlapped (scheduled + manual `/run-now`). The 409 guard added later closes that hole. So we're betting the design is correct — metrics give early warning if it isn't.

### Verification

Run for 30 days. If `ddl_lock_contention=true` shows up more than ~5 times/cycle, the lock granularity is wrong (likely too coarse — currently per-process instead of per-TLD). Re-investigate.

---

## A8 — OOM watchdog + memory budget alerts (P7 prevention) 🟡

### What to change

Two layers:

**1. Application-level early warning** in `pipeline.py` `_log_mem`:
```python
if rss_kb > 3_500_000:  # 3.5GB of 4GB limit
    log.warning("metric mem_pressure tld=%s rss_kb=%d budget_pct=%.0f",
                tld, rss_kb, rss_kb / 4_000_000 * 100)
```

**2. Container-level OOM detection** as a daily cron in production:
```bash
# /etc/cron.daily/observador-oom-check
docker events --since 24h --until 0s --filter event=oom 2>&1 \
  | grep observador-ingestion \
  | tee -a /var/log/observador-oom.log
# If non-empty, post to ops channel
```

### Why both layers

- App-level: predicts OOM before it happens, allows graceful skip of next TLD.
- Container-level: confirms when OOM actually fires (kernel-level signal not visible inside the container post-mortem).

### Verification

```bash
# Should be empty on a healthy day
ssh $SSH_HOST 'docker events --since 24h --filter event=oom'
# Application warnings: search worker logs for "mem_pressure"
ssh $SSH_HOST 'docker service logs observador-ingestion_ingestion_worker --since 24h 2>&1 | grep mem_pressure'
```

---

## A9 — P1 verification: dashboard query for duplicate-key elimination 🟡

### What to change

Add a recurring check (Grafana panel or daily Slack post via cron):

```sql
-- Last 7 days: count of duplicate-key failures by TLD
SELECT date_trunc('day', started_at) AS day,
       count(*) FILTER (WHERE error_message LIKE '%duplicate key%') AS dup_failures,
       count(*) AS total_failures
FROM ingestion_run
WHERE source='openintel' AND status='failed'
  AND started_at >= NOW() - INTERVAL '7 days'
GROUP BY 1 ORDER BY 1 DESC;
```

**Acceptance criterion for closing P1:**
3 consecutive days with `dup_failures = 0`. Until then, P1 status remains ⚠️ in the evidence report.

### Update the evidence report

Edit `docs/runbooks/ingestion-issues-evidence.md`:
- P1 status: change `✅ Fix deployed (b5cba56)` → `⚠️ Fix deployed, awaiting 3-day clean window`.
- P5 status: change `✅ Mitigated by b5cba56` → `⚠️ Mitigated by b5cba56 + run-now 409 guard, monitored via A7`.

---

## Prioritized timeline (recommended)

```
Today (T+0):
  - A1 catalog repair (30min, maintenance window)
  - A9 verification query (deploy as Grafana panel)

T+1 (next day):
  - Validate 04:00 UTC cycle results
  - If P1 stays clean: keep monitoring per A9
  - If A1 successful: schedule A2 phase 1 (CZDS backfill)

T+2 to T+5 (this week):
  - A4 (CZDS session reuse) — unblocks A2 sustainability
  - A6 (generic repair script)
  - A7 + A8 (observability layer)

T+1 sprint (~2 weeks):
  - A3 (scheduler refactor) — biggest structural fix, gets quality time
  - A5 phase 1 (profile ch)

T+2 sprints:
  - A5 phase 2 (ch fix based on profile)
  - Validate full cycle: 0 P1, 0 P5/P6, CZDS coverage > 95%
```

---

## What I'm explicitly NOT proposing (and why)

1. **Increasing watchdog threshold from 60min to 120min** — masks the symptom (`ch` is too slow) instead of fixing it. A5 attacks the cause.
2. **Adding `ch` to exclusion list** — operational debt with no expiration date. Profile first.
3. **Switching to dedicated CZDS scheduler job (cron)** — splits cycle tracking between two systems. A3 keeps single source of truth (`ingestion_cycle` table) while parallelizing execution.
4. **Forcing FULL_RUN on every CZDS TLD daily** — bandwidth cost ~10× current; ICANN ToS likely violated. A2 phase-2 plus A3 brings us to weekly FULL_RUN per TLD which is the right cadence.
5. **`VACUUM FULL` as catalog repair (P6)** — touches every partition table, hours of downtime. Targeted DROP/recreate (A1) is surgical.
