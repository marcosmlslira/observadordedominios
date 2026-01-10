# 🚀 Comandos Docker Stack - Referência Rápida

## ⚡ Usando Makefile (Recomendado)

O projeto possui um Makefile completo que simplifica todos os comandos.

```powershell
# Ver todos os comandos disponíveis
make help

# Deploy completo (build + deploy)
make deploy

# Ver logs
make logs
make logs-frontend
make logs-backend

# Status
make status

# Rebuild e atualizar
make rebuild-frontend
make rebuild-backend

# Remover
make remove
make clean  # Remove + limpa volumes
```

---

## 📋 Comandos Docker Stack Manuais

### Inicialização (Primeira Vez)

```powershell
# 1. Inicializar Docker Swarm
docker swarm init

# 2. Build das imagens
docker build -t observadordedominios-frontend:dev -f frontend/Dockerfile.dev frontend/
docker build -t observadordedominios-backend:dev -f backend/Dockerfile.dev backend/

# 3. Deploy da stack
cd infra
docker stack deploy -c stack.dev.yml obs
```

## Uso Diário

```powershell
# Iniciar (usando script helper)
.\stack.ps1 deploy

# Ver status
.\stack.ps1 status
# ou
docker stack services obs
docker stack ps obs

# Ver logs
.\stack.ps1 logs
# ou
docker service logs -f obs_frontend obs_backend

# Parar
docker stack rm obs
```

## Rebuild (Após adicionar dependências)

```powershell
# Frontend
docker build -t observadordedominios-frontend:dev -f frontend/Dockerfile.dev frontend/
docker service update --image observadordedominios-frontend:dev obs_frontend

# Backend
docker build -t observadordedominios-backend:dev -f backend/Dockerfile.dev backend/
docker service update --image observadordedominios-backend:dev obs_backend
```

## Debug

```powershell
# Listar containers
docker ps

# Entrar em um container
docker exec -it <CONTAINER_ID> bash   # Backend
docker exec -it <CONTAINER_ID> sh     # Frontend

# Ver logs de um serviço específico
docker service logs obs_frontend
docker service logs obs_backend

# Ver logs em tempo real
docker service logs -f obs_frontend
```

## Limpeza

```powershell
# Remover stack
docker stack rm obs

# Limpar volumes órfãos
docker volume prune

# Limpar tudo (CUIDADO!)
docker system prune -a --volumes
```

## Verificar Hot Reload

```powershell
# 1. Deploy da stack
.\stack.ps1 deploy

# 2. Ver logs
.\stack.ps1 logs

# 3. Editar arquivo .tsx ou .py
# 4. Observe os logs mostrando reload automático
```

## Troubleshooting

```powershell
# Stack não inicia
docker stack ps obs --no-trunc

# Verificar Swarm ativo
docker info | findstr Swarm

# Recriar tudo
docker stack rm obs
# Aguarde 10 segundos
.\stack.ps1 deploy

# Ver erros detalhados
docker service ps obs_frontend --no-trunc
docker service ps obs_backend --no-trunc
```

## URLs

- Frontend: http://localhost:3005
- Backend: http://localhost:8005/docs
- Design System: http://localhost:3005/design-system
