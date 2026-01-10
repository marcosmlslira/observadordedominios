
# MODELING INSTRUCTIONS (DOMAIN + DATABASE)

This file defines **mandatory rules** for domain analysis and database modeling.
Every agent code (LLM) **MUST** follow these instructions whenever a feature is added or modified.

Target stack:
- FastAPI
- Python
- PostgreSQL
- SQLAlchemy ORM
- Alembic

---

## 1. CORE PRINCIPLE

❗ **Never write code before modeling the domain and the data.**

Before generating:
- ORM models
- database migrations
- Pydantic schemas
- API endpoints

The agent **MUST FIRST** reason about:
- domain boundaries
- entity ownership
- data lifecycle
- temporal behavior
- multi-tenancy impact

---

## 2. DOMAIN IDENTIFICATION (MANDATORY)

Before creating or changing any table, explicitly identify:

```

Domain:
Subdomain:
Primary responsibility:

```

### Rules
- ❌ Never mix multiple domains in the same table
- ✅ A domain may have multiple tables
- ❌ A table must not serve multiple domains

### Example domains
- identity (users, authentication, roles)
- organizations (companies, teams, invitations)
- billing (plans, invoices, payments)
- monitoring (domains, uptime, blacklist, ssl)
- notifications (alerts, channels, deliveries)
- audit (events, logs, trails)

---

## 3. TABLE CLASSIFICATION

Before creating a table, classify it as:

| Type | Description |
|----|----|
| Entity | Has identity and lifecycle |
| Relationship | Connects two entities |
| Event | Something that happened in time (append-only) |
| Snapshot | State captured at a point in time |
| Configuration | Preference or rule |

### Examples
- `domain` → Entity
- `domain_blacklist_event` → Event
- `domain_uptime_snapshot` → Snapshot
- `domain_monitoring_settings` → Configuration

---

## 4. OWNERSHIP & RESPONSIBILITY

Every entity must have a **single owner**:

- One domain owns the data
- Other domains may only reference it
- Cross-domain writes are forbidden

---

## 5. NAMING RULES (STRICT)

### Tables
- `snake_case`
- singular
- explicit names
- domain prefix when needed

✔ `domain_monitoring`  
❌ `domains_data`  
❌ `monitoring_table`

### Columns
- No abbreviations
- No generic names
- Must be self-descriptive

✔ `checked_at`  
❌ `dt`  
❌ `data`  
❌ `info`

---

## 6. TEMPORAL MODELING (CRITICAL)

Every entity must answer:

- Does this data change over time?
- Is historical tracking required?
- Do we need to know when it was valid?

### Rules
- Events → append-only tables
- Mutable state → historical or versioned tables
- Configuration → consider `valid_from` / `valid_to`

### Standard columns
- `created_at`
- `updated_at`
- `deleted_at` (soft delete when applicable)

---

## 7. MULTI-TENANCY (ALWAYS EVALUATE)

Before creating a table, explicitly decide:

```

Ownership level:
[ ] System
[ ] Organization
[ ] User
[ ] Shared

````

### Rule
- Any customer-domain table **MUST include**:
```sql
organization_id
````

### Exceptions

* global reference tables
* static catalogs
* system-level enums

---

## 8. NORMALIZATION WITH INTENT

### Default

* Third Normal Form as baseline
* Denormalization only when:

  * read-heavy
  * performance-critical
  * explicitly justified

### JSONB usage

❌ Never as a modeling shortcut
✔ Allowed only for:

* technical metadata
* raw external payloads
* logs

---

## 9. RELATIONSHIPS & FOREIGN KEYS

### Mandatory rules

* All relationships must be enforced by FKs
* `ondelete` behavior must be explicit
* Bidirectional ORM relationships only when needed

✔

```python
ForeignKey("domains.id", ondelete="CASCADE")
```

❌

```python
ForeignKey("domains.id")
```

---

## 10. INDEXING STRATEGY

Before creating an index, answer:

* Is it used for filtering?
* Is it used for ordering?
* Is it required for joins?

### Rules

* Index foreign keys by default
* Composite indexes must reflect real queries
* Avoid speculative indexes

---

## 11. MIGRATIONS (ALEMBIC)

Every schema change must answer:

* Is it backward compatible?
* Does it require data backfill?
* Can it break production?

### Rules

* ❌ Never modify applied migrations
* ✅ Always create a new migration
* ✅ Migrations must be isolated from business logic
* ✅ Existing data must be preserved

---

## 12. FEATURE EVOLUTION CHECKLIST

Whenever a feature is added or modified:

```
[ ] Domain identified
[ ] Entity ownership defined
[ ] Temporal impact analyzed
[ ] Multi-tenancy validated
[ ] Naming rules respected
[ ] Relationships clarified
[ ] Migration created
[ ] Indexes reviewed
```

---

## 13. ANTI-PATTERNS (FORBIDDEN)

* Catch-all tables
* Generic columns (`data`, `info`, `extra`)
* Implicit relationships (no FK)
* JSONB as primary model
* Persisted calculated values without justification
* Business rules inside the database

---

## 14. MINIMUM DOCUMENTATION PER TABLE

Every new table must be documented with:

```
Responsibility:
Domain:
Who writes:
Who reads:
Expected volume:
Growth expectations:
```

---

## 15. AGENT BEHAVIOR EXPECTATION

The agent code must:

* Model before coding
* Think in domains, not CRUD
* Prefer safe evolution over shortcuts
* Question destructive changes
* Explicitly justify any rule violation

---

## 16. FINAL RULE

> Code can be refactored.
> Database design is permanent.

Correct modeling is **mandatory**