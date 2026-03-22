# Production Deploy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy Observador de Domínios to production on the existing Docker Swarm infrastructure with selective CI/CD and Cloudflare R2 storage.

**Architecture:** Two-repo CI/CD — `observadordedominios` builds and pushes images to GHCR, then triggers `repository_dispatch` on `docker-stack-infra` which deploys only the observador stack. Production replaces MinIO with Cloudflare R2 via S3-compatible env vars.

**Tech Stack:** GitHub Actions, Docker Swarm, GHCR, Traefik v3, Cloudflare R2, PostgreSQL 16, FastAPI, Next.js 15

**Spec:** `docs/superpowers/specs/2026-03-22-production-deploy-design.md`

---

## File Structure

### Files to Create

| File | Responsibility |
|---|---|
| `observadordedominios/.github/workflows/build-push.yml` | Selective build + GHCR push + dispatch |
| `observadordedominios/backend/entrypoint.sh` | Wait for postgres, run alembic migrations, then start uvicorn |
| `observadordedominios/frontend/app/api/health/route.ts` | Frontend health check endpoint for Traefik |

### Files to Modify

| File | Change |
|---|---|
| `observadordedominios/frontend/next.config.js` | Enable `output: 'standalone'` (required by Dockerfile) |
| `observadordedominios/backend/Dockerfile` | Generate `poetry.lock`, copy `entrypoint.sh`, use as ENTRYPOINT, `--only main` |
| `observadordedominios/backend/.dockerignore` | Remove `poetry.lock` exclusion |
| `docker-stack-infra/stacks/observador.yml` | Replace whoami with full production stack |
| `docker-stack-infra/.github/workflows/deploy.yml` | Add `repository_dispatch` + selective deploy + observador image validation |

---

## Task 1: Fix frontend build for production

The Dockerfile expects `output: 'standalone'` but it's commented out in `next.config.js`. Also needs a health check endpoint for Traefik.

**Files:**
- Modify: `observadordedominios/frontend/next.config.js`
- Create: `observadordedominios/frontend/app/api/health/route.ts`

- [ ] **Step 1: Enable standalone output**

In `frontend/next.config.js`, uncomment and enable standalone:

```js
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
}

module.exports = nextConfig
```

- [ ] **Step 2: Create frontend health endpoint**

Create `frontend/app/api/health/route.ts`:

```ts
export async function GET() {
  return Response.json({ status: "ok" });
}
```

- [ ] **Step 3: Verify frontend builds locally**

Run: `cd frontend && npm run build`
Expected: `.next/standalone` directory is created.

- [ ] **Step 4: Commit**

```bash
git add frontend/next.config.js frontend/app/api/health/route.ts
git commit -m "build: enable standalone output and add health endpoint for production"
```

---

## Task 2: Add backend entrypoint with migrations

The backend needs to run `alembic upgrade head` before starting uvicorn in production.

**Files:**
- Create: `observadordedominios/backend/entrypoint.sh`
- Modify: `observadordedominios/backend/Dockerfile`

- [ ] **Step 1: Generate poetry.lock and fix .dockerignore**

```bash
cd backend
poetry lock
```

Then remove the `poetry.lock` line from `backend/.dockerignore` so it's included in the Docker build context.

- [ ] **Step 2: Create entrypoint script**

Create `backend/entrypoint.sh`:

```bash
#!/bin/bash
set -e

# Wait for postgres to be ready
echo "Waiting for postgres..."
while ! python -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.connect(('postgres', 5432))
    s.close()
    exit(0)
except:
    exit(1)
" 2>/dev/null; do
  sleep 2
done
echo "Postgres is ready."

echo "Running database migrations..."
alembic upgrade head

echo "Starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 3: Update Dockerfile**

Replace `backend/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install poetry

COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false && poetry install --no-root --no-interaction --no-ansi --only main

COPY . .

