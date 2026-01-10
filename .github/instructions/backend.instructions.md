# BACKEND ENGINEERING INSTRUCTIONS (PYTHON / FASTAPI)

This file defines **mandatory backend engineering rules** for agent code (LLMs).
All backend code must follow these instructions when creating or modifying features.

Target stack:
- Python 3.12+
- FastAPI
- PostgreSQL
- SQLAlchemy ORM
- Alembic
- Pydantic v2

---

## 1. CORE PRINCIPLE

❗ **Architecture and structure come before implementation.**

Before writing any code, the agent must reason about:
- domain boundaries
- responsibility of each layer
- data flow
- ownership of business rules

The backend must prioritize:
- clarity
- maintainability
- predictable evolution

---

## 2. ARCHITECTURE STYLE

Use a **Domain-Oriented, Layered Architecture**.

### Mandatory layers
```

api            → HTTP / FastAPI layer
domain         → business concepts and rules
services       → use cases and orchestration
repositories   → data access abstraction
models         → SQLAlchemy ORM models
schemas        → Pydantic input/output schemas
infra          → database, cache, external services
core           → configuration, logging, security

````

❌ Do not collapse layers  
❌ Do not mix responsibilities  

---

## 3. PROJECT STRUCTURE (RECOMMENDED)

```text
app/
├── api/
│   ├── v1/
│   │   ├── routers/
│   │   └── dependencies.py
│
├── domain/
│   ├── entities/
│   ├── value_objects/
│   └── enums/
│
├── services/
│   └── use_cases/
│
├── repositories/
│   ├── interfaces.py
│   └── sqlalchemy/
│
├── models/
├── schemas/
├── infra/
│   ├── db/
│   ├── cache/
│   └── external/
│
├── core/
│   ├── config.py
│   ├── logging.py
│   └── security.py
│
├── migrations/
└── main.py
````

---

## 4. RESPONSIBILITY RULES

### API Layer

* HTTP concerns only
* Request/response handling
* Authentication and authorization
* No business logic

### Services (Use Cases)

* Business rules
* Orchestration
* Transactions
* Cross-entity coordination

### Repositories

* Database access only
* Query logic
* No business rules
* No commits

### ORM Models

* Persistence mapping only
* No service calls
* No orchestration logic

---

## 5. FASTAPI BEST PRACTICES

* Use `APIRouter` per domain
* Version APIs (`/v1`)
* Use dependency injection (`Depends`)
* Explicit response models
* Thin route handlers

✔

```python
@router.post("/", response_model=DomainOut)
def create_domain(
    payload: DomainCreate,
    service: DomainService = Depends()
):
    return service.create(payload)
```

❌ No logic in routes

---

## 6. PYDANTIC (SCHEMA) RULES

* Separate input and output schemas
* Never reuse ORM models as schemas
* Explicit optional fields
* No hidden defaults

✔

```python
class DomainCreate(BaseModel):
    name: str

class DomainOut(BaseModel):
    id: UUID
    name: str
```

---

## 7. SQLALCHEMY RULES

* One model per file
* Explicit columns and constraints
* Explicit relationships
* Predictable behavior

✔

```python
class Domain(Base):
    __tablename__ = "domains"
```

❌ No magic fields
❌ No dynamic table names

---

## 8. TRANSACTIONS & SESSIONS

* Transactions handled in services
* Repositories must never commit
* One transaction per use case

✔

```python
with session.begin():
    service.execute()
```

---

## 9. ERROR HANDLING

* Use explicit domain exceptions
* Map exceptions to HTTP responses in API layer
* Never expose raw database errors

✔

```python
class DomainAlreadyExists(Exception):
    pass
```

---

## 10. VALIDATION STRATEGY

* Input validation → Pydantic
* Business validation → services/domain
* Database constraints as final safeguard

❌ Do not rely only on DB constraints

---

## 11. LOGGING

* Structured logging
* Correlation/request IDs
* No sensitive data in logs

Log:

* state changes
* failures
* external interactions

---

## 12. TESTING POLICY (EXPLICIT)

⚠️ **Unit tests are NOT required in this project.**

### Guidelines

* Do not block feature delivery due to missing unit tests
* Focus on correctness, clarity, and structure
* Prefer simple manual validation or integration testing when needed
* Code must still be clean, readable, and deterministic

---

## 13. FEATURE EVOLUTION CHECKLIST

Whenever a feature is added or modified:

```
[ ] Domain identified
[ ] Use case/service updated or created
[ ] Repository reviewed
[ ] Schemas updated
[ ] API version respected
[ ] Database impact evaluated
```

---

## 14. ANTI-PATTERNS (FORBIDDEN)

* Fat controllers
* Business logic in routes
* ORM models used as DTOs
* Direct DB access outside repositories
* Circular dependencies
* God services

---

## 15. AGENT EXPECTATION

The agent must:

* follow the existing structure
* favor readability over cleverness
* request refactors instead of shortcuts
* explicitly justify deviations from these rules

---

## 16. FINAL RULE

> Code is read far more than it is written.

Optimize for **clarity, structure, and long-term maintainability**.