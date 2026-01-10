# Makefile para OBS Domínios
STACK_FILE ?= infra/stack.dev.yml
STACK_NAME ?= obs

.PHONY: help
help:
	@echo "🦉 OBS Domínios - Comandos Disponíveis"
	@echo "======================================"
	@echo ""
	@echo "🚀 Deploy e Build:"
	@echo "  make deploy          - Build e deploy da stack completa"
	@echo "  make build           - Build de todas as imagens"
	@echo "  make build-frontend  - Build apenas frontend"
	@echo "  make build-backend   - Build apenas backend"
	@echo ""
	@echo "📋 Logs:"
	@echo "  make logs            - Logs de todos os serviços"
	@echo "  make logs-frontend   - Logs do frontend"
	@echo "  make logs-backend    - Logs do backend"
	@echo "  make logs-10m        - Logs dos últimos 10 minutos"
	@echo ""
	@echo "🔍 Status e Info:"
	@echo "  make status          - Status da stack"
	@echo "  make ps              - Lista tasks/containers"
	@echo "  make services        - Lista serviços"
	@echo ""
	@echo "🔄 Atualização:"
	@echo "  make update          - Atualiza todos os serviços"
	@echo "  make update-frontend - Atualiza apenas frontend"
	@echo "  make update-backend  - Atualiza apenas backend"
	@echo ""
	@echo "🧹 Limpeza:"
	@echo "  make remove          - Remove a stack"
	@echo "  make clean           - Remove stack e volumes"
	@echo "  make prune           - Limpeza completa do Docker"
	@echo ""
	@echo "🐛 Debug:"
	@echo "  make exec-frontend   - Entra no container frontend"
	@echo "  make exec-backend    - Entra no container backend"
	@echo "  make shell-frontend  - Shell no frontend"
	@echo "  make shell-backend   - Shell no backend"
	@echo ""
	@echo "🧪 Testes:"
	@echo "  make test-backend    - Executa testes do backend"
	@echo ""
	@echo "📦 URLs:"
	@echo "  Frontend:      http://localhost:3005"
	@echo "  Backend:       http://localhost:8005/docs"
	@echo "  Design System: http://localhost:3005/design-system"

# ============================================================================
# BUILD - Construção de imagens
# ============================================================================

.PHONY: build build-frontend build-backend
build: build-frontend build-backend

build-frontend:
	@echo "📦 Building frontend:dev..."
	docker build -t observadordedominios-frontend:dev -f frontend/Dockerfile.dev frontend/
	@echo "✅ Frontend image built!"

build-backend:
	@echo "📦 Building backend:dev..."
	docker build -t observadordedominios-backend:dev -f backend/Dockerfile.dev backend/
	@echo "✅ Backend image built!"

# Build para produção
.PHONY: build-prod build-frontend-prod build-backend-prod
build-prod: build-frontend-prod build-backend-prod

build-frontend-prod:
	@echo "📦 Building frontend:latest (production)..."
	docker build -t observadordedominios-frontend:latest -f frontend/Dockerfile frontend/
	@echo "✅ Frontend production image built!"

build-backend-prod:
	@echo "📦 Building backend:latest (production)..."
	docker build -t observadordedominios-backend:latest -f backend/Dockerfile backend/
	@echo "✅ Backend production image built!"

# Build sem cache
.PHONY: build-clean
build-clean:
	@echo "🧹 Building without cache..."
	docker build --no-cache -t observadordedominios-frontend:dev -f frontend/Dockerfile.dev frontend/
	docker build --no-cache -t observadordedominios-backend:dev -f backend/Dockerfile.dev backend/
	@echo "✅ Clean build completed!"

# ============================================================================
# DEPLOY - Deploy da stack
# ============================================================================

.PHONY: deploy deploy-prod init-swarm
deploy: build
	@echo "🚀 Deploying stack '$(STACK_NAME)'..."
	@$(MAKE) init-swarm
	docker stack deploy -c $(STACK_FILE) $(STACK_NAME)
	@echo "✅ Stack deployed successfully!"
	@echo "⏳ Aguarde alguns segundos para os serviços iniciarem..."
	@sleep 3
	@$(MAKE) status

deploy-prod: build-prod
	@echo "🚀 Deploying production stack '$(STACK_NAME)'..."
	@$(MAKE) init-swarm
	docker stack deploy -c infra/stack.yml $(STACK_NAME)
	@echo "✅ Production stack deployed!"