RUN chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
```

Note: Uses `--only main` to exclude dev dependencies from the production image.

- [ ] **Step 4: Commit**

```bash
git add backend/entrypoint.sh backend/Dockerfile backend/.dockerignore backend/poetry.lock
git commit -m "build: add entrypoint with postgres wait + alembic migrations for production"
```

---

## Task 3: Create build-push workflow (observadordedominios)

**Files:**
- Create: `observadordedominios/.github/workflows/build-push.yml`

- [ ] **Step 1: Create the workflow file**

Create `.github/workflows/build-push.yml`:

```yaml
name: Build & Push Images

on:
  push:
    branches: [main]
  workflow_dispatch:

concurrency:
  group: build-push
  cancel-in-progress: true

env:
  GHCR_REGISTRY: ghcr.io
  GHCR_OWNER: ${{ vars.GHCR_OWNER }}

jobs:
  detect-changes:
    runs-on: ubuntu-latest
    outputs:
      backend: ${{ steps.filter.outputs.backend }}
      frontend: ${{ steps.filter.outputs.frontend }}
    steps:
      - uses: actions/checkout@v4
      - uses: dorny/paths-filter@v3
        id: filter
        with:
          filters: |
            backend:
              - 'backend/**'
            frontend:
              - 'frontend/**'

  build-backend:
    needs: detect-changes
    if: needs.detect-changes.outputs.backend == 'true' || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    permissions:
      packages: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - name: Login to GHCR
        run: echo "${{ secrets.GHCR_TOKEN }}" | docker login "$GHCR_REGISTRY" --username "$GHCR_OWNER" --password-stdin
      - name: Build and push backend
        run: |
          IMAGE="$GHCR_REGISTRY/$GHCR_OWNER/observador-backend:latest"
          docker build -t "$IMAGE" backend/
          docker push "$IMAGE"

  build-frontend:
    needs: detect-changes
    if: needs.detect-changes.outputs.frontend == 'true' || github.event_name == 'workflow_dispatch'
    runs-on: ubuntu-latest
    permissions:
      packages: write
      contents: read
    steps:
      - uses: actions/checkout@v4
      - name: Login to GHCR
        run: echo "${{ secrets.GHCR_TOKEN }}" | docker login "$GHCR_REGISTRY" --username "$GHCR_OWNER" --password-stdin
      - name: Build and push frontend
        run: |
          IMAGE="$GHCR_REGISTRY/$GHCR_OWNER/observador-frontend:latest"
          docker build -t "$IMAGE" frontend/
          docker push "$IMAGE"

  trigger-deploy:
    needs: [build-backend, build-frontend]
    if: always() && (needs.build-backend.result == 'success' || needs.build-frontend.result == 'success')
    runs-on: ubuntu-latest
    steps:
      - name: Trigger deploy on docker-stack-infra
        run: |
          curl -X POST \
            -H "Accept: application/vnd.github+json" \
            -H "Authorization: Bearer ${{ secrets.INFRA_DISPATCH_TOKEN }}" \
            https://api.github.com/repos/${{ vars.GHCR_OWNER }}/docker-stack-infra/dispatches \
            -d '{"event_type":"deploy-stack","client_payload":{"stack":"observador"}}'
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/build-push.yml
git commit -m "ci: add selective build-push workflow with GHCR and infra dispatch"
```

---

## Task 4: Create production stack (docker-stack-infra)

**Files:**
- Modify: `docker-stack-infra/stacks/observador.yml`

- [ ] **Step 1: Replace observador.yml with full production stack**

Replace `stacks/observador.yml`:

```yaml
version: '3.8'

# Stack do projeto Observador de Domínios.
# Dominio: observadordedominios.com.br

networks:
  traefik-public:
    external: true
  internal:
    driver: overlay
    attachable: true

volumes:
  observador-postgres-data:
    driver: local

