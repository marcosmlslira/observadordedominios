# Production Deploy Design — Observador de Domínios

**Date**: 2026-03-22
**Status**: Approved

## Overview

Deploy the Observador de Domínios application to production using the existing Docker Swarm infrastructure in `docker-stack-infra`, following the Shalem deployment pattern (GHCR images, Traefik routing, Docker Swarm stacks). Production uses Cloudflare R2 instead of local MinIO for S3-compatible object storage.

## Architecture

```
observadordedominios repo          docker-stack-infra repo
┌──────────────────────┐          ┌─────────────────────────┐
│ push to main         │          │ push to main            │
│   ↓                  │          │   ↓                     │
│ detect changes:      │          │ deploy ALL stacks       │
│  backend/** →        │          │                         │
│    build+push backend│          │ repository_dispatch     │
│  frontend/** →       │          │   ↓                     │
│    build+push frontend          │ deploy ONLY specified   │
│   ↓                  │  trigger │ stack                   │
│ repository_dispatch  │ ───────→ │                         │
└──────────────────────┘          └─────────────────────────┘
```

## Selective Build & Deploy

### Build (observadordedominios repo)

Workflow `.github/workflows/build-push.yml`:

1. On push to `main`, detect changed paths using `dorny/paths-filter` action:
   - `backend/**` → build `ghcr.io/{owner}/observador-backend:latest`
   - `frontend/**` → build `ghcr.io/{owner}/observador-frontend:latest`
2. Push only changed images to GHCR
3. Trigger `repository_dispatch` on `docker-stack-infra` with payload:
   ```json
   { "event_type": "deploy-stack", "client_payload": { "stack": "observador" } }
   ```

**Cross-repo dispatch token**: Requires a GitHub Secret `INFRA_DISPATCH_TOKEN` on the `observadordedominios` repo — a PAT with `repo` scope on `docker-stack-infra`. The existing `GHCR_TOKEN` does not have this scope.

### Deploy (docker-stack-infra repo)

Modify `.github/workflows/deploy.yml`:

- **On `push` to main**: full deploy (infra + all app stacks) — current behavior preserved
- **On `repository_dispatch`**: deploy ONLY the specified stack
  - Conditional steps: `if: github.event_name != 'repository_dispatch'` on infra steps
  - Shared steps (SSH, Docker context, GHCR login, rsync) always run
  - App stack deploy step: on dispatch, only deploy the target stack from `client_payload.stack`

## Production Stack (observador.yml)

### Services

| Service | Image | Port | Network |
|---|---|---|---|
| postgres | postgres:16-alpine | 5432 (internal) | internal |
| backend | ghcr.io/{owner}/observador-backend:latest | 8000 | internal + traefik-public |
| frontend | ghcr.io/{owner}/observador-frontend:latest | 3000 | internal + traefik-public |
| czds_ingestor | ghcr.io/{owner}/observador-backend:latest | — | internal |
| similarity_worker | ghcr.io/{owner}/observador-backend:latest | — | internal |

### Traefik Routing

All router names are prefixed with `observador-` to avoid collisions with other stacks.

| Domain | Router name | Target |
|---|---|---|
| `observadordedominios.com.br` | `observador-frontend` | frontend:3000 |
| `www.observadordedominios.com.br` | `observador-www` | redirect → `observadordedominios.com.br` |
| `api.observadordedominios.com.br` | `observador-backend` | backend:8000 |

All routes use `websecure` entrypoint with Cloudflare DNS challenge (`certresolver=cf`).

