---
name: production-server-ops
description: "Gerencia e depura o servidor de producao do Observador de Dominios via SSH, com foco em Docker Swarm, servicos observador_*, health checks, envs efetivas e testes reais contra as URLs produtivas."
---

# Production Server Ops

Use este skill quando precisar operar ou depurar a producao do Observador de Dominios.

## Escopo
- Verificar `docker service ps`, `docker service inspect` e `docker service logs`.
- Validar envs efetivas do `observador_backend`, `observador_frontend`, `observador_czds_ingestor` e `observador_similarity_worker`.
- Testar `https://observadordedominios.com.br` e `https://api.observadordedominios.com.br/health`.
- Diagnosticar login admin em `POST /v1/auth/login`.
- Fazer reinicio controlado de servicos do stack.

## Regras
- Nao grave senha, token ou hash no repositorio.
- Prefira ajustar a origem da configuracao em `docker-stack-infra` antes de fazer hotfix manual no servidor.
- Use hotfix manual apenas quando o ambiente estiver quebrado e o usuario quiser restauracao imediata.
- Sempre confirme a env efetiva do servico com `docker service inspect` antes de concluir que um deploy entrou.

## Fonte da verdade
- Login admin: [backend/app/api/v1/routers/auth.py](/C:/PROJETOS/observadordedominios/backend/app/api/v1/routers/auth.py)
- Configs do backend: [backend/app/core/config.py](/C:/PROJETOS/observadordedominios/backend/app/core/config.py)
- Stack produtivo da app: [infra/stack.yml](/C:/PROJETOS/observadordedominios/infra/stack.yml)
- Stack produtivo real: `C:\PROJETOS\docker-stack-infra\stacks\observador.yml`
- Workflow de deploy real: `C:\PROJETOS\docker-stack-infra\.github\workflows\deploy.yml`

## Fluxo recomendado
1. Verificar se a URL publica e o `/health` respondem.
2. Verificar `docker service ps observador_backend`.
3. Inspecionar envs do servico:
   - `ADMIN_EMAIL`
   - `ADMIN_PASSWORD_HASH`
   - `JWT_SECRET_KEY`
   - `CZDS_ENABLED_TLDS`
4. Validar logs recentes do backend.
5. Testar login real com `POST /v1/auth/login`.
6. Se env estiver errada, corrigir no `docker-stack-infra` e redeployar.

## Ferramenta local
Use [scripts/prod_server.py](/C:/PROJETOS/observadordedominios/scripts/prod_server.py) para operacoes comuns.

Variaveis esperadas:
- `PROD_HOST`
- `PROD_USER`
- `PROD_PASSWORD`

Exemplos:
```powershell
$env:PROD_HOST="158.69.211.109"
$env:PROD_USER="ubuntu"
$env:PROD_PASSWORD="***"
py scripts/prod_server.py status
py scripts/prod_server.py auth-env
py scripts/prod_server.py logs --service observador_backend --tail 200
py scripts/prod_server.py test-login --email admin@observador.com --password mls1509ti
```

## Diagnostico conhecido deste projeto
- Se `ADMIN_EMAIL`, `ADMIN_PASSWORD_HASH` ou `JWT_SECRET_KEY` estiverem vazios no `observador_backend`, nao existe login valido em producao.
- O frontend chama `POST /v1/auth/login` e nao ha fallback para banco; o login depende estritamente das envs do backend.
- O conjunto de TLDs ingeridos hoje vem de `CZDS_ENABLED_TLDS`.
