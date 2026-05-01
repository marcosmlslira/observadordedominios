# Relatório de Investigação — Ingestion 30/04/2026

## Escopo
- Validar deploy/backend em produção.
- Validar endpoints de ingestão para 2026-04-30.
- Levantar causa dos TLDs faltantes e falhas `stale_recovered`.
- Validar hipótese de `days` vazio no heatmap.

## Evidências coletadas
- Serviço `observador_backend` forçado com sucesso (`docker service update --force observador_backend`) e convergido.
- Backend ativo em `1/1` com imagem `ghcr.io/marcosmlslira/observador-backend:latest` (digest atual: `sha256:bb71ca3a...`).
- `GET /v1/ingestion/heatmap?days=1` respondeu `200` e retornou `days: ["2026-04-30"]` e células por TLD.
- `GET /v1/ingestion/incidents?hours=24&limit=200` respondeu `200` e trouxe incidentes `stale_recovered` para TLDs críticos.
- `GET /v1/ingestion/policy-coverage?date=2026-04-30` respondeu `500`.

## Correção aplicada (produção)
- DDL aplicado diretamente no Postgres de produção:
  - criação da tabela `ingestion_cycle_tld` (não existia na base atual);
  - criação de índices relacionados (`ix_ict_cycle_status`, `ix_ict_source_tld`, `ix_ict_planned`, `ix_ict_cycle_day`);
  - criação/recriação da view `tld_daily_policy_status_v` com coluna `policy_status`.
- Resultado imediato:
  - endpoint `GET /v1/ingestion/policy-coverage` saiu de `500` para `200`.

## Causa raiz dos problemas

### 1) `policy-coverage` quebrado em produção
- Erro confirmado em log:
  - `psycopg2.errors.UndefinedTable: relation "tld_daily_policy_status_v" does not exist`
- Impacto:
  - endpoint `/v1/ingestion/policy-coverage` indisponível (500), impedindo leitura de cobertura planejado x executado.
- Causa:
  - view `tld_daily_policy_status_v` não existe no banco de produção (migração incompleta/parcial do objeto de banco).

### 2) TLDs críticos com `stale_recovered`
- Incidentes confirmados:
  - `czds`: `.net`, `.org`, `.info`, `.xyz`, `.shop`, `.top` (janela observada).
  - `openintel`: `.ch`.
- Mensagem padrão:
  - `Run recovered automatically after stale timeout`.
- Interpretação técnica:
  - o ciclo marca execução como "stale" após timeout operacional (janela de estagnação), antes da conclusão do processamento de TLDs pesados ou instáveis.
  - para CZDS/OpenINTEL grandes, o gargalo pode ocorrer em download/processamento e/ou carga PG.

### 3) Heatmap com `days` vazio
- Na validação atual (30/04/2026), o endpoint retornou `days` corretamente.
- Conclusão:
  - não foi reproduzido no backend atual.
  - provável ocorrência anterior em build/instância antiga durante rollout (havia histórico de resposta `404` em réplicas antigas para endpoint novo) ou leitura inconsistente no frontend.

## Estado dos TLDs citados pelo time
- `.com`: `ok`
- `.abb`: `ok`
- `.agency`: `ok`
- `.net`: `failed` (`stale_recovered`)
- `.org`: `failed` (`stale_recovered`)
- `.info`: `failed` (`stale_recovered`)
- `.ch` (openintel): `failed` (`stale_recovered`)

## Propostas de tracking (ação recomendada)

1. Criar tabela de eventos por fase (`r2_download_start/end`, `pg_load_start/end`, `checkpoint_write`) com `run_id`, `source`, `tld`, `duration_ms`, `rows_processed`, `error_code`.
2. Persistir heartbeats periódicos por run (ex.: a cada 30s) para distinguir "lento" de "travado".
3. Diferenciar reason codes de timeout:
   - `stale_r2_download`, `stale_pg_load`, `stale_postprocess`.
4. Incluir no incidente campos mínimos:
   - `phase`, `last_progress_at`, `bytes_downloaded`, `rows_loaded`, `retry_count`.
5. Expor endpoint de diagnóstico operacional por run:
   - `/v1/ingestion/runs/{run_id}/timeline`.
6. Ajustar timeout por perfil de TLD:
   - TLDs massivos (`com`, `net`, `org`, `info`, `xyz`, `shop`, `top`) com SLA maior que TLDs pequenos.
7. Alertas proativos:
   - alarme quando heartbeat sem progresso > N minutos por fase.
8. Dashboard de cobertura diária:
   - `enabled_total`, `attempted`, `success`, `failed`, `not_reached` por source, com drill-down em `run_id`.

## Checklist técnico para nova validação (API)

1. Login admin e obter token.
2. `GET /v1/ingestion/cycle-status` antes do trigger.
3. `POST /v1/ingestion/trigger/daily-cycle` e confirmar `accepted` ou `already_running`.
4. Poll `cycle-status` até finalizar.
5. Validar:
   - `GET /v1/ingestion/incidents?hours=24&limit=200`
   - `GET /v1/ingestion/heatmap?days=1`
   - `GET /v1/ingestion/tld-status?source=czds`
   - `GET /v1/ingestion/tld-status?source=openintel`
   - `GET /v1/ingestion/policy-coverage?date=YYYY-MM-DD` (deve sair de 500 após correção da view).
6. Critérios de aceite:
   - sem `500` no `policy-coverage`;
   - TLDs críticos com estado do dia rastreável;
   - redução consistente de `stale_recovered` nos TLDs de maior volume.

## Reexecução do checklist (após correção)

Data/hora da validação: 30/04/2026

1. `GET /health`
- Resultado: `ok`.

2. `GET /v1/ingestion/cycle-status`
- Resultado: ciclo CZDS ativo (`is_active: false` na amostra de resposta, porém `summary.running_now=1` indica processamento em curso no momento da janela), `completed_tlds: 464`, `total_tlds: 1097`.

3. `POST /v1/ingestion/trigger/daily-cycle`
- Resultado: `already_running` (esperado quando já existe ciclo em execução).

4. `GET /v1/ingestion/cycles?limit=1`
- Resultado: último ciclo fechado `interrupted` (ciclo de 29/04/2026).

5. `GET /v1/ingestion/summary`
- Resultado: `czds.running_now = 1`.

6. `GET /v1/ingestion/incidents?hours=2&limit=100`
- Resultado: sem incidentes na janela de 2h.

7. `GET /v1/ingestion/heatmap?days=1`
- Resultado: `200`, `days = ["2026-04-30"]`, `rows_count = 465`.

8. `GET /v1/ingestion/daily-summary?from_date=2026-04-30&to_date=2026-04-30`
- Resultado:
  - `czds`: `tld_total=464`, `pg_ok=463`, `pg_failed=1`, `pg_complete_pct=0.9978`.
  - `openintel`: `tld_total=1`, `pg_failed=1`.

9. `GET /v1/ingestion/policy-coverage?date=2026-04-30`
- Resultado: `200` com `items=[]` (sem erro).
- Interpretação: a view usa dias de ciclos fechados; para a data consultada não havia ciclo fechado correspondente na janela UTC, por isso não há linhas para agregar.

10. TLDs críticos (status)
- `czds`:
  - `ok`: `.com`, `.abb`, `.agency`, `.shop`, `.top`
  - `failed/stale_recovered`: `.net`, `.org`, `.info`, `.xyz`
- `openintel`:
  - `failed/stale_recovered`: `.ch`
