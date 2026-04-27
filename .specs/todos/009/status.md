# 009 — Status

## Titulo
Correções de Confiabilidade no Monitoramento de Ingestão

## Status: in_progress

## Fases

| Fase | Descrição | Status |
|------|-----------|--------|
| 1 | Definição de contrato de "TLD funcional" | done |
| 2 | Backend: endpoint/consulta canônica de saúde | done |
| 3 | OpenINTEL: consistência da fonte de status | done |
| 4 | Frontend: separação visual de execução vs funcionalidade | done |
| 5 | Testes + validação operacional | in_progress |
| 6 | Recuperação automática de carga parcial | in_progress |

## Correções aplicadas (2026-04-27)

### A1 — Idempotência do loader ✅
- **Arquivo:** `ingestion/loader/delta_loader.py`
- **Mudança:** `_load_shard_worker` agora usa `COPY → temp table → INSERT ON CONFLICT DO NOTHING` em vez de `COPY` direto na partição
- **Efeito:** Reruns do mesmo `(source, tld, snapshot_date)` não falham mais com `duplicate key value violates unique constraint`
- **Corrige:** Incidente 4 (openintel/at duplicate key)

### A2 — Sanitização de `removed_day` nulo ✅
- **Arquivo:** `ingestion/loader/delta_loader.py`
- **Mudança:** Quando `removed_day` está null no parquet, o loader substitui pelo `snapshot_date` (added_day) antes do COPY
- **Efeito:** Cargas de `domain_removed` não falham mais com `null value in column "removed_day" violates not-null constraint`
- **Corrige:** Incidentes 3 (.com e .blog removed_day nulo) e 7 (carga parcial)

### A3 — Reconciliação `openintel_tld_status` ✅
- **Arquivo:** `ingestion/orchestrator/pipeline.py`
- **Mudança:** Nova função `_reconcile_openintel_status()` chamada após `finish_run(status="success")` em ambos os caminhos (local e Databricks)
- **Efeito:** Após sucesso de ingestão OpenINTEL, `openintel_tld_status` é atualizado com `ingested_new_snapshot` e o `last_ingested_snapshot_date` correto
- **Corrige:** Incidente 5 (openintel/ae sucesso sem reconciliação)

### B1 — Batch-size configurável para Databricks ✅
- **Arquivos:** `ingestion/config/settings.py`, `ingestion/orchestrator/pipeline.py`
- **Mudança:**
  - Novos settings: `DATABRICKS_BATCH_SIZE_OPENINTEL` (default=50), `DATABRICKS_BATCH_SIZE_CZDS` (default=100)
  - Método helper: `cfg.databricks_batch_size_for_source(source)`
  - Pipeline agora chunka batches em ambos os modos (`databricks_only` e `hybrid`)
- **Efeito:** Batches são limitados a 50 TLDs (OpenINTEL) e 100 TLDs (CZDS) por job Databricks
- **Corrige:** Incidentes 1 (OOM 302 TLDs) e 2 (rate-limit 1101 TLDs)

## Itens pendentes

| # | Item | Fase | Status |
|---|------|------|--------|
| B2 | Token reuse para CZDS no notebook Databricks | B | pendente (requer alteração no notebook) |
| B3 | Validação pós-Databricks (checar parquets + marker) | B | pendente |
| C1 | Separar `never_attempted` de `no_run_today` no tld-status | C | pendente |
| C2 | Timezone canônico (UTC vs local) | C | pendente |
| C3 | Marker R2 no tld-status (marker_present/phase inferida) | C | pendente |
| C4 | Estado de carga parcial na UI | C | pendente |
| D1 | Retry parcial (removed-only quando added ok) | D | pendente |
| D2 | Reason codes estendidos | D | pendente |
| E1 | Teste de idempotência do loader | E | pendente |
| E2 | Teste de sanitização removed_day | E | pendente |
| E3 | Teste de carga parcial + recovery | E | pendente |
| E4 | Teste de stale recovery | E | pendente |

## Última atualização
2026-04-27

