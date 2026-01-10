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
│   ├── app/                # Next.js App Router
│   ├── components/         # UI components (Geist + shadcn + Magic UI)
│   ├── lib/                # Helpers, hooks, utils
│   ├── styles/             # Global styles and tokens
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
│   ├── stack.yml            # Docker Swarm stack
│   └── env/                 # Environment files
│
├── .github/
│   └── workflows/
│       └── deploy.yml       # CI/CD pipeline
│
└── AGENT.md

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
```