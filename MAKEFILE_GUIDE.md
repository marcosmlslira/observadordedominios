# 📘 Guia do Makefile - OBS Domínios

O Makefile simplifica todos os comandos Docker Stack do projeto.

## 🚀 Quick Start

```powershell
# Ver todos os comandos
make help

# Build e deploy
make deploy

# Ver logs
make logs

# Ver status
make status
```

---

## 📚 Comandos Disponíveis

### 🚀 Deploy e Build

| Comando | Descrição |
|---------|-----------|
| `make deploy` | Build e deploy da stack completa |
| `make build` | Build de todas as imagens |
| `make build-frontend` | Build apenas frontend |
| `make build-backend` | Build apenas backend |
| `make build-prod` | Build para produção |
| `make build-clean` | Build sem cache |

**Exemplos:**
```powershell
# Deploy completo (desenvolvimento)
make deploy

# Build apenas uma imagem
make build-frontend

# Build para produção
make build-prod
make deploy-prod
```

---

### 📋 Logs

| Comando | Descrição |
|---------|-----------|
| `make logs` | Logs de todos os serviços |
| `make logs-frontend` | Logs do frontend |
| `make logs-backend` | Logs do backend |
| `make logs-10m` | Logs dos últimos 10 minutos |
| `make logs-show` | Logs sem follow (apenas exibe) |

**Exemplos:**
```powershell
# Ver logs em tempo real
make logs

# Ver apenas logs do backend
make logs-backend

# Ver logs dos últimos 10 minutos
make logs-10m
```

---

### 🔍 Status e Informações

| Comando | Descrição |
|---------|-----------|
| `make status` | Status completo da stack |
| `make services` | Lista serviços |
| `make ps` | Lista tasks/containers |
| `make health` | Verifica saúde dos serviços |

**Exemplos:**
```powershell
# Status completo
make status

# Verificar saúde
make health
```

---

### 🔄 Atualização e Rebuild

| Comando | Descrição |
|---------|-----------|
| `make update` | Atualiza todos os serviços |
| `make update-frontend` | Atualiza apenas frontend |
| `make update-backend` | Atualiza apenas backend |
| `make rebuild-frontend` | Rebuild e atualiza frontend |
| `make rebuild-backend` | Rebuild e atualiza backend |

**Exemplos:**
```powershell
# Após adicionar dependência no package.json
make rebuild-frontend

# Após adicionar dependência no pyproject.toml
make rebuild-backend

# Forçar atualização sem rebuild
make update
```

---

### 🧹 Limpeza

| Comando | Descrição |
|---------|-----------|
| `make remove` | Remove a stack |
| `make clean` | Remove stack + volumes |
| `make prune` | Limpa volumes e imagens |
| `make prune-all` | Limpeza completa (CUIDADO!) |

**Exemplos:**
```powershell
# Remover stack
make remove

# Remover + limpar volumes
make clean

# Limpar imagens não utilizadas
make prune
```

---

### 🐛 Debug

| Comando | Descrição |
|---------|-----------|
| `make exec-frontend` | Entra no container frontend |
| `make exec-backend` | Entra no container backend |
| `make shell-frontend` | Shell no frontend (alias) |
| `make shell-backend` | Shell no backend (alias) |
| `make inspect-frontend` | Inspeciona serviço frontend |
| `make inspect-backend` | Inspeciona serviço backend |

**Exemplos:**
```powershell
# Entrar no container backend
make exec-backend

# Executar comando
# Dentro do container:
python app/debug_scripts/teste.py
```

---

### 🧪 Testes

| Comando | Descrição |
|---------|-----------|
| `make test` | Executa todos os testes |
| `make test-backend` | Testes do backend (local) |
| `make test-backend-docker` | Testes no container |
| `make test-frontend` | Testes do frontend |

**Exemplos:**
```powershell
# Rodar testes
make test-backend

# Rodar testes dentro do container
make test-backend-docker
```

---

### 🌐 Atalhos de Navegador

| Comando | Descrição |
|---------|-----------|
| `make open` | Abre frontend |
| `make open-frontend` | Abre frontend |
| `make open-backend` | Abre backend docs |
| `make open-design-system` | Abre Design System |

**Exemplos:**
```powershell
# Abrir frontend no navegador
make open

# Abrir API docs
make open-backend

# Abrir Design System
make open-design-system
```

---

## 🎯 Workflows Comuns

### Primeira Vez

```powershell
# 1. Deploy completo
make deploy

# 2. Ver logs
make logs

# 3. Abrir no navegador
make open
```

### Desenvolvimento Diário

```powershell
# Iniciar
make deploy

# Ver logs enquanto desenvolve
make logs

# Hot reload detecta mudanças automaticamente
# Não precisa rebuildar!
```

### Adicionar Dependências

**Frontend:**
```powershell
# 1. Editar package.json
# 2. Rebuild e atualizar
make rebuild-frontend
```

**Backend:**
```powershell
# 1. Editar pyproject.toml
# 2. Rebuild e atualizar
make rebuild-backend
```

### Debug de Problemas

```powershell
# Ver status detalhado
make status

# Ver logs recentes
make logs-10m

# Entrar no container
make exec-backend

# Verificar saúde
make health

# Recriar tudo
make clean
make deploy
```

### Limpeza de Ambiente

```powershell
# Limpeza leve
make remove

# Limpeza média
make clean

# Limpeza profunda
make prune

# Limpeza total (CUIDADO!)
make prune-all
```

---

## 💡 Dicas

### Personalizar Comandos

Você pode criar seus próprios targets no Makefile:

```makefile
.PHONY: meu-comando
meu-comando:
	@echo "Fazendo algo útil..."
	# seus comandos aqui
```

### Passar Variáveis

```powershell
# Usar stack diferente
make deploy STACK_NAME=obs-teste STACK_FILE=infra/stack.test.yml
```

### Combinar Comandos

```powershell
# Rebuild e ver logs
make rebuild-backend && make logs-backend
```

### Alias Úteis

Adicione ao seu perfil PowerShell (`$PROFILE`):

```powershell
# Atalhos para OBS Domínios
function obs-deploy { make deploy }
function obs-logs { make logs }
function obs-status { make status }
function obs-clean { make clean }
```

---

## 🔧 Requisitos

- **Make**: Instale via Chocolatey
  ```powershell
  choco install make
  ```

- **Docker**: Docker Desktop com Swarm habilitado
  ```powershell
  docker swarm init
  ```

---

## 📖 Mais Informações

- [README.md](README.md) - Documentação principal
- [DOCKER_QUICK_START.md](DOCKER_QUICK_START.md) - Quick start
- [COMANDOS_STACK.md](COMANDOS_STACK.md) - Comandos Docker Stack manuais
- [docs/docker-commands.md](docs/docker-commands.md) - Documentação completa

---

## 🆘 Ajuda

```powershell
# Ver todos os comandos disponíveis
make help

# Ver comandos Make disponíveis
make -n <comando>  # Mostra o que seria executado
```
