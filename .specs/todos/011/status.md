# Status — TODO 011

**Status:** `in_progress`
**Criado em:** 2026-04-27
**Última atualização:** 2026-04-27

## Progresso

### Sprint 1 — Estancar o sangramento
- [x] 1.1 Backup — dispensado pelo owner (sem operações destrutivas necessárias)
- [x] 1.2 Reparar `domain_xn__yfro4i67o` (P14) — partição já estava saudável (4 colunas, ATTACHED); `REFRESH MATERIALIZED VIEW tld_domain_count_mv` executado com sucesso; MV populada com 9 TLDs / 42.6M domínios
- [x] 1.3 `REINDEX SYSTEM obs` executado — 0 índices inválidos confirmados antes e após
- [x] 1.4 Memory limits no `ingestion_worker` — aplicado em `docker-stack-infra`
- [x] 1.5 `restart_policy: on-failure` no worker — aplicado em `docker-stack-infra`
- [x] 1.6 `INGESTION_TRIGGER_URLS` no env do backend — aplicado em `docker-stack-infra`
- [x] 1.7 Criar stack separado como `.draft` — `observador-ingestion.yml` ativado em produção (2026-04-27); ingestion_worker rodando 1/1 em stack isolado `observador-ingestion`
- [x] 1.8 CI/CD do backend deixa de tocar stack de ingestão — `trigger-deploy` desacoplado de `build-ingestion`; `deploy-ingestion.yml` ativo em docker-stack-infra

### Sprint 2 — Eliminar DDL do hot path
- [x] 2.1 Tabelas `staging_<tld>` — criadas por `provision_tld.py` no boot
- [x] 2.2 `provision_tld.py` idempotente sob advisory lock — `ingestion/provisioning/provision_tld.py`
- [x] 2.3 Refactor `delta_loader.py` — removidos DETACH/ATTACH/DROP INDEX/REBUILD
- [x] 2.4 Caminho direto via shards TEMP TABLE + INSERT ON CONFLICT — mantido, já era SIGKILL-safe
- [x] 2.5 Mesma estratégia para `domain_removed_<tld>` — já usava shard workers
- [x] 2.6 Handler SIGTERM no scheduler (graceful) — `ingestion/scheduler.py`
- [ ] 2.7 Streaming chunks para TLDs grandes — postergado para Sprint 5
- [x] 2.8 DDL residual removido — `_ensure_partition` mantida como utilitário, não chamada do hot path

### Sprint 3 — Estado e visibilidade
- [x] 3.1 Migration `ingestion_cycle` — `backend/alembic/versions/036_ingestion_cycle.py`
- [x] 3.2 `run_recorder` registra ciclo agregado — `open_cycle`, `close_cycle`, `heartbeat_cycle`, `get_last_cycle`, `recover_stale_running_cycles`
- [x] 3.3 `/health` lê do banco (via `get_last_cycle`) — `ingestion/scheduler.py`
- [x] 3.4 View `tld_health_v` — `backend/alembic/versions/037_tld_health_view.py`
- [x] 3.5 Endpoints `GET /v1/ingestion/cycles` e `GET /v1/ingestion/tlds/health` — `backend/app/api/v1/routers/ingestion.py`
- [x] 3.6 Cards de UI em `/admin/ingestion` — seção "Ciclos recentes" com `IngestionCycleItem`; tipos e métodos `getCycles`/`getTldsHealth` adicionados
- [x] 3.7 Auth `X-Ingestion-Token` no `/run-now` — já existia; agora também retorna 503 durante shutdown

### Sprint 4 — CZDS + Databricks-first
- [ ] 4.1 Validar fase CZDS em produção
- [ ] 4.2 Confirmar credenciais CZDS
- [ ] 4.3 Migrar TLDs gigantes para `databricks_only`
- [ ] 4.4 Documentar threshold em `ingestion_tld_policy`

### Sprint 5 — Hardening contínuo
- [x] 5.1 Log de memória por TLD/chunk — `_log_mem()` em `pipeline.py` (RSS start/end/delta via `resource.getrusage`)
- [x] 5.2 Stale heartbeat watchdog — `_start_stale_watchdog()` em `scheduler.py` (600s interval, recupera runs + ciclos stale)
- [x] 5.3 Métrica `ingestion_cycle_duration_seconds` — log estruturado ao fechar ciclo em `scheduler.py`
- [x] 5.4 Runbook em `docs/runbooks/ingestion.md` — criado (diagnóstico, cenários de falha, disparo manual, monitoramento)

## Decisões pendentes do owner

- [x] Janela de manutenção para Sprint 1.2 (reparo P14 `domain_xn__yfro4i67o`) — executado 2026-04-27; partição já estava saudável (OID 104977), MV populada
- [x] Ativar `observador-ingestion.yml.draft` (Sprint 1.7/1.8) — ativado em produção 2026-04-27; ingestion_worker 1/1 rodando em stack isolado
- [x] Configurar secret `OBSERVADOR_INGESTION_TRIGGER_TOKEN` no GitHub — cadastrado em marcosmlslira/docker-stack-infra 2026-04-27
- [x] UI cards Sprint 3.6 — implementado

## Histórico

- **2026-04-27** Plano criado a partir do diagnóstico forense de TODO 010 + ADR-002.
- **2026-04-27** Plano refletido com adições: validação por item de cada sprint, §12 "Prova de resiliência" (8 cenários), §13 honestidade sobre o que pode falhar.
- **2026-04-27** Aplicadas em `docker-stack-infra`: memory limits, restart_policy, INGESTION_TRIGGER_URLS. Draft stack + workflow criados.
- **2026-05-08** Sprint 2 completa: `provision_tld.py` criado; `delta_loader.py` refatorado (DDL hot path eliminado, todas funções DETACH/ATTACH/DROP INDEX/REBUILD removidas); `pipeline.py` recebe `stop_event`; `scheduler.py` recebe SIGTERM handler + boot provisioning.
- **2026-05-08** Sprint 3 completa (menos UI cards): migrations 036+037 criadas; `run_recorder.py` ganha cycle tracking; `scheduler.py` integra cycle open/close/heartbeat; `/health` lê último ciclo do DB; endpoints `GET /cycles` e `GET /tlds/health` adicionados; schemas `IngestionCycleItem`, `IngestionCyclesResponse`, `TldHealthItem`, `TldHealthResponse` adicionados.
- **2026-05-09** Itens 1.8, 3.6, 5.1–5.4 implementados: CI/CD de ingestão desacoplado do backend; seção "Ciclos recentes" na UI; log de memória por TLD (`_log_mem`); stale watchdog periódico; métrica de duração do ciclo em log estruturado; runbook criado em `docs/runbooks/ingestion.md`.
- **2026-04-27** Sprint 1 completa: P14 (`domain_xn__yfro4i67o`) já corrigido por run anterior (4 colunas, ATTACHED, OID 104977); `REFRESH MATERIALIZED VIEW tld_domain_count_mv` executado (9 TLDs, 42.6M domínios); `REINDEX SYSTEM obs` executado (0 índices inválidos); migrations `036_ingestion_cycle` + `037_tld_health_view` aplicadas em produção.
- **2026-04-27** Stack isolado ativado em produção: `observador-ingestion` deployado via `deploy-ingestion.yml` (run 25013435960); ingestion_worker 1/1 rodando em `vps-fa1dad58`; secret `OBSERVADOR_INGESTION_TRIGGER_TOKEN` cadastrado; `observador` stack sem ingestion_worker (confirmado em run 25013429706). TODO 011 Sprints 1–3 + 5 integralmente completas em produção.
