sempre leve em consideração os arquivos:

- `.github\frontend.instructions.md` quando trabalhando na pasta frontend
- `.github\backend.instructions.md` quando estiver trabalhando na pasta backend

a Definição do produto está em `.specs/product_definition.md` e deve ser consultada antes de iniciar o desenvolvimento para garantir alinhamento com os requisitos do produto.

Os arquivos PRD e especificações dos produtos estão em `.specs/` e devem ser consultados antes de iniciar o desenvolvimento para garantir alinhamento com os requisitos do produto.
---

## 📁 Organização

- Todas as documentações devem ficar na pasta `docs` de forma organizada
- Scripts de teste/debug devem ficar em `backend/app/debug_scripts`

---

## 🐳 Docker e Hot Reload

### Ambiente de Desenvolvimento

O projeto usa **Docker Stack** (Swarm mode) com `infra/stack.dev.yml` e hot reload configurado:

**Frontend (Next.js)**
- Alterações em código recarregam automaticamente (Fast Refresh)
- Volumes mapeados: `app/`, `components/`, `lib/`, `public/`, `styles/`

**Backend (FastAPI)**
- Alterações em código reiniciam servidor automaticamente (Uvicorn --reload)
- Volumes mapeados: `app/`, `tests/`

### Executar Comandos

Scripts de teste e debug devem ser executados **dentro do container Docker**:

```powershell
# Encontrar container do backend
docker ps | findstr obs_backend

# Backend (use o CONTAINER ID)
docker exec -it <CONTAINER_ID> python app/debug_scripts/seu_script.py

# Frontend (encontre o container primeiro)
docker ps | findstr obs_frontend
docker exec -it <CONTAINER_ID> npm run seu-comando
```

### Rebuild apenas quando necessário

Hot reload detecta mudanças automaticamente. Rebuild APENAS quando:
- Adicionar dependências no `package.json` (frontend)
- Adicionar dependências no `pyproject.toml` (backend)
- Alterar Dockerfile

```powershell
# Rebuild específico
docker build -t observadordedominios-frontend:dev -f frontend/Dockerfile.dev frontend/
docker service update --image observadordedominios-frontend:dev obs_frontend

docker build -t observadordedominios-backend:dev -f backend/Dockerfile.dev backend/
docker service update --image observadordedominios-backend:dev obs_backend
```

---

## 📚 Documentação

Consulte sempre:
- `README.md` - Quick start
- `docs/docker-commands.md` - Comandos Docker completos
- `docs/design-system.md` - Componentes frontend

---

## 🗂️ Gestão de Refinamentos (`.specs/todos`)

- Todo refinamento técnico aprovado deve ganhar um item em `.specs/todos`.
- A numeração é sequencial de 3 dígitos (`001`, `002`, `003`...).
- Cada item deve conter:
	- `.specs/todos/<NNN>/plan.md`
	- `.specs/todos/<NNN>/references.md`
	- `.specs/todos/<NNN>/status.md`
- O arquivo `.specs/todos/_registry.md` é obrigatório para controlar ordem e status geral.
- Sempre atualizar `_registry.md` junto com `status.md` quando o status mudar.
- Status permitidos: `todo`, `in_progress`, `blocked`, `done`.

