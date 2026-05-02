# AGENT INSTRUCTIONS

## Project
- Type: Monorepo
- Frontend and backend isolated
- Communication via HTTP (REST)
- Independent build and runtime per service

## Project Structure
```
/
├── frontend/
│   ├── app/                 # Next.js App Router
│   ├── components/          # UI components (Geist + shadcn + Magic UI)
│   ├── lib/                 # Helpers, hooks, utils
│   ├── styles/              # Global styles and tokens
│   ├── public/
│   ├── package.json
│   ├── next.config.js
│   └── Dockerfile
│
├── backend/
│   ├── app/
│   │   ├── api/             # Routes/controllers
│   │   ├── core/            # Config, settings, security
│   │   ├── models/          # ORM models
│   │   ├── schemas/         # Pydantic schemas
│   │   ├── services/        # Business logic
│   │   ├── repositories/    # Data access
│   │   └── main.py
│   ├── tests/
│   ├── alembic/             # DB migrations
│   ├── pyproject.toml
│   └── Dockerfile
│
├── infra/
│   ├── stack.yml             # Docker Swarm stack
│   └── env/                  # Environment files
│
├── .agents/
│   ├── skills/               # Extensible agent skills
│   │   ├── architecture-blueprint-generator/
│   │   ├── chrome-devtools/
│   │   ├── database-modeling/
│   │   ├── email-best-practices/
│   │   ├── fastapi-templates/
│   │   ├── front-end-responsive/
│   │   ├── interface-design/
│   │   ├── next-best-practices/
│   │   ├── next-upgrade/
│   │   ├── nextjs-micro-ux-expert/
│   │   ├── react-email/
│   │   ├── resend/
│   │   ├── responsive-design-expert/
│   │   ├── stripe-best-practices/
│   │   └── upgrade-stripe/
│   └── workflows/            # Automated agent workflows
│
├── .github/
│   ├── agents/               # Custom GitHub Copilot agents
│   │   ├── AGENT-tech-refiner.md
│   │   ├── arch.agent.md
│   │   ├── debug.agent.md
│   │   ├── devops-expert.agent.md
│   │   ├── expert-nextjs-developer.agent.md
│   │   ├── postgresql-dba.agent.md
│   │   ├── prd.agent.md
│   │   ├── principal-software-engineer.agent.md
│   │   └── python-mcp-expert.agent.md
│   ├── instructions/         # Contextual instructions for agents
│   │   ├── backend.instructions.md
│   │   ├── frontend.instructions.md
│   │   └── modeling.instructions.md
│   ├── prompts/              # Reusable prompt templates
│   │   ├── especification.md
│   │   ├── execution.md
│   │   ├── frontend-implement.md.example
│   │   └── planning.md
│   ├── skills/               # Shared skills (mirrors .agents/skills)
│   ├── workflows/            # GitHub Actions CI/CD pipelines
│   └── copilot-instructions.md
│
├── .specs/
│   ├── product_definition.md # Core product definition
│   ├── features/             # Feature PRDs (Product Requirements)
│   │   ├── auth/
│   │   │   ├── prd_auth_simples.md
│   │   │   └── prd_sso.md
│   │   ├── domain-database/
│   │   │   └── prd.md
│   │   ├── domain_similarity/
│   │   ├── freetools/
│   │   │   ├── prd.md
│   │   │   ├── prd_dns_lookup.md
│   │   │   ├── prd_pagina_suspeita.md
│   │   │   ├── prd_screenshot.md
│   │   │   ├── prd_ssl_check.md
│   │   │   └── prd_whois.md
│   │   ├── notifications/
│   │   ├── payment/
│   │   │   └── pagameto.md
│   │   ├── ssl_monitoring/
│   │   └── uptime_monitoring/
│   ├── setup_project/        # Initial project setup guides
│   │   ├── 001-frontend-desgin.md
│   │   ├── 002-ambiente-docker.md
│   │   ├── 003-make-file.md
│   │   └── 004-page-design-system.md
│   └── todos/                # Task tracking
│       ├── README.md
│       ├── _registry.md
│       ├── 001/
│       │   ├── plan.md
│       │   ├── references.md
│       │   └── status.md
│       ├── 002/
│       │   ├── plan.md
│       │   ├── references.md
│       │   └── status.md
│       └── 003/
│           ├── plan.md
│           ├── references.md
│           └── status.md
│
└── AGENTS.md
```

## Frontend
- Framework: Next.js (latest)
- Router: App Router
- Language: TypeScript
- Default: Server Components
- Client Components only when required

### Design System (priority order)
1. Geist (typography, spacing, tokens)
2. shadcn/ui (structural components)
3. Magic UI (animations and visual components)

- Tailwind CSS: utility-only
- Responsive: mobile-first

### Forbidden
- Material UI
- Ant Design
- Chakra UI
- Bootstrap
- Pages Router

## Backend
- Language: Python (latest)
- Framework: FastAPI
- Database: PostgreSQL (latest)

### Architecture Rules
- Separate: api, services, repositories, models, schemas
- No business logic in routes
- Typed with Pydantic
- Required endpoint: `GET /health`

## Infrastructure
- Containerization: Docker
- Mode: warm
- Orchestration: Docker Swarm
- Deploy: `docker stack deploy`
- docker-compose: forbidden

## CI/CD
- Provider: GitHub Actions
- Registry: AWS ECR
- Image tags: versioned only (no `latest`)
- Secrets via GitHub Secrets

## Agent Rules
- Do not add libraries outside this stack
- Do not change design system
- Do not use docker-compose
- Do not mix responsibilities
- Prefer clarity and maintainability

## Production Access / Ingestion Ops
- SSH access to production is allowed without password for this host/user:
  - `ubuntu@158.69.211.109`
- Preferred non-interactive SSH flags:
  - `ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new ubuntu@158.69.211.109 "<command>"`
- For ingestion validation, always use existing API endpoints (never insert manual DB records):
  - `POST /v1/ingestion/trigger/daily-cycle`
  - `GET /v1/ingestion/cycle-status`
  - `GET /v1/ingestion/cycles`
  - `GET /v1/ingestion/runs?status=running`
  - `GET /health`
- Swarm service names relevant to ingestion:
  - `observador-ingestion_ingestion_worker`
- Legacy CT services must not be restarted or recreated:
  - `observador_ct_ingestor`
  - `observador_certstream_server`
- Production source of truth for the app stack is:
  - `C:\PROJETOS\docker-stack-infra\stacks\observador.yml`
- Production source of truth for the isolated ingestion stack is:
  - `C:\PROJETOS\docker-stack-infra\stacks\observador-ingestion.yml`
- If trigger returns `already_running`, confirm real execution with `runs?status=running` and latest `cycles`.
  - If there are no running rows and no new cycle, treat as inconsistent worker state.
- `observador_ct_ingestor` is legacy and removed from the current backend source tree.
  - If it appears in production again, remove it from Swarm and fix the deploy source instead of restoring the module.
