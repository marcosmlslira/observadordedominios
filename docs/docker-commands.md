# Scripts Docker - OBS Domínios

## 🔧 Comandos para Desenvolvimento

### Iniciar Ambiente de Desenvolvimento (com Hot Reload)

```powershell
# Build e start com hot reload
cd infra
docker-compose -f stack.dev.yml up --build

# Ou em modo detached
docker-compose -f stack.dev.yml up -d --build
```

### Parar Ambiente de Desenvolvimento

```powershell
cd infra
docker-compose -f stack.dev.yml down
```

### Ver Logs

```powershell
# Todos os serviços
docker-compose -f stack.dev.yml logs -f

# Apenas frontend
docker-compose -f stack.dev.yml logs -f frontend

# Apenas backend
docker-compose -f stack.dev.yml logs -f backend
```

### Rebuild de um Serviço Específico

```powershell
# Rebuild frontend
docker-compose -f stack.dev.yml up -d --build frontend

# Rebuild backend
docker-compose -f stack.dev.yml up -d --build backend
```

---

## 🚀 Comandos para Produção

### Build e Deploy

```powershell
cd infra
docker-compose -f stack.yml up --build -d
```

### Parar Produção

```powershell
cd infra
docker-compose -f stack.yml down
```

---

## 📁 Estrutura de Volumes (Desenvolvimento)

### Frontend
```
../frontend/app         → /app/app
../frontend/components  → /app/components
../frontend/lib         → /app/lib
../frontend/public      → /app/public
../frontend/styles      → /app/styles
```

**Excluído do volume:**
- `node_modules` (usa o do container)
- `.next` (cache de build)

### Backend
```
../backend/app          → /app/app
../backend/tests        → /app/tests
```

**Excluído do volume:**
- `__pycache__` (arquivos compilados Python)

---

## 🔥 Hot Reload Configurado

### Frontend (Next.js)
- ✅ Fast Refresh habilitado
- ✅ Alterações em `.tsx`, `.ts`, `.css` recarregam automaticamente
- ✅ Sem necessidade de rebuild

### Backend (FastAPI)
- ✅ Uvicorn com flag `--reload`
- ✅ Alterações em `.py` reiniciam servidor automaticamente
- ✅ Sem necessidade de rebuild

---

## 🐛 Troubleshooting

### Hot Reload não funciona no Frontend

```powershell
# Verificar se os volumes estão montados
docker-compose -f stack.dev.yml exec frontend ls -la /app/app

# Recriar container
docker-compose -f stack.dev.yml up -d --force-recreate frontend
```

### Hot Reload não funciona no Backend

```powershell
# Verificar se uvicorn está com --reload
docker-compose -f stack.dev.yml logs backend | grep reload

# Recriar container
docker-compose -f stack.dev.yml up -d --force-recreate backend
```

### Erros de Permissão (Windows)

```powershell
# Garantir que Docker Desktop tem acesso aos diretórios
# Settings → Resources → File Sharing
# Adicionar: C:\PROJETOS\observadordedominios
```

### Node Modules Desatualizados

```powershell
# Rebuild completo do frontend
docker-compose -f stack.dev.yml build --no-cache frontend
docker-compose -f stack.dev.yml up -d frontend
```

### Dependências Python Desatualizadas

```powershell
# Rebuild completo do backend
docker-compose -f stack.dev.yml build --no-cache backend
docker-compose -f stack.dev.yml up -d backend
```

---

## 📊 Portas

| Serviço  | Porta Local | Porta Container |
|----------|-------------|-----------------|
| Frontend | 3005        | 3000            |
| Backend  | 8005        | 8000            |

### Acessar Aplicação

- **Frontend**: http://localhost:3005
- **Backend API**: http://localhost:8005/docs
- **Design System**: http://localhost:3005/design-system

---

## 🧹 Limpeza

### Remover Containers e Volumes

```powershell
cd infra
docker-compose -f stack.dev.yml down -v
```

### Remover Imagens

```powershell
docker rmi observadordedominios-frontend:dev
docker rmi observadordedominios-backend:dev
```

### Limpeza Completa do Docker

```powershell
# ⚠️ Remove TODOS os containers, volumes e imagens não utilizados
docker system prune -a --volumes
```

---

## 🔄 Fluxo de Trabalho Recomendado

### 1. Primeira Vez

```powershell
cd infra
docker-compose -f stack.dev.yml up --build
```

### 2. Desenvolvimento Diário

```powershell
# Start (já buildado)
cd infra
docker-compose -f stack.dev.yml up -d

# Editar código normalmente
# Hot reload aplica mudanças automaticamente

# Ver logs se necessário
docker-compose -f stack.dev.yml logs -f

# Stop ao final do dia
docker-compose -f stack.dev.yml down
```

### 3. Novas Dependências

```powershell
# Rebuild apenas se adicionar dependências no package.json ou pyproject.toml
cd infra
docker-compose -f stack.dev.yml up -d --build
```

---

## ✅ Checklist de Configuração

- [x] Hot Reload Frontend (Next.js Fast Refresh)
- [x] Hot Reload Backend (Uvicorn --reload)
- [x] Volumes mapeados corretamente
- [x] Node modules isolados no container
- [x] Python cache isolado
- [x] Variáveis de ambiente configuradas
- [x] Restart policy configurada
- [x] Network bridge criada

---

## 📝 Notas

- **Sempre use `stack.dev.yml` para desenvolvimento**
- **Mudanças em arquivos `.tsx`, `.ts`, `.py` são detectadas automaticamente**
- **Não é necessário rebuild após cada alteração**
- **Rebuild apenas quando adicionar novas dependências**