init-swarm:
	@if ! docker info --format '{{.Swarm.LocalNodeState}}' | grep -q active; then \
		echo "🔄 Inicializando Docker Swarm..."; \
		docker swarm init; \
	fi

# ============================================================================
# LOGS - Visualização de logs
# ============================================================================

.PHONY: logs logs-frontend logs-backend logs-10m logs-frontend-10m logs-backend-10m
logs:
	docker service logs -f $(STACK_NAME)_frontend $(STACK_NAME)_backend

logs-frontend:
	docker service logs -f $(STACK_NAME)_frontend

logs-backend:
	docker service logs -f $(STACK_NAME)_backend

logs-10m:
	docker service logs --follow --since 10m $(STACK_NAME)_frontend $(STACK_NAME)_backend

logs-frontend-10m:
	docker service logs --follow --since 10m $(STACK_NAME)_frontend

logs-backend-10m:
	docker service logs --follow --since 10m $(STACK_NAME)_backend

# Logs sem follow (apenas exibe)
.PHONY: logs-show
logs-show:
	docker service logs $(STACK_NAME)_frontend $(STACK_NAME)_backend

# ============================================================================
# STATUS - Verificação de status
# ============================================================================

.PHONY: status services ps
status:
	@echo "📊 Status da Stack $(STACK_NAME)"
	@echo "================================"
	@docker stack services $(STACK_NAME)
	@echo ""
	@echo "📦 Tasks:"
	@docker stack ps $(STACK_NAME) --no-trunc
	@echo ""
	@echo "📍 URLs:"
	@echo "   Frontend:      http://localhost:3005"
	@echo "   Backend:       http://localhost:8005/docs"
	@echo "   Design System: http://localhost:3005/design-system"

services:
	docker stack services $(STACK_NAME)

ps:
	docker stack ps $(STACK_NAME)

# ============================================================================
# UPDATE - Atualização de serviços
# ============================================================================

.PHONY: update update-frontend update-backend update-all
update: update-all

update-all:
	@echo "🔄 Atualizando todos os serviços..."
	-docker service update --force $(STACK_NAME)_frontend
	-docker service update --force $(STACK_NAME)_backend
	@echo "✅ Serviços atualizados!"

update-frontend:
	@echo "🔄 Atualizando frontend..."
	docker service update --force $(STACK_NAME)_frontend
	@echo "✅ Frontend atualizado!"

update-backend:
	@echo "🔄 Atualizando backend..."
	docker service update --force $(STACK_NAME)_backend
	@echo "✅ Backend atualizado!"

# Rebuild e update de um serviço específico
.PHONY: rebuild-frontend rebuild-backend
rebuild-frontend: build-frontend
	@echo "🔄 Atualizando imagem do frontend..."
	docker service update --image observadordedominios-frontend:dev $(STACK_NAME)_frontend
	@echo "✅ Frontend rebuilded e atualizado!"

rebuild-backend: build-backend
	@echo "🔄 Atualizando imagem do backend..."
	docker service update --image observadordedominios-backend:dev $(STACK_NAME)_backend
	@echo "✅ Backend rebuilded e atualizado!"

# ============================================================================
# REMOVE - Remoção da stack
# ============================================================================

.PHONY: remove down clean
remove:
	@echo "🛑 Removendo stack $(STACK_NAME)..."
	docker stack rm $(STACK_NAME)
	@echo "✅ Stack removida!"

down: remove

clean: remove
	@echo "🧹 Limpando volumes órfãos..."
	@sleep 5
	docker volume prune -f
	@echo "✅ Ambiente limpo!"

# ============================================================================
# PRUNE - Limpeza profunda
# ============================================================================

.PHONY: prune prune-volumes prune-images prune-all
prune-volumes:
	@echo "🧹 Removendo volumes não utilizados..."
	docker volume prune -f

prune-images:
	@echo "🧹 Removendo imagens não utilizadas..."
	docker image prune -a -f

prune-all:
	@echo "⚠️  ATENÇÃO: Isso removerá TODOS os recursos Docker não utilizados!"
	@echo "Pressione Ctrl+C para cancelar ou Enter para continuar..."
	@read dummy
	docker system prune -a --volumes -f
	@echo "✅ Limpeza completa realizada!"

prune: prune-volumes prune-images

# ============================================================================
# DEBUG - Comandos de debug
# ============================================================================

