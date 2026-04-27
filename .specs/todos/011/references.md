# References — TODO 011

## Decisões base

- [ADR-001 — Redesign da tabela `domain`](../../../docs/adr/001-domain-table-redesign.md) — modelo append-only, partições por TLD
- [ADR-002 — Arquitetura de ingestão diária e atualização por TLD](../../../docs/adr/002-ingestion-daily-tld-update-architecture.md) — fases SKIP/LOAD_ONLY/FULL_RUN, R2 como contrato operacional
- [TODO 010 — Catálogo de problemas em produção](../010/plan.md) — diagnóstico forense que motivou este plano
- [TODO 008 — Pipeline de ingestão automatizado](../008/plan.md) — base do orquestrador atual
- [TODO 009 — Correções de confiabilidade](../009/plan.md) — overlap parcial; ver §10 do plan.md

## Arquivos do worker que serão alterados

- `ingestion/scheduler.py` — entry point, HTTP server porta 8080, `_run_daily_cycle()`, `_last_run_info` (Sprint 3.3)
- `ingestion/ingestion/orchestrator/pipeline.py` — `run_cycle()`, idempotência (sem mudanças estruturais)
- `ingestion/ingestion/loader/delta_loader.py` — **alvo principal do Sprint 2** (eliminar DETACH/ATTACH/DROP INDEX)
- `ingestion/ingestion/observability/run_recorder.py` — adicionar `ingestion_cycle` (Sprint 3.2)
- `ingestion/provisioning/provision_tld.py` — **novo** (Sprint 2.2)

## Arquivos do backend que serão alterados

- `backend/app/api/v1/routers/ingestion.py` — proxy de triggers + novos endpoints `/cycles` e `/tlds/health`
- `backend/alembic/versions/xxxx_staging_tables.py` — **nova** migration (Sprint 2.1)
- `backend/alembic/versions/xxxx_ingestion_cycle.py` — **nova** migration (Sprint 3.1)
- `backend/alembic/versions/xxxx_tld_health_view.py` — **nova** migration (Sprint 3.4)

## Arquivos de infra que serão alterados — em `C:\PROJETOS\docker-stack-infra`

> Atenção: a infra real mora em **outro repositório** (`docker-stack-infra`). Mudanças em stacks/workflows precisam ser commitadas lá, não aqui.

- `stacks/observador.yml` — memory limits no `postgres` e `ingestion_worker` (Sprint 1.4); `restart_policy: on-failure` no worker (1.5); `INGESTION_TRIGGER_URLS` no env do backend (1.6); **remover bloco `ingestion_worker`** quando 1.7 for ativada
- `stacks/observador-ingestion.yml.draft` — **novo, criado já como draft** (Sprint 1.7); ativar removendo o `.draft` quando aprovado
- `.github/workflows/deploy.yml` — filtrar `observador-ingestion` em `push` automático (Sprint 1.8)
- `.github/workflows/deploy-ingestion.yml` — **novo** (Sprint 1.8); workflow manual com checagem de "ciclo idle"

### Sequência segura de aplicação (importante)

Mover `ingestion_worker` de um stack para outro com `--prune` é delicado. Ordem segura:

1. Aplicar **1.4, 1.5, 1.6** primeiro (mudanças in-place no `observador.yml`); validar 24h em produção
2. PR no `docker-stack-infra` que faz **simultaneamente**:
   - Renomeia `stacks/observador-ingestion.yml.draft` → `stacks/observador-ingestion.yml`
   - Remove o bloco `ingestion_worker` de `stacks/observador.yml`
   - Atualiza `.github/workflows/deploy.yml` para incluir filtro
   - Adiciona `.github/workflows/deploy-ingestion.yml`
3. Merge → CI/CD cria stack `observador-ingestion` e remove serviço de `observador` na mesma janela (downtime mínimo, < 1 min)
4. Validar `docker stack ls` mostra os 2 stacks; `docker service ps` mostra worker rodando no novo stack

## Secrets do GitHub a adicionar (Sprint 3.7)

- `INGESTION_TRIGGER_TOKEN` — token aleatório para auth do `/run-now`. Gerar com `openssl rand -hex 32`

## Tabelas que serão criadas/alteradas

- **Novas:** `staging_<tld>`, `staging_removed_<tld>` (Sprint 2.1) — uma por TLD listado em `ingestion_tld_policy`
- **Nova:** `ingestion_cycle` (Sprint 3.1)
- **Nova view:** `tld_health_v` (Sprint 3.4)

## Tabelas existentes consultadas

- `ingestion_run` — registro por (source, tld, snapshot_date) — origem da view de saúde
- `ingestion_tld_policy` — fonte de verdade dos TLDs ativos; usada pela migration de staging
- `domain` — pai particionado por LIST(tld); permanece intacta no esquema
- `domain_<tld>` — partições; permanecem com índices ativos durante load (mudança vs hoje)
- `domain_removed_<tld>` — idem

## Comandos de operação

```bash
# Stack de ingestão isolado (após Sprint 1.7)
docker stack deploy -c infra/stack.ingestion.yml obs_ingestion

# Provisioning manual de novo TLD
docker exec -it obs_ingestion_worker.1.* python -m ingestion.provisioning.provision_tld --tld br

# Disparar ciclo via UI: /admin/ingestion → botão "Disparar ciclo"
# Disparar ciclo via API:
curl -X POST -H "X-Ingestion-Token: $TOKEN" http://obs_ingestion_worker:8080/run-now
```

## Reparos pontuais Sprint 1.2 (P14)

Plano detalhado para `domain_xn__yfro4i67o` (catalog inconsistente, 0 colunas em `pg_attribute`):

```sql
-- 1. Confirmar inconsistência
SELECT count(*) FROM pg_attribute WHERE attrelid = 'domain_xn__yfro4i67o'::regclass AND attnum > 0;
-- esperado: 0 (problema)

-- 2. DETACH via catálogo (não via ALTER, que falha)
SET allow_system_table_mods = on;
DELETE FROM pg_inherits WHERE inhrelid = 'domain_xn__yfro4i67o'::regclass;
SET allow_system_table_mods = off;

-- 3. DROP TABLE (agora possível)
DROP TABLE domain_xn__yfro4i67o;

-- 4. Próxima run recria via FULL_RUN ou LOAD_ONLY
```

## Catálogo PostgreSQL relevante (apenas para debugging)

A partir do Sprint 2, **nenhuma operação rotineira** deve precisar consultar estas tabelas. Mantidas aqui só como referência para o reparo único do Sprint 1.

- `pg_class.relispartition`
- `pg_inherits` (relação pai-filho)
- `pg_constraint.coninhcount`, `conislocal`, `conparentid`
- `pg_attribute` (colunas)
- `pg_depend` (dependências)