services:
  ###########################################
  # POSTGRES
  ###########################################
  postgres:
    image: postgres:16-alpine
    environment:
      - POSTGRES_DB=obs
      - POSTGRES_USER=obs
      - POSTGRES_PASSWORD=${OBSERVADOR_POSTGRES_PASSWORD}
    volumes:
      - observador-postgres-data:/var/lib/postgresql/data
    networks:
      - internal
    deploy:
      replicas: 1
      restart_policy:
        condition: any

  ###########################################
  # BACKEND API - FastAPI
  ###########################################
  backend:
    image: ghcr.io/${GHCR_OWNER}/observador-backend:latest
    networks:
      - internal
      - traefik-public
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=postgresql://obs:${OBSERVADOR_POSTGRES_PASSWORD}@postgres:5432/obs
      - S3_BUCKET=observadordedominios
      - S3_REGION=auto
      - S3_ENDPOINT_URL=https://c7d69182e6ae8686a3edc7bdd6eae9f8.r2.cloudflarestorage.com
      - S3_ACCESS_KEY_ID=${OBSERVADOR_R2_ACCESS_KEY_ID}
      - S3_SECRET_ACCESS_KEY=${OBSERVADOR_R2_SECRET_ACCESS_KEY}
      - S3_FORCE_PATH_STYLE=true
      - CZDS_USERNAME=${OBSERVADOR_CZDS_USERNAME}
      - CZDS_PASSWORD=${OBSERVADOR_CZDS_PASSWORD}
      - CZDS_ENABLED_TLDS=net,org,info
      - CZDS_SYNC_CRON=0 7 * * *
      - CZDS_BASE_URL=https://czds-api.icann.org
    deploy:
      labels:
        - traefik.enable=true
        - traefik.http.routers.observador-backend.rule=Host(`api.observadordedominios.com.br`)
        - traefik.http.routers.observador-backend.entrypoints=websecure
        - traefik.http.routers.observador-backend.tls=true
        - traefik.http.routers.observador-backend.tls.certresolver=cf
        - traefik.http.services.observador-backend.loadbalancer.server.port=8000
        - traefik.http.services.observador-backend.loadbalancer.healthcheck.path=/health
        - traefik.http.services.observador-backend.loadbalancer.healthcheck.interval=10s
        - traefik.http.services.observador-backend.loadbalancer.healthcheck.timeout=3s
        - traefik.http.routers.observador-backend.middlewares=cors@file
        - traefik.swarm.network=traefik-public
      replicas: 1
      update_config:
        order: start-first
        parallelism: 1
        delay: 10s
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3

  ###########################################
  # FRONTEND - Next.js
  ###########################################
  frontend:
    image: ghcr.io/${GHCR_OWNER}/observador-frontend:latest
    networks:
      - internal
      - traefik-public
    environment:
      - NODE_ENV=production
      - NEXT_PUBLIC_API_URL=https://api.observadordedominios.com.br
      - HOSTNAME=0.0.0.0
      - PORT=3000
    deploy:
      labels:
        - traefik.enable=true
        - traefik.http.routers.observador-frontend.rule=Host(`observadordedominios.com.br`) || Host(`www.observadordedominios.com.br`)
        - traefik.http.routers.observador-frontend.entrypoints=websecure
        - traefik.http.routers.observador-frontend.tls=true
        - traefik.http.routers.observador-frontend.tls.certresolver=cf
        - traefik.http.routers.observador-frontend.tls.domains[0].main=observadordedominios.com.br
        - traefik.http.routers.observador-frontend.tls.domains[0].sans=www.observadordedominios.com.br
        - traefik.http.routers.observador-frontend.middlewares=secure-headers@file
        - traefik.http.services.observador-frontend.loadbalancer.server.port=3000
        - traefik.http.services.observador-frontend.loadbalancer.healthcheck.path=/api/health
        - traefik.http.services.observador-frontend.loadbalancer.healthcheck.interval=10s
        - traefik.http.services.observador-frontend.loadbalancer.healthcheck.timeout=3s
        - traefik.http.routers.observador-www.rule=Host(`www.observadordedominios.com.br`)
        - traefik.http.routers.observador-www.entrypoints=websecure
        - traefik.http.routers.observador-www.middlewares=observador-www-redirect
        - traefik.http.middlewares.observador-www-redirect.redirectregex.regex=^https://www\.(.*)
        - traefik.http.middlewares.observador-www-redirect.redirectregex.replacement=https://$${1}
        - traefik.http.middlewares.observador-www-redirect.redirectregex.permanent=true
        - traefik.swarm.network=traefik-public
      replicas: 1
      update_config:
        order: start-first
        parallelism: 1
        delay: 10s
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3

  ###########################################
  # CZDS INGESTOR WORKER
  ###########################################
  czds_ingestor:
    image: ghcr.io/${GHCR_OWNER}/observador-backend:latest
    command: ["python", "-m", "app.worker.czds_ingestor"]
    networks:
      - internal
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=postgresql://obs:${OBSERVADOR_POSTGRES_PASSWORD}@postgres:5432/obs
      - S3_BUCKET=observadordedominios
      - S3_REGION=auto
      - S3_ENDPOINT_URL=https://c7d69182e6ae8686a3edc7bdd6eae9f8.r2.cloudflarestorage.com
      - S3_ACCESS_KEY_ID=${OBSERVADOR_R2_ACCESS_KEY_ID}
      - S3_SECRET_ACCESS_KEY=${OBSERVADOR_R2_SECRET_ACCESS_KEY}
      - S3_FORCE_PATH_STYLE=true
      - CZDS_USERNAME=${OBSERVADOR_CZDS_USERNAME}
      - CZDS_PASSWORD=${OBSERVADOR_CZDS_PASSWORD}
      - CZDS_ENABLED_TLDS=net,org,info
      - CZDS_SYNC_CRON=0 7 * * *
      - CZDS_BASE_URL=https://czds-api.icann.org
    deploy:
      replicas: 1
      update_config:
        order: start-first
        parallelism: 1
        delay: 10s
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3

  ###########################################
  # SIMILARITY WORKER
  ###########################################
  similarity_worker:
    image: ghcr.io/${GHCR_OWNER}/observador-backend:latest
    command: ["python", "-m", "app.worker.similarity_worker"]
    networks:
      - internal
    environment:
      - ENVIRONMENT=production
      - DATABASE_URL=postgresql://obs:${OBSERVADOR_POSTGRES_PASSWORD}@postgres:5432/obs
      - S3_BUCKET=observadordedominios
      - S3_REGION=auto
      - S3_ENDPOINT_URL=https://c7d69182e6ae8686a3edc7bdd6eae9f8.r2.cloudflarestorage.com
      - S3_ACCESS_KEY_ID=${OBSERVADOR_R2_ACCESS_KEY_ID}
      - S3_SECRET_ACCESS_KEY=${OBSERVADOR_R2_SECRET_ACCESS_KEY}
      - S3_FORCE_PATH_STYLE=true
      - CZDS_USERNAME=${OBSERVADOR_CZDS_USERNAME}
      - CZDS_PASSWORD=${OBSERVADOR_CZDS_PASSWORD}
      - CZDS_ENABLED_TLDS=net,org,info
      - CZDS_BASE_URL=https://czds-api.icann.org
    deploy:
      replicas: 1
      update_config:
        order: start-first
        parallelism: 1
        delay: 10s
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
```

- [ ] **Step 2: Commit**

```bash
git add stacks/observador.yml
git commit -m "feat: add observador production stack with R2, workers, and Traefik routing"
```

---

## Task 5: Modify deploy workflow for selective deploy (docker-stack-infra)

**Files:**
- Modify: `docker-stack-infra/.github/workflows/deploy.yml`

- [ ] **Step 1: Add `repository_dispatch` trigger**

Add `repository_dispatch` to the `on:` block:

```yaml
on:
  push:
    branches: [main]
  repository_dispatch:
    types: [deploy-stack]
  workflow_dispatch:
