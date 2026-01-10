# 🐳 Quick Start - Docker Stack

## 🎯 Opção 1: Makefile (Mais Simples)

```powershell
# Ver todos os comandos
make help

# Build + Deploy
make deploy

# Ver logs
make logs

# Status
make status

# Remover
make remove
```

## 📝 Opção 2: Script Helper

```powershell
# Build + Deploy
.\stack.ps1 deploy

# Ver logs em tempo real
.\stack.ps1 logs

# Remover stack
.\stack.ps1 remove

# Status
.\stack.ps1 status
```

## 🛠️ Opção 3: Docker Stack Manual

### Primeira Vez (Inicializar Swarm)

```powershell
docker swarm init
```

### Build das Imagens

```powershell
docker build -t observadordedominios-frontend:dev -f frontend/Dockerfile.dev frontend/
docker build -t observadordedominios-backend:dev -f backend/Dockerfile.dev backend/
```

### Deploy da Stack

```powershell
cd infra
docker stack deploy -c stack.dev.yml obs
```

## URLs

- Frontend: http://localhost:3005
- Backend: http://localhost:8005/docs
- Design System: http://localhost:3005/design-system

## Hot Reload Configurado ✅

### Frontend (Next.js)
Alterações em arquivos `.tsx`, `.ts`, `.css` recarregam automaticamente

### Backend (FastAPI)
Alterações em arquivos `.py` reiniciam o servidor automaticamente

## Comandos Úteis

**Usando Makefile (recomendado):**
```powershell
# Logs específicos
make logs-frontend
make logs-backend

# Rebuild e atualizar
make rebuild-frontend
make rebuild-backend

# Entrar no container
make exec-frontend
make exec-backend

# Abrir no navegador
make open-frontend
make open-backend
make open-design-system
```

**Usando comandos Docker:**
```powershell
# Ver logs em tempo real
docker service logs -f obs_frontend obs_backend

# Ver logs de um serviço específico  
docker service logs -f obs_backend
docker service logs -f obs_frontend

# Parar stack
docker stack rm obs

# Rebuild após adicionar dependências
docker build -t observadordedominios-frontend:dev -f frontend/Dockerfile.dev frontend/
docker build -t observadordedominios-backend:dev -f backend/Dockerfile.dev backend/
docker stack deploy -c infra/stack.dev.yml obs
```
