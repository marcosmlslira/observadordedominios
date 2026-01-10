# 🦉 OBS Domínios - Observador de Domínios

Sistema completo de monitoramento de domínios com análise de DNS, SSL, Uptime e Blacklist.

---

## 🚀 Quick Start

### Pré-requisitos

- Docker Desktop
- Docker Compose
- **Make** (opcional, mas recomendado)
  ```powershell
  # Instalar Make via Chocolatey
  choco install make
  ```

### Opção 1: Makefile (Mais Simples) 🎯

```powershell
# Ver todos os comandos disponíveis
make help

# Build e deploy completo
make deploy

# Ver logs
make logs

# Status da stack
make status

# Remover stack
make remove
```

### Opção 2: Script Helper

```powershell
# Build e deploy da stack
.\stack.ps1 deploy

# Ver logs
.\stack.ps1 logs

# Ver logs de um serviço específico
.\stack.ps1 logs -Service frontend
.\stack.ps1 logs -Service backend

# Remover stack
.\stack.ps1 remove

# Rebuild após adicionar dependências
.\stack.ps1 build
.\stack.ps1 deploy

# Ver status
.\stack.ps1 status

# Limpeza completa
.\stack.ps1 clean
```

### Opção 3: Docker Stack Manual

```powershell
# Inicializar Swarm (primeira vez)
docker swarm init

# Build das imagens
docker build -t observadordedominios-frontend:dev -f frontend/Dockerfile.dev frontend/
docker build -t observadordedominios-backend:dev -f backend/Dockerfile.dev backend/

# Deploy da stack
cd infra
docker stack deploy -c stack.dev.yml obs
```

Aguarde o build e inicialização. Acesse:

- **Frontend**: http://localhost:3005
- **Backend API**: http://localhost:8005/docs
- **Design System**: http://localhost:3005/design-system

### ✅ Hot Reload Configurado

**Frontend (Next.js)**
- Alterações em `.tsx`, `.ts`, `.css` recarregam automaticamente
- Fast Refresh habilitado

**Backend (FastAPI)**
- Alterações em `.py` reiniciam o servidor automaticamente
- Uvicorn com `--reload`

---

## 📂 Estrutura do Projeto

```
observadordedominios/
├── backend/           # FastAPI + Python
│   ├── app/          # Código fonte
│   ├── tests/        # Testes
│   ├── Dockerfile    # Build produção
│   └── Dockerfile.dev # Build desenvolvimento
├── frontend/         # Next.js + React + TypeScript
│   ├── app/         # Pages e routes
│   ├── components/  # Componentes reutilizáveis
│   ├── lib/         # Utilitários
│   ├── Dockerfile   # Build produção
│   └── Dockerfile.dev # Build desenvolvimento
├── infra/           # Configuração Docker
│   ├── stack.yml    # Docker Compose produção
│   └── stack.dev.yml # Docker Compose desenvolvimento
└── docs/            # Documentação
```

---

## 🛠️ Desenvolvimento

### Comandos Úteis

**Usando Makefile (recomendado):**
```powershell
# Ver logs
make logs

# Ver logs de um serviço específico
make logs-frontend
make logs-backend

# Status
make status

# Rebuild e atualizar
make rebuild-frontend
make rebuild-backend

# Entrar no container
make exec-frontend
make exec-backend
```

**Ou manualmente:**
```powershell
# Usando Makefile:**
```powershell
# Edite frontend/package.json
make rebuild-frontend

# Edite backend/pyproject.toml
make rebuild-backend
```

**Manualmente:**

**Ver logs em tempo real
docker service logs -f obs_frontend obs_backend

# Ver logs de um serviço específico
docker service logs -f obs_backend
docker service logs -f obs_frontend

# Remover stack
docker stack rm obs

# Rebuild após adicionar dependências
docker build -t observadordedominios-frontend:dev -f frontend/Dockerfile.dev frontend/
docker build -t observadordedominios-backend:dev -f backend/Dockerfile.dev backend/
docker stack deploy -c infra/stack.dev.yml obs

# Ver status da stack
docker stack services obs
docker stack ps obs
```

### Adicionar Dependências

**Frontend (npm)**
1. Edite `frontend/package.json`
2. Rebuild: 
```powershell
docker build -t observadordedominios-frontend:dev -f frontend/Dockerfile.dev frontend/
docker service update --image observadordedominios-frontend:dev obs_frontend
```