```

- [ ] **Step 2: Add observador image validation step**

After the existing Shalem image validation step, add an equivalent for observador:

```yaml
      - name: Validar imagens do Observador e aquecer cache remoto
        id: observador_images
        if: github.event_name != 'repository_dispatch' || github.event.client_payload.stack == 'observador'
        env:
          GHCR_TOKEN: ${{ secrets.GHCR_TOKEN }}
        run: |
          set -euo pipefail

          # Login no GHCR (local runner + servidor remoto)
          echo "$GHCR_TOKEN" | docker login "$GHCR_REGISTRY" --username "$GHCR_OWNER" --password-stdin
          ssh -o BatchMode=yes "$SERVER_HOST" "echo \"$GHCR_TOKEN\" | docker login \"$GHCR_REGISTRY\" --username \"$GHCR_OWNER\" --password-stdin"

          BACKEND_IMAGE="$GHCR_REGISTRY/$GHCR_OWNER/observador-backend:latest"
          FRONTEND_IMAGE="$GHCR_REGISTRY/$GHCR_OWNER/observador-frontend:latest"
          BACKEND_AVAILABLE=false
          FRONTEND_AVAILABLE=false

          if docker manifest inspect "$BACKEND_IMAGE" > /dev/null 2>&1; then
            BACKEND_AVAILABLE=true
            ssh -o BatchMode=yes "$SERVER_HOST" "docker --debug pull \"$BACKEND_IMAGE\""
          else
            echo "::warning::Imagem nao encontrada no GHCR: $BACKEND_IMAGE"
          fi

          if docker manifest inspect "$FRONTEND_IMAGE" > /dev/null 2>&1; then
            FRONTEND_AVAILABLE=true
            ssh -o BatchMode=yes "$SERVER_HOST" "docker --debug pull \"$FRONTEND_IMAGE\""
          else
            echo "::warning::Imagem nao encontrada no GHCR: $FRONTEND_IMAGE"
          fi

          echo "backend_available=$BACKEND_AVAILABLE" >> "$GITHUB_OUTPUT"
          echo "frontend_available=$FRONTEND_AVAILABLE" >> "$GITHUB_OUTPUT"
