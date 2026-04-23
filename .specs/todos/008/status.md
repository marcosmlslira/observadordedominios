# 008 — Status

## Titulo
Pipeline de Ingestão Automatizado: Orquestrador + Observabilidade

## Status: todo

## Fases

| Fase | Descrição | Status |
|------|-----------|--------|
| 0 | Deprecar pipeline legado (sync_czds_tld, sync_openintel_tld) + seed TLD policies | todo |
| 1 | Conectar `ingestion_run` ao pipeline (run_recorder.py) | todo |
| 2 | Orquestrador CLI (`orchestrate` + roteamento local/Databricks) | todo |
| 3 | Scheduler Docker (APScheduler + serviço obs_ingestion_worker) | todo |
| 4 | Pós-ingestão: trigger similarity scan + expiração de ameaças + limpeza R2 | todo |
| 5 | Painel admin complementar (TLD table + ciclo diário) | todo |

## Última atualização
2026-04-23

## Notas
- Plano revisado com 7 problemas críticos identificados e resolvidos
- Adicionada Fase 0 (deprecar legado) e Fase 4 (similarity + cleanup)
- Roteamento local vs Databricks adicionado à Fase 2
- Diagnóstico de aderência expandido com novos gaps
- `ingestion/` é o motor canônico; backend `sync_*` são legado
- Dependências: 0→1→2→3 (sequencial); 4 e 5 paralelas após Fase 2
