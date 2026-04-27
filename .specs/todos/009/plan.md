# 009 — Correções de Confiabilidade no Monitoramento de Ingestão

## Problema

O painel `/admin/ingestion` é útil para acompanhar execução, mas hoje mistura sinais de naturezas diferentes para inferir se um TLD está funcional:

- `/v1/ingestion/tld-status` considera apenas execuções do dia (`started_at::date = today`), o que pode marcar `never_run` mesmo com TLD saudável em dias anteriores.
- `/v1/ingestion/openintel/status` depende de `openintel_tld_status`, cuja atualização precisa ser validada no fluxo canônico (`ingestion/`).
- `ingestion_run` com status `running` pode ficar órfão (stale) e inflar o card "Executando agora" sem ciclo ativo real.
- O heatmap usa esses sinais para status atual, podendo gerar leitura incorreta de saúde operacional.

## Objetivo

Separar claramente:

1. **Status do ciclo atual (hoje)**
2. **Saúde funcional real do TLD (último estado válido em janela configurável)**

## Escopo do TODO

- Definir contrato explícito para "TLD funcional" por fonte.
- Ajustar backend para expor status de saúde real por TLD (não limitado ao dia atual).
- Ajustar frontend para exibir separadamente "execução de hoje" e "saúde funcional".
- Validar OpenINTEL para garantir que o painel consuma apenas fonte atualizada pelo pipeline canônico.

## Fases

### Fase 1 — Definição de contrato e critérios
- Definir semântica de `functional_status` (ex.: `healthy`, `degraded`, `failed`, `unknown`).
- Definir janela de avaliação (ex.: últimas 24h/48h) por fonte.
- Definir regras para casos de `SKIP` idempotente e "sem snapshot novo".

### Fase 2 — Backend: endpoint/consulta canônica
- Evoluir `/v1/ingestion/tld-status` ou criar endpoint dedicado para saúde funcional.
- Remover dependência de filtro exclusivo por data do dia para inferir saúde.
- Garantir ordenação e filtros por `is_enabled`, `priority` e fonte.
- Tratar `running` stale no summary (ex.: ignorar/marcar como failed quando `updated_at` exceder timeout).
- Expor `running_now` real (ativo) separado de `running_stale_count` para observabilidade.

### Fase 3 — OpenINTEL: consistência da fonte de status
- Validar como `openintel_tld_status` é atualizado no fluxo atual de ingestão.
- Se necessário, ajustar pipeline canônico para persistir status de verificação/ingestão.
- Garantir aderência entre `openintel/status` e `ingestion_run`.
- Garantir reconciliação automática após sucesso real de ingestão:
  - se `ingestion_run` concluir `success` para `openintel`
  - então `openintel_tld_status.last_ingested_snapshot_date` e `last_probe_outcome` devem refletir esse sucesso
  - sem depender de um fluxo legado separado para "verificação".

### Fase 4 — Frontend: leitura correta no heatmap
- Exibir indicador separado para "rodando hoje" e "funcional".
- Evitar mapear `never_run` (do dia) como "não funcional" sem contexto.
- Revisar filtros e legenda para reduzir falso alerta.
- Corrigir a semântica de `Sem execução` quando existir histórico recente no heatmap, preferindo rótulos como `Sem execução hoje`.
- Alinhar a referência temporal entre backend e frontend:
  - `tld-status` hoje usa recorte UTC (`started_at::date = today`)
  - heatmap usa agrupamento por dia local do navegador
  - isso precisa ser unificado ou explicitado na UI para evitar contradições visuais.
- Destacar `last_run_at` / `last_status` como sinal primário de "houve tentativa recente", deixando `execution_status_today` como sinal secundário.
- Adicionar visibilidade unificada de marker R2 por `source + tld + snapshot_date`, não limitada ao OpenINTEL:
  - `marker_present`
  - `marker_snapshot_date`
  - `marker_checked_at`
  - fase inferida: `skip | load_only | full_run`
- Exibir claramente quando existe marker no R2 mas ainda não houve carga confirmada no PostgreSQL, para auditoria de casos `LOAD_ONLY`.

### Fase 5 — Testes e validação operacional
- Testes unitários de regras de classificação de saúde.
- Testes de API cobrindo casos: sucesso recente, skip idempotente, sem snapshot, falha recente.
- Teste específico para run órfão em `running` não aparecer como execução ativa.
- Checklist de validação durante janela de execução real (pré/durante/pós ciclo).

### Fase 6 — Recuperação automática de carga parcial (sem ação manual)
- Detectar falha de carga parcial quando Databricks terminar `SUCCESS` mas o `load_delta` falhar (`pg_load_error`).
- Implementar fallback automático `removed-only` quando apenas `domain_removed` falhar (ex.: `removed_day` nulo em parquet).
- Adicionar sanitização no loader para normalizar `removed_day` ausente/nulo para o `snapshot_date` da execução.
- Registrar reason codes explícitos de recuperação (`recovered_removed_only` / `recovery_failed`) para auditoria na API e UI.
- Evitar rerun Databricks em cenários de recuperação de carga, reaproveitando artefatos já persistidos no R2.
- Cobrir com testes automatizados: `added` ok + `removed` falha -> recuperação automática concluída.
- Corrigir a idempotência do `load_delta` para reruns do mesmo `source + tld + snapshot_date`:
  - hoje um rerun pode falhar com `duplicate key value violates unique constraint domain_<tld>_pkey`
  - isso impede recuperação segura via `LOAD_ONLY` quando o `delta_added` já foi parcialmente ou totalmente aplicado
  - o loader precisa tolerar reaplicação sem erro, preservando a semântica `ON CONFLICT DO NOTHING` do modelo append-only.