**Middleware**: www redirect uses `observador-www-redirect` (unique name to avoid collision with Shalem's `www-redirect`).

**Health checks** (Traefik):
- Frontend: `healthcheck.path=/api/health`, interval 10s, timeout 3s
- Backend: `healthcheck.path=/api/health`, interval 10s, timeout 3s

### Environment Variables

**Backend + Workers (shared)**:
```
ENVIRONMENT=production
DATABASE_URL=postgresql://obs:${OBSERVADOR_POSTGRES_PASSWORD}@postgres:5432/obs
S3_BUCKET=observadordedominios
S3_REGION=auto
S3_ENDPOINT_URL=https://c7d69182e6ae8686a3edc7bdd6eae9f8.r2.cloudflarestorage.com
S3_ACCESS_KEY_ID=${OBSERVADOR_R2_ACCESS_KEY_ID}
S3_SECRET_ACCESS_KEY=${OBSERVADOR_R2_SECRET_ACCESS_KEY}
S3_FORCE_PATH_STYLE=true
CZDS_USERNAME=${OBSERVADOR_CZDS_USERNAME}
CZDS_PASSWORD=${OBSERVADOR_CZDS_PASSWORD}
CZDS_ENABLED_TLDS=net,org,info
CZDS_SYNC_CRON=0 7 * * *
CZDS_BASE_URL=https://czds-api.icann.org
```

**Frontend**:
```
NODE_ENV=production
NEXT_PUBLIC_API_URL=https://api.observadordedominios.com.br
HOSTNAME=0.0.0.0
PORT=3000
```

**Postgres**:
```
POSTGRES_USER=obs
POSTGRES_PASSWORD=${OBSERVADOR_POSTGRES_PASSWORD}
POSTGRES_DB=obs
```

### Storage — Cloudflare R2

- **Bucket**: `observadordedominios` (note: differs from dev default `observador-zones` — the `S3_BUCKET` env var overrides the config default)
- **Endpoint**: `https://c7d69182e6ae8686a3edc7bdd6eae9f8.r2.cloudflarestorage.com`
- **Access**: S3-compatible via boto3
- `S3_FORCE_PATH_STYLE=true`
- `S3_REGION=auto` (R2 convention)

### Workers

Both workers reuse the backend image with command overrides:
- `czds_ingestor`: `python -m app.worker.czds_ingestor`
- `similarity_worker`: `python -m app.worker.similarity_worker`

Both share the same environment variables as the backend.

### Deploy Config

All services follow the Shalem pattern:
```yaml
update_config:
  order: start-first
  parallelism: 1
  delay: 10s
restart_policy:
  condition: on-failure
  delay: 5s
  max_attempts: 3
```

### Database Migrations

Alembic migrations run at backend container startup. The backend `Dockerfile` CMD runs uvicorn; migrations should be executed as part of the entrypoint or as a pre-start step. Implementation will add an entrypoint script that runs `alembic upgrade head` before starting uvicorn.

### Image Validation

The deploy workflow will validate observador images exist on GHCR before deploying (same pattern as Shalem's `shalem_images` step). If images are missing, the observador stack deploy is skipped with a warning.

## Credentials

All credentials stored as GitHub Secrets, injected as environment variables in the deploy workflow step.

**On `docker-stack-infra` repo** (used during deploy):

| GitHub Secret | Stack env var | Service |
|---|---|---|
| `OBSERVADOR_POSTGRES_PASSWORD` | `POSTGRES_PASSWORD` / `DATABASE_URL` | postgres, backend, workers |
| `OBSERVADOR_R2_ACCESS_KEY_ID` | `S3_ACCESS_KEY_ID` | backend, workers |
| `OBSERVADOR_R2_SECRET_ACCESS_KEY` | `S3_SECRET_ACCESS_KEY` | backend, workers |
| `OBSERVADOR_CZDS_USERNAME` | `CZDS_USERNAME` | workers |
| `OBSERVADOR_CZDS_PASSWORD` | `CZDS_PASSWORD` | workers |

**On `observadordedominios` repo** (used during build + dispatch):

| GitHub Secret/Variable | Purpose |
|---|---|
| `GHCR_TOKEN` | Push images to GHCR |
| `GHCR_OWNER` (variable) | GHCR namespace |
| `INFRA_DISPATCH_TOKEN` | **New** — PAT with `repo` scope to trigger dispatch on docker-stack-infra |

## Files to Create/Modify

| Repo | File | Action |
|---|---|---|
| `observadordedominios` | `.github/workflows/build-push.yml` | **Create** — selective build, GHCR push, dispatch |
| `docker-stack-infra` | `stacks/observador.yml` | **Replace** (currently whoami placeholder) |
| `docker-stack-infra` | `.github/workflows/deploy.yml` | **Modify** — add `repository_dispatch` trigger + selective deploy + observador image validation |

## Volumes

| Volume | Purpose |
|---|---|
| `observador-postgres-data` | PostgreSQL data persistence |

## Networks

- `traefik-public` (external) — shared with Traefik
- `internal` (overlay, attachable) — inter-service communication