.PHONY: exec-frontend exec-backend shell-frontend shell-backend inspect-frontend inspect-backend
exec-frontend:
	@container_id=$$(docker ps -q -f name=$(STACK_NAME)_frontend | head -n1); \
	if [ -z "$$container_id" ]; then echo "❌ Container frontend não encontrado"; exit 1; fi; \
	docker exec -it $$container_id sh

exec-backend:
	@container_id=$$(docker ps -q -f name=$(STACK_NAME)_backend | head -n1); \
	if [ -z "$$container_id" ]; then echo "❌ Container backend não encontrado"; exit 1; fi; \
	docker exec -it $$container_id bash

shell-frontend: exec-frontend
shell-backend: exec-backend

inspect-frontend:
	docker service inspect $(STACK_NAME)_frontend --pretty

inspect-backend:
	docker service inspect $(STACK_NAME)_backend --pretty

# ============================================================================
# RESTART - Reiniciar serviços
# ============================================================================

.PHONY: restart restart-frontend restart-backend
restart: update-all

restart-frontend: update-frontend

restart-backend: update-backend

# ============================================================================
# TESTS - Execução de testes
# ============================================================================

.PHONY: test test-backend test-backend-docker test-frontend
test: test-backend

test-backend:
	@echo "🧪 Executando testes do backend..."
	cd backend && pytest tests/ -v

test-backend-docker:
	@echo "🧪 Executando testes dentro do container backend..."
	@container_id=$$(docker ps -q -f name=$(STACK_NAME)_backend | head -n1); \
	if [ -z "$$container_id" ]; then echo "❌ Container backend não encontrado"; exit 1; fi; \
	docker exec -it $$container_id pytest /app/tests/ -v

test-frontend:
	@echo "🧪 Executando testes do frontend..."
	cd frontend && npm test

# ============================================================================
# INSTALL - Instalação de dependências
# ============================================================================

.PHONY: install-frontend install-backend
install-frontend:
	@echo "📦 Instalando dependências do frontend..."
	cd frontend && npm install
	@echo "⚠️  Lembre-se de rebuildar a imagem: make rebuild-frontend"

install-backend:
	@echo "📦 Instalando dependências do backend..."
	cd backend && poetry install
	@echo "⚠️  Lembre-se de rebuildar a imagem: make rebuild-backend"

# ============================================================================
# DEV - Comandos de desenvolvimento
# ============================================================================

.PHONY: dev dev-frontend dev-backend
dev: deploy
	@echo "🎯 Ambiente de desenvolvimento iniciado!"
	@echo ""
	@echo "Hot Reload configurado:"
	@echo "  ✅ Frontend: Fast Refresh automático"
	@echo "  ✅ Backend: Uvicorn --reload automático"
	@echo ""
	@echo "Para ver logs: make logs"

dev-frontend:
	@echo "🎨 Iniciando apenas frontend em dev..."
	cd frontend && npm run dev

dev-backend:
	@echo "🔧 Iniciando apenas backend em dev..."
	cd backend && poetry run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ============================================================================
# URLS - Atalhos para abrir URLs
# ============================================================================

.PHONY: open open-frontend open-backend open-design-system
open: open-frontend

open-frontend:
	@echo "🌐 Abrindo frontend..."
	@powershell -Command "Start-Process 'http://localhost:3005'"

open-backend:
	@echo "🌐 Abrindo backend docs..."
	@powershell -Command "Start-Process 'http://localhost:8005/docs'"

open-design-system:
	@echo "🎨 Abrindo Design System..."
	@powershell -Command "Start-Process 'http://localhost:3005/design-system'"

# ============================================================================
# HEALTH - Verificação de saúde
# ============================================================================

.PHONY: health health-frontend health-backend
health: health-frontend health-backend

health-frontend:
	@echo "🏥 Verificando saúde do frontend..."
	@curl -f http://localhost:3005 > /dev/null 2>&1 && echo "✅ Frontend OK" || echo "❌ Frontend DOWN"

health-backend:
	@echo "🏥 Verificando saúde do backend..."
	@curl -f http://localhost:8005/health > /dev/null 2>&1 && echo "✅ Backend OK" || echo "❌ Backend DOWN"

# ============================================================================
# WATCH - Observar mudanças (experimental)
# ============================================================================

.PHONY: watch-logs
watch-logs:
	@echo "👀 Observando logs (Ctrl+C para sair)..."
	watch -n 2 'docker stack ps $(STACK_NAME)'
