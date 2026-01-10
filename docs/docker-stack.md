# Stack Docker - Observador de Domínios

## 🚀 Ambientes

O projeto possui duas configurações Docker:

### Desenvolvimento (`stack.dev.yml`) ⚡
- **Hot Reload Habilitado**
- Volumes mapeados para código fonte
- Next.js em modo `dev` com Fast Refresh
- FastAPI com `--reload` flag
- Ideal para desenvolvimento local

### Produção (`stack.yml`) 🚀
- Build otimizado
- Sem volumes de código
- Next.js em modo `standalone`
- FastAPI sem reload
- Pronto para deploy

---

## ✅ Status do Ambiente

### Containers Ativos
- **Backend**: `observadordedominios-backend:latest`
  - Container: `infra-backend-1`
  - Porta interna: 8000
  - Porta externa: **8005**
  - Status: ✅ Rodando
  - Health check: ✅ OK (`{"status":"ok"}`)

- **Frontend**: `observadordedominios-frontend:latest`
  - Container: `infra-frontend-1`
  - Porta interna: 3000
  - Porta externa: **3005**
  - Status: ✅ Rodando
  - Next.js: ✅ Pronto

### Rede
- Network: `infra_app-network` (bridge)
- Comunicação interna: ✅ Funcionando

## 🚀 Comandos Úteis

### Gerenciar Stack
```powershell
# Subir stack
cd c:\PROJETOS\observadordedominios\infra
docker-compose -f stack.yml up -d

# Ver logs
docker-compose -f stack.yml logs -f

# Parar stack
docker-compose -f stack.yml down

# Rebuild
docker-compose -f stack.yml build
docker-compose -f stack.yml up -d --force-recreate
```

### Verificar Status
```powershell
# Status dos containers
docker-compose -f stack.yml ps

# Logs do backend
docker logs infra-backend-1 --tail 50 -f

# Logs do frontend
docker logs infra-frontend-1 --tail 50 -f
```

### Testes Internos (dentro dos containers)
```powershell
# Health check do backend
docker exec infra-backend-1 python -c "import requests; print(requests.get('http://localhost:8000/health').json())"

# Frontend acessando backend
docker exec infra-frontend-1 wget -qO- http://infra-backend-1:8000/health
```

## 🌐 Acesso

### URLs Locais
- **Frontend**: http://localhost:3005
- **Backend API**: http://localhost:8005
- **Backend Health**: http://localhost:8005/health
- **Backend Docs**: http://localhost:8005/docs

### ✅ Ambiente Local Confirmado
- Contexto Docker: `desktop-linux` (local)
- Containers rodando no Docker Desktop local
- Acesso via localhost funcionando

## 📋 Configurações

### Portas (todas terminam em 5)
- Frontend: `3005` (mapeada de 3000)
- Backend: `8005` (mapeada de 8000)

### Arquivos
- Stack: `infra/stack.yml`
- Backend Dockerfile: `backend/Dockerfile`
- Frontend Dockerfile: `frontend/Dockerfile`

## 🔧 Troubleshooting

### Container não inicia
```powershell
docker logs <container-name>
docker-compose -f stack.yml down
docker-compose -f stack.yml up -d
```

### Rebuild completo
```powershell
docker-compose -f stack.yml down
docker-compose -f stack.yml build --no-cache
docker-compose -f stack.yml up -d
```

### Limpar recursos não utilizados
```powershell
docker system prune -a --volumes
```

### ⚠️ IMPORTANTE: Verificar Contexto Docker
Sempre confirme que está usando o contexto local antes de executar comandos:

```powershell
# Verificar contexto atual
docker context ls

# Deve mostrar: desktop-linux * ou default *

# Se estiver em outro contexto (ex: swarm-prod), mude para local:
docker context use desktop-linux

# Ou
docker context use default
```

**NUNCA execute comandos com contexto apontando para servidores de produção!**

## ✨ Features

- ✅ Tailwind CSS v4 com design system Grok
- ✅ Shadcn/ui configurado
- ✅ FastAPI backend com health check
- ✅ Next.js 15 frontend standalone
- ✅ Docker multi-stage builds
- ✅ Network isolation
- ✅ Portas não conflitantes (terminam em 5)