## Notas
- Item criado a partir de validação em tempo real da ingestão.
- Prioridade alta por impacto direto na observabilidade operacional.
- Inclui correção de falso positivo no card "Executando agora" causado por `ingestion_run` órfão em `running`.
- 2026-04-26: migração aplicada (`035_ingestion_run_reason_code`) e ciclo manual real validado em ambiente local.
- 2026-04-26: Fase A habilitada no worker local (`INGESTION_EXECUTION_MODE_OPENINTEL=databricks_only`, `INGESTION_EXECUTION_MODE_CZDS=hybrid`) com escopo reduzido (`*_MAX_TLDS=2`).
- 2026-04-26: stale recovery validado com run artificial `openintel/staletest` -> `failed` + `reason_code=stale_recovered`.
- Achado operacional catalogado: histórico OpenINTEL com múltiplas falhas legadas contendo `last_error_message="'DomainRepository' object has no attribute 'bulk_upsert'"`.
- 2026-04-26: Fase B iniciada localmente (`INGESTION_EXECUTION_MODE_OPENINTEL=databricks_only`, `INGESTION_EXECUTION_MODE_CZDS=databricks_only`) sem `OPENINTEL_MAX_TLDS`/`CZDS_MAX_TLDS`.
- 2026-04-26 06:01:29Z: ciclo manual aceito e iniciado com escopo completo (`run_cycle source=openintel mode=databricks_only total=304` no worker log).
- Achado novo de observabilidade: durante a varredura de markers em lote grande, o ciclo pode ficar ativo sem refletir `ingestion_run` em `running`, mantendo `/v1/ingestion/summary.running_active_count=0` apesar de execução em andamento.
- 2026-04-26: correção aplicada para esse gap: worker passou a expor `current_phase` em `/health`, e o backend `/v1/ingestion/summary` agora combina heartbeat do worker com `ingestion_run` para calcular `running_active_count`.
- 2026-04-27: novo item priorizado adicionado ao TODO: recuperação automática de carga parcial (sem ação manual) quando Databricks finalizar com sucesso e falhar apenas o `load_delta` (ex.: `domain_removed` com `removed_day` nulo).
- 2026-04-27: incidentes de Databricks documentados em detalhe em `references.md`, com `run_id`, mensagens exatas, links, hipóteses e pedidos explícitos de ajuda para investigação externa.
- 2026-04-27: novo achado de semântica/UI catalogado: o `/admin/ingestion` pode exibir histórico em dias como `23/04` no heatmap e, ao mesmo tempo, rotular o TLD como `Sem execução`, porque o heatmap usa `/v1/ingestion/runs` agrupado por dia local do navegador, enquanto o status atual usa `/v1/ingestion/tld-status` com recorte de "hoje" em UTC. Isso precisa ser corrigido para diferenciar claramente `sem execução hoje` de `sem histórico de tentativa`.
- 2026-04-27: novo gap de observabilidade catalogado: o `/admin/ingestion` ainda não expõe, de forma unificada, a existência de marker R2 por `source + tld + snapshot_date`. Hoje há visibilidade parcial apenas para OpenINTEL via `last_available_snapshot_date`, mas não existe um contrato geral para CZDS/OpenINTEL que permita auditar explicitamente `marker presente`, `marker ausente`, `snapshot do marker` e `marker presente sem carga confirmada no PostgreSQL`.
- 2026-04-27: bug real catalogado durante teste local de TLD único: `openintel/at` apareceu no `/admin/ingestion`, mas o rerun em `FULL_RUN` falhou no loader com `duplicate key value violates unique constraint "domain_at_pkey"` ao tentar reaplicar `delta_added`. Isso evidencia falha de idempotência do `load_delta` e bloqueia recuperações seguras via `LOAD_ONLY`/rerun do mesmo snapshot.
- 2026-04-27: teste real bem-sucedido de TLD único concluído com `openintel/ae` (`run_id=33fa4fee-86e8-45ab-832a-e13de79f31b4`, `status=success`, `snapshot_date=2026-04-20`, `domains_inserted=140830`), confirmando que o fluxo ponta a ponta consegue aparecer corretamente no `/admin/ingestion` quando não encontra conflito de idempotência no loader.
- 2026-04-27: novo bug de consistência catalogado: após o sucesso real de `openintel/ae`, o `ingestion_run` foi persistido corretamente e `domain_ae` recebeu `140830` linhas, mas `openintel_tld_status` permaneceu stale (`last_ingested_snapshot_date=NULL`, `last_probe_outcome=new_snapshot_pending_or_failed`, erro legado de `bulk_upsert`). Isso faz o `/admin/ingestion` continuar mostrando estado incorreto mesmo com ingestão concluída.
- 2026-04-27: teste Databricks isolado de `openintel/ag` concluiu com run remoto `SUCCESS`, mas o pipeline falhou localmente com `reason_code=r2_marker_missing` (`R2 marker missing after Databricks run — TLD likely failed in notebook`). Isso mostra um gap no contrato Databricks -> R2 -> loader: sucesso remoto nao garante marker consumivel pelo PostgreSQL.
- 2026-04-27: teste Databricks isolado de `czds/blog` concluiu com run remoto `SUCCESS`, carregou parcialmente `domain_blog` (`490` rows, `added_day=20260427`), mas falhou no `domain_removed_blog` com `reason_code=pg_load_error` por `removed_day` nulo. Isso confirma o problema de carga parcial tambem em TLD pequeno, nao apenas no caso `.com`.
- 2026-04-27: **correções A1, A2, A3, B1 aplicadas** — idempotência do loader (staging table), sanitização de removed_day nulo, reconciliação openintel_tld_status, e batch-size configurável para Databricks.
