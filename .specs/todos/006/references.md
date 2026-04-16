# 006 - Referências

## Contexto de infraestrutura
- `infra/stack.yml` (repo atual) - serviço `postgres` em produção sem `ports`, e backend usando `postgres:5432`.
- `infra/stack.dev.yml` e `infra/stack.local.yml` - exemplos com `5432:5432` publicado.
- `COMANDOS_PRODUCAO.md` - host e fluxo operacional de produção.
- `.github/workflows/test-llm-prod.yml` - confirma acesso SSH ao host `158.69.211.109` com usuário `ubuntu`.

## Conexão atual da aplicação
- `DATABASE_URL=postgresql://obs:obs@postgres:5432/obs` no backend/workers.
- Serviço `postgres` nomeado na rede `app-network`.

## Decisões deste refinamento
- Padronizar porta publicada de produção em `15432/tcp`.
- Conexão de desenvolvedor via DBeaver com SSH tunnel nativo.
- Evitar dependência operacional de container proxy auxiliar por sessão.
