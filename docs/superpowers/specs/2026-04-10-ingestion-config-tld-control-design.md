# Ingestion Config & TLD Control — Design Spec

**Date:** 2026-04-10  
**Status:** Approved

---

## Context

Currently, ingestion cron schedules are controlled exclusively via environment variables (`CZDS_SYNC_CRON`, `OPENINTEL_SYNC_CRON`, `CT_CRTSH_SYNC_CRON`). Changing a schedule requires a deploy or container restart. TLD control exists only for CZDS (via `czds_tld_policy`); OpenINTEL and CertStream have no TLD filtering.

The goal is to give operators a UI-driven way to:
1. Enable/disable specific TLDs per ingestion source
2. Change cron schedules from the frontend, with immediate effect (no restart)
3. See per-TLD metrics: duration, domains inserted, last successful run, last 10 run statuses

---

## Scope

Sources in scope: **CZDS**, **CertStream**, **OpenINTEL**  
CertStream TLD list is auto-populated from historical `ingestion_run` records; new TLDs default to `is_enabled=true`.

---

## Database Schema

### New table: `ingestion_source_config`

```sql
source          VARCHAR(32)   PRIMARY KEY   -- "czds" | "certstream" | "openintel"
cron_expression VARCHAR(64)   NOT NULL
created_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
updated_at      TIMESTAMPTZ   NOT NULL DEFAULT now()
```

Seeded on migration with current env var values so workers never start with an empty config.  
Env vars remain as fallback if a source has no row.

### New table: `ingestion_tld_policy`

```sql
source      VARCHAR(32)   -- composite PK
tld         VARCHAR(64)   -- composite PK
is_enabled  BOOLEAN       NOT NULL DEFAULT true
updated_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
```

Used by OpenINTEL and CertStream. CZDS continues using `czds_tld_policy` (which has source-specific fields: priority, cooldown_hours, failure_count, etc.).

---

## Backend API

All endpoints require `get_current_admin`.

### Cron config — `/v1/ingestion/config`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/ingestion/config` | List `{source, cron_expression}` for all sources |
| GET | `/v1/ingestion/config/{source}` | Get cron for one source |
| PUT | `/v1/ingestion/config/{source}` | Body: `{cron_expression}` — validates cron syntax before saving |

### Generic TLD policy — `/v1/ingestion/tld-policy`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/ingestion/tld-policy/{source}` | List TLDs with `is_enabled` |
| PATCH | `/v1/ingestion/tld-policy/{source}/{tld}` | Body: `{is_enabled: bool}` |
| PUT | `/v1/ingestion/tld-policy/{source}` | Bulk upsert — sets `is_enabled` for all supplied TLDs; rows not in payload are left unchanged (not deleted) |

### Metrics (reuse existing endpoints)

- `GET /v1/ingestion/runs?source={source}&tld={tld}&limit=10` — last 10 runs per TLD
- `GET /v1/ingestion/checkpoints?source={source}` — last successful run timestamps

The frontend fetches these and builds per-TLD metrics client-side.

### New layers

- `backend/app/repositories/ingestion_config_repository.py` — CRUD for both new tables
- `backend/app/services/ingestion_config_service.py` — cron validation logic
- `backend/app/api/v1/routers/ingestion_config.py` — mounts the above routes

---

## Worker Changes

### Cron reload (czds_ingestor, openintel_ingestor, ct_ingestor)

Workers read cron from `ingestion_source_config` at the start of each cycle. If the value differs from the currently scheduled cron, they reschedule the APScheduler job without restarting. Env var is the fallback if no DB row exists.

```python
# Before scheduling next run:
db_cron = config_repo.get_cron(source) or settings.SOURCE_SYNC_CRON
if db_cron != current_scheduled_cron:
    scheduler.reschedule_job("sync", trigger=CronTrigger.from_crontab(db_cron))
```

**Note on timing:** The new cron takes effect only at the start of the next cycle. For a worker with a long schedule (e.g., 6h), the change may be delayed up to one full cycle. This is acceptable for MVP — no live scheduler signal is implemented.

### TLD filtering — OpenINTEL

Before processing each TLD in a cycle, checks `ingestion_tld_policy.is_enabled`. Disabled TLDs are skipped (same behavior as `czds_tld_policy.is_enabled`).

### TLD filtering — CertStream

After extracting the TLD from each certificate domain:
- If no row exists in `ingestion_tld_policy`: inserts with `is_enabled=true` and processes
- If `is_enabled=false`: discards the domain without inserting

### CZDS

No changes to TLD filtering — continues using `czds_tld_policy`.

---

## Frontend

### New routes

```
frontend/app/admin/ingestion/
├── page.tsx               ← updated: adds 3 source cards
└── [source]/
    └── page.tsx           ← new: /ingestion/czds | /ingestion/openintel | /ingestion/certstream
```

### New components

```
frontend/components/ingestion/
├── source-config-page.tsx    ← main component, reused by all 3 sources
├── cron-config-card.tsx      ← cron input + validation + save
├── tld-metrics-table.tsx     ← table: toggle, TLD name, duration, inserted, last OK, sparkbar
└── sparkbar.tsx              ← 10 vertical bars: color=status, height=duration
```

### Updated files

- `frontend/app/admin/ingestion/page.tsx` — adds 3 source summary cards (name, status, cron preview, active TLD count, "Configurar →" link)
- `frontend/hooks/use-ingestion-data.ts` — adds actions: `updateCron`, `patchTldPolicy`, `bulkSetTldPolicy`

### TLD metrics table columns

| Column | Source |
|--------|--------|
| TLD | `ingestion_tld_policy` (or `czds_tld_policy` for CZDS) |
| Ativo (toggle) | `is_enabled` field |
| Duração | `finished_at - started_at` from last run |
| Inseridos | `domains_inserted` from last run |
| Última OK | `last_successful_run_at` from `ingestion_checkpoint` |
| Últimas 10 | Last 10 `ingestion_run` rows — sparkbar: green=success, red=failed, height ∝ duration |

### Sparkbar behavior

- Bars ordered oldest→newest (left→right)
- Height normalized relative to the max duration in the set
- Missing slots (fewer than 10 runs) shown as short gray bars
- Tooltip on hover: `{date} — {status} — {duration} — {domains_inserted}`

---

## Verification

1. Apply migration → confirm both tables exist and are seeded with env var values
2. Change cron via `PUT /v1/ingestion/config/openintel` → verify worker reschedules on next cycle without restart
3. Disable a TLD via `PATCH /v1/ingestion/tld-policy/openintel/br` → verify next OpenINTEL cycle skips `.br`
4. Disable a TLD via CertStream policy → verify `.fr` certificates are discarded in the next flush
5. Frontend: navigate to `/admin/ingestion/openintel` → confirm cron card, TLD table, sparkbars render with real data
6. Toggle a TLD in UI → verify PATCH fires and row updates optimistically