**Backend (poetry)**
1. Edite `backend/pyproject.toml`
2. Rebuild:
```powershell
docker build -t observadordedominios-backend:dev -f backend/Dockerfile.dev backend/
docker service update --image observadordedominios-backend:dev obs_backend
```

---

## 🎨 Design System

O projeto usa um Design System rigoroso baseado em Shadcn/ui + Tailwind CSS.

**Acesse**: http://localhost:3005/design-system

### Regra de Ouro
> Se um componente não aparece na página `/design-system`, ele não existe.

### Princípios
- ✅ Mobile-first obrigatório
- ✅ Apenas tokens de design
- ❌ Sem cores hardcoded
- ❌ Sem espaçamentos arbitrários

📖 **[Documentação Completa](docs/design-system.md)**

---

## 📚 Documentação
**Usando Makefile:**
```powershell
# Testes backend
make test-backend

# Testes dentro do container
make test-backend-docker
```

**Manualmente:**


- **[Docker Stack](docs/docker-stack.md)** - Arquitetura Docker
- **[Docker Commands](docs/docker-commands.md)** - Comandos e troubleshooting
- **[Design System](docs/design-system.md)** - Componentes e tokens
- **[Frontend Governance](.github/instructions/frontend.instructions.md)** - Regras de frontend
- **[Backend Governance](.github/instructions/backend.instructions.md)** - Regras de backend

---

## 🧪 Testes

### Backend
```powershell
# Encontrar o container
docker ps | findstr obs_backend

# Entrar no container (use o CONTAINER ID)
docker exec -it <CONTAINER_ID> bash

# Rodar testes
pytest
```

### Frontend
```powershell
# Encontrar o container
docker ps | findstr obs_frontend

# Entrar no container (use o CONTAINER ID)
docker exec -it <CONTAINER_ID> sh

# Rodar testes (quando implementados)
npm test
```

---

## 🔒 Governança

Este projeto segue regras rígidas de governança para manter a qualidade do código.

### Frontend
- Design System é fonte única de verdade
- Mobile-first obrigatório
- Componentes reutilizáveis apenas
- Sem duplicação visual

### Backend
- API RESTful seguindo padrões
- Testes unitários obrigatórios
- Type hints em Python
- Documentação automática (Swagger)

---

## 🚀 Deploy (Produção)

```powershell
# Build imagens de produção
docker build -t observadordedominios-frontend:latest -f frontend/Dockerfile frontend/
docker build -t observadordedominios-backend:latest -f backend/Dockerfile backend/

# Deploy stack de produção
cd infra
docker stack deploy -c stack.yml obs
```

---

## 🐛 Troubleshooting

### Hot Reload não funciona

```powershell
# Remover e recriar stack
docker stack rm obs
# Aguarde ~10 segundos
.\stack.ps1 deploy
```

### Erros de Build

```powershell
# Limpar cache e rebuildar
docker build --no-cache -t observadordedominios-frontend:dev -f frontend/Dockerfile.dev frontend/
docker build --no-cache -t observadordedominios-backend:dev -f backend/Dockerfile.dev backend/
docker stack deploy -c infra/stack.dev.yml obs
```

### Portas em uso

```powershell
# Verificar processos usando as portas
netstat -ano | findstr :3005
netstat -ano | findstr :8005

# Matar processo (substitua PID)
taskkill /PID <PID> /F
```

---

## 📦 Stack Tecnológica

### Frontend
- Next.js 15
- React 19
- TypeScript
- Tailwind CSS 4
- Shadcn/ui
- Radix UI
- Lucide Icons

### Backend
- Python 3.12
- FastAPI
- Poetry
- Uvicorn
- Pydantic

### DevOps
- Docker
- Docker Compose

---

## 👥 Contribuindo

1. Clone o repositório
2. Crie uma branch: `git checkout -b feature/nova-funcionalidade`
3. Faça suas alterações
4. Rode os testes
5. Commit: `git commit -m 'feat: adiciona nova funcionalidade'`
6. Push: `git push origin feature/nova-funcionalidade`
7. Abra um Pull Request

### Checklist para PRs

- [ ] Código segue as regras de governança
- [ ] Componentes frontend existem no Design System
- [ ] Testes implementados
- [ ] Documentação atualizada
- [ ] Hot reload testado
- [ ] Build funciona sem erros

---

## 📄 Licença

Propriedade de OBS Domínios. Todos os direitos reservados.

---

## 📞 Suporte

Para dúvidas ou problemas, consulte a documentação em `/docs` ou abra uma issue.