```

- [ ] **Step 3: Add conditional `if` to infra deploy steps**

Add to each infra step (bootstrap, traefik, portainer, dozzle):

```yaml
        if: github.event_name != 'repository_dispatch'
```

Steps that ALWAYS run (keep without condition):
- Checkout
- SSH known_hosts
- SSH agent
- Criar Docker Context
- Login no GHCR
- rsync de configs/ e stacks/
- Limpeza do Docker Context

- [ ] **Step 4: Update Deploy Application Stacks step**

Add observador env vars and selective logic:

```yaml
      - name: Deploy Application Stacks
        env:
          OPENAI_APIKEY: ${{ secrets.OPENAI_APIKEY }}
          SINDICOAI_POSTGRES_PASSWORD: ${{ secrets.SINDICOAI_POSTGRES_PASSWORD }}
          SHALEM_BACKEND_AVAILABLE: ${{ steps.shalem_images.outputs.backend_available }}
          SHALEM_FRONTEND_AVAILABLE: ${{ steps.shalem_images.outputs.frontend_available }}
          OBSERVADOR_POSTGRES_PASSWORD: ${{ secrets.OBSERVADOR_POSTGRES_PASSWORD }}
          OBSERVADOR_R2_ACCESS_KEY_ID: ${{ secrets.OBSERVADOR_R2_ACCESS_KEY_ID }}
          OBSERVADOR_R2_SECRET_ACCESS_KEY: ${{ secrets.OBSERVADOR_R2_SECRET_ACCESS_KEY }}
          OBSERVADOR_CZDS_USERNAME: ${{ secrets.OBSERVADOR_CZDS_USERNAME }}
          OBSERVADOR_CZDS_PASSWORD: ${{ secrets.OBSERVADOR_CZDS_PASSWORD }}
          OBSERVADOR_BACKEND_AVAILABLE: ${{ steps.observador_images.outputs.backend_available }}
          OBSERVADOR_FRONTEND_AVAILABLE: ${{ steps.observador_images.outputs.frontend_available }}
          DISPATCH_STACK: ${{ github.event.client_payload.stack }}
        run: |
          docker context use "$DOCKER_CONTEXT_NAME"

          for stack_file in stacks/*.yml; do
            if [ -f "$stack_file" ]; then
              stack_name=$(basename "$stack_file" .yml)

              # Selective deploy: on dispatch, only deploy the target stack
              if [ -n "${DISPATCH_STACK:-}" ] && [ "$stack_name" != "$DISPATCH_STACK" ]; then
                echo "Skipping stack $stack_name (dispatch target: $DISPATCH_STACK)"
                continue
              fi

              # Shalem image check
              if [ "$stack_name" = "shalem" ] && { [ "$SHALEM_BACKEND_AVAILABLE" != "true" ] || [ "$SHALEM_FRONTEND_AVAILABLE" != "true" ]; }; then
                echo "::warning::Pulando stack shalem (imagens indisponiveis)"
                continue
              fi

              # Observador image check
              if [ "$stack_name" = "observador" ] && { [ "${OBSERVADOR_BACKEND_AVAILABLE:-}" != "true" ] || [ "${OBSERVADOR_FRONTEND_AVAILABLE:-}" != "true" ]; }; then
                echo "::warning::Pulando stack observador (imagens indisponiveis)"
                continue
              fi

              echo "Deploying stack: $stack_name"
              docker stack deploy --compose-file "$stack_file" --with-registry-auth --resolve-image always --prune "$stack_name"

              set -o pipefail
              fmt='{{.Name}}'
              docker stack services "$stack_name" --format "$fmt" \
                | while read -r service; do
                    echo "Forcando atualizacao do servico $service"
                    if ! docker service update --force --with-registry-auth "$service"; then
                      echo "WARN: update failed for $service"
                      docker service ps "$service" --no-trunc || true
                      docker service logs "$service" --tail 200 || true
                    fi
                  done
            fi
          done
```

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/deploy.yml
git commit -m "ci: add repository_dispatch for selective stack deploy + observador support"
```

---

## Task 6: Configure DNS on Cloudflare

**Prerequisite:** This is a manual/MCP step, not code.

- [ ] **Step 1: Add DNS record for `api.observadordedominios.com.br`**

Add A record or CNAME pointing to `158.69.211.109` (the Swarm server).

- [ ] **Step 2: Verify existing DNS for `observadordedominios.com.br`**

Confirm root domain and `www` subdomain point to the server.

---

## Task 7: First deploy — push and verify

- [ ] **Step 1: Push observadordedominios changes**

```bash
cd observadordedominios
git push origin main
```

Expected: build-push workflow triggers, builds both images (first run), pushes to GHCR, dispatches to docker-stack-infra.

- [ ] **Step 2: Push docker-stack-infra changes**

```bash
cd docker-stack-infra
git push origin main
```

Expected: full deploy workflow triggers, deploys observador stack alongside others.

- [ ] **Step 3: Verify services are running**

```bash
ssh ubuntu@158.69.211.109 "docker stack services observador"
```

Expected: 5 services (postgres, backend, frontend, czds_ingestor, similarity_worker) all with 1/1 replicas.

- [ ] **Step 4: Verify endpoints**

- `https://observadordedominios.com.br` — frontend loads
- `https://api.observadordedominios.com.br/health` — returns 200
- `https://www.observadordedominios.com.br` — redirects to root domain
