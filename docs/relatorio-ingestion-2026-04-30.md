# Relatório de investigação — Ingestion (30/04/2026)

## Escopo
Investigar por que a tela `/admin/ingestion` mostra percentual de 100% no dia **30/04/2026** mesmo com vários TLDs não ingeridos no heatmap (ex.: `.abb`, `.agency`, `.ch`) e com volume total ingerido muito abaixo do esperado (ex.: ausência de `.com` no dia).

## Fontes analisadas
- Evidências de auditoria já coletadas localmente: `.tmp_ingestion_audit_output.txt` e SQLs auxiliares.
- Backend da API de ingestão e view de base do heatmap.
- Frontend da página administrativa de ingestão.
- Código do worker/scheduler de ingestão.

Limitação: nesta sessão, as variáveis `PROD_HOST`, `PROD_USER` e `PROD_PASSWORD` não estavam configuradas, então a investigação não consultou logs produtivos ao vivo. As causas abaixo foram inferidas a partir do código e dos artefatos de auditoria disponíveis no workspace.

## Achados principais

### 1) O “%” mostrado no cabeçalho do heatmap não usa o total de TLDs habilitados
O percentual diário exibido na UI é calculado com base em `daily-summary`, que por sua vez agrega apenas linhas existentes em `tld_daily_status_v` para aquele dia.

Consequência:
- Se no dia houver poucos TLDs com linha na view e todos com `pg_ok`, o cálculo pode bater 100%.
- TLDs habilitados sem qualquer linha no dia simplesmente não entram no denominador.

Evidência de código:
- Backend daily summary usa `FROM tld_daily_status_v v` e `count(*) AS tld_total`: [ingestion.py](/C:/PROJETOS/observadordedominios/backend/app/api/v1/routers/ingestion.py:1259), [ingestion.py](/C:/PROJETOS/observadordedominios/backend/app/api/v1/routers/ingestion.py:1283)
- Frontend usa esse `tld_total` para o `%` diário: [page.tsx](/C:/PROJETOS/observadordedominios/frontend/app/admin/ingestion/page.tsx:497), [page.tsx](/C:/PROJETOS/observadordedominios/frontend/app/admin/ingestion/page.tsx:502), [page.tsx](/C:/PROJETOS/observadordedominios/frontend/app/admin/ingestion/page.tsx:509)

### 2) A `tld_daily_status_v` só contém TLD com execução registrada
A view é derivada de `ingestion_run`; ela não materializa “todos os TLDs habilitados por política”.

Consequência:
- TLD habilitado sem run no dia fica invisível para o cálculo de cobertura diária.
- O heatmap e o percentual diário podem divergir da expectativa operacional de “cobertura total de política”.

Evidência de código:
- Criação da view e origem em `ingestion_run`: [039_tld_daily_status_view.py](/C:/PROJETOS/observadordedominios/backend/alembic/versions/039_tld_daily_status_view.py:25), [039_tld_daily_status_view.py](/C:/PROJETOS/observadordedominios/backend/alembic/versions/039_tld_daily_status_view.py:41), [039_tld_daily_status_view.py](/C:/PROJETOS/observadordedominios/backend/alembic/versions/039_tld_daily_status_view.py:74)

### 3) A cobertura operacional real está muito abaixo do esperado
Na auditoria coletada:
- TLDs habilitados: `czds=1125`, `openintel=316` (total 1441).
- Sumário executivo indica praticamente sem atividade no dia da coleta e `% completo = 0.0` por fonte.
- Vários TLDs com última execução antiga e fora do limiar.

Evidências (arquivo de auditoria):
- `SECTION:layer0_openintel_enabled`, `SECTION:layer1_coverage_today`, `SECTION:executive_summary`.
- `SECTION:layer4_days_since_last_success` com vários TLDs defasados.

## Casos solicitados (amostra)

### `.com` (CZDS)
- Aparece com `last_ok_date = 2026-04-26` e `dias_sem_run = 3` na auditoria.
- Indica ausência de sucesso no dia-alvo (30/04/2026).

### `.abb` (CZDS)
- Também aparece com `last_ok_date = 2026-04-26` e fora do limiar.

### `.agency` (CZDS)
- Também aparece com `last_ok_date = 2026-04-26` e fora do limiar.

### `.ch` (OpenINTEL)
- Aparece em `layer2_r2ok_pg_not_success` com `pg_status = running` e snapshot antigo (`2026-04-15`).
- Também aparece com `dias_sem_run` alto na camada de aging.

## Causa-raiz consolidada
1. **Causa de apresentação/métrica:** o percentual mostrado no topo reflete apenas o subconjunto com registros na `tld_daily_status_v` naquele dia, não a cobertura contra a política habilitada.
2. **Causa operacional:** há grande backlog de TLDs habilitados sem sucesso recente (inclusive TLDs críticos), evidenciando que o ciclo diário não está cobrindo o universo habilitado.

## Investigacao operacional dos TLDs faltantes

### O que significa "faltante" hoje
Um TLD faltante nao significa necessariamente que ele tentou executar e falhou. Pela implementacao atual, muitos faltantes sao TLDs habilitados que nao chegaram a ter uma tentativa registrada no dia.

O worker so cria uma linha em `ingestion_run` quando o TLD comeca a executar:
- caminho local: `_process_tld_local()` chama `create_run()`;
- caminho Databricks: `_submit_databricks_batch()` ou o fluxo solo do `.com` cria a linha `phase='r2'`;
- TLDs que ainda nao chegaram na vez, ou que ficaram atras de uma interrupcao, nao ganham registro proprio.

Referencia: [pipeline.py](/C:/PROJETOS/observadordedominios/ingestion/ingestion/orchestrator/pipeline.py:204), [pipeline.py](/C:/PROJETOS/observadordedominios/ingestion/ingestion/orchestrator/pipeline.py:468), [run_recorder.py](/C:/PROJETOS/observadordedominios/ingestion/ingestion/observability/run_recorder.py:38)

### Como o ciclo decide a ordem
O ciclo diario executa nessa ordem:
- OpenINTEL primeiro.
- CZDS depois.
- Dentro de cada fonte, os TLDs vem de `ingestion_tld_policy`, ordenados por `priority` e `tld`.
- TLDs grandes rodam em Databricks; `.com` e sempre solo e por ultimo no CZDS.

Referencia: [scheduler.py](/C:/PROJETOS/observadordedominios/ingestion/scheduler.py:294), [pipeline.py](/C:/PROJETOS/observadordedominios/ingestion/ingestion/orchestrator/pipeline.py:138), [pipeline.py](/C:/PROJETOS/observadordedominios/ingestion/ingestion/orchestrator/pipeline.py:619), [submitter.py](/C:/PROJETOS/observadordedominios/ingestion/ingestion/databricks/submitter.py:20)

### Por que os faltantes nao executaram
A explicacao mais consistente com os dados e com o codigo e:

1. O ciclo nao percorreu todo o universo habilitado.
2. Parte dos TLDs ficou simplesmente "nao alcancada", sem linha em `ingestion_run`.
3. Como esses TLDs nao tiveram tentativa, o sistema atual nao consegue mostrar um erro por TLD; ele so mostra ausencia.

Evidencias da auditoria local:
- Habilitados: `czds=1125`, `openintel=316`.
- No recorte auditado, `czds` tinha `1124` TLDs sem atividade no dia e `openintel` tinha `315`.
- A visao dual-phase do dia tinha apenas `1` CZDS em falha e `1` OpenINTEL rodando.
- `.abb`, `.agency` e `.com` aparecem com ultimo sucesso em `2026-04-26`; `.ch` aparece com ultimo sucesso em `2026-04-15`.

Isso aponta para um problema de cobertura do ciclo, nao para falhas independentes em mais de 500 TLDs.

### Pontos do codigo que favorecem esse comportamento
- O `SIGTERM` seta `stop_event`; o loop de pequenos TLDs para com `break`, mas os TLDs restantes nao sao persistidos como `not_reached`.
- `ingestion_cycle` registra contadores agregados, mas nao registra o plano por TLD; alem disso, `open_cycle()` e chamado sem `tld_total`, entao a linha do ciclo pode nascer sem o denominador.
- O endpoint `cycle-status` calcula CZDS a partir de `czds_tld_policy`, enquanto o ciclo canonico usa `ingestion_tld_policy`; isso pode gerar divergencia de totais e status.
- `cycle-status` busca apenas `limit=500` runs CZDS antes de filtrar o dia, o que pode esconder parte do ciclo em dias com muitas execucoes.
- A recuperacao CZDS usa `status = 'done'`, mas as execucoes bem-sucedidas usam `status = 'success'`; esse bug faz a recuperacao considerar que CZDS nao rodou mesmo quando rodou.

Referencias: [scheduler.py](/C:/PROJETOS/observadordedominios/ingestion/scheduler.py:47), [pipeline.py](/C:/PROJETOS/observadordedominios/ingestion/ingestion/orchestrator/pipeline.py:850), [run_recorder.py](/C:/PROJETOS/observadordedominios/ingestion/ingestion/observability/run_recorder.py:167), [run_recorder.py](/C:/PROJETOS/observadordedominios/ingestion/ingestion/observability/run_recorder.py:310), [ingestion.py](/C:/PROJETOS/observadordedominios/backend/app/api/v1/routers/ingestion.py:474), [ingestion.py](/C:/PROJETOS/observadordedominios/backend/app/api/v1/routers/ingestion.py:480)

## Propostas para tracking mais apurado

### 1) Registrar o plano do ciclo por TLD
Criar uma tabela `ingestion_cycle_tld` com uma linha por `(cycle_id, source, tld)` no inicio do ciclo.

Campos recomendados:
- `cycle_id`, `source`, `tld`, `priority`, `planned_position`
- `planned_phase`: `skip`, `load_only`, `full_run`
- `execution_status`: `planned`, `running`, `success`, `failed`, `skipped`, `not_reached`, `interrupted`
- `blocked_by_source`, `blocked_by_tld`
- `reason_code`, `error_message`
- `r2_run_id`, `pg_run_id`, `databricks_run_id`, `databricks_run_url`
- `r2_marker_date`, `snapshot_date`, `started_at`, `finished_at`, `duration_seconds`

Beneficio: o painel passa a dizer "nao executou porque o ciclo foi interrompido antes dele", em vez de apenas mostrar pendente/ausente.

### 2) Fechar pendentes ao interromper ciclo
Quando `stop_event` ou erro fatal acontecer, todos os itens ainda em `planned` devem ser atualizados para:
- `execution_status='not_reached'`
- `reason_code='cycle_interrupted'`, `worker_shutdown`, `previous_phase_blocked` ou `source_crashed`

Beneficio: TLDs como `.com`, que ficam no fim, deixam de parecer um mistério operacional.

### 3) Separar cobertura por atividade de cobertura por politica
Adicionar uma view daily baseada em `ingestion_tld_policy` como denominador:
- `enabled_total`
- `attempted_today`
- `success_today`
- `failed_today`
- `not_started_today`
- `policy_coverage_pct`

Beneficio: o `100%` atual deixa de mascarar TLDs habilitados que nao foram alcançados.

### 4) Persistir detalhes de Databricks
Gravar em banco:
- `run_page_url`
- `result_state`
- `notebook_result`
- `notebook_output` resumido
- lista de TLDs por batch
- contrato R2: marker presente, parquet presente, contagem de arquivos

Beneficio: diferenciar claramente `databricks_submit_error`, `databricks_run_error`, `r2_marker_missing`, `databricks_contract_violation` e `pg_load_error`.

### 5) Corrigir inconsistencias imediatas
- Trocar `status = 'done'` por `status = 'success'` em `czds_ran_today()`.
- Passar `tld_total` para `open_cycle()`.
- Fazer `cycle-status` usar `ingestion_tld_policy` e remover o limite fixo de `500` runs para o calculo do dia.
- Adicionar status visual `not_started/not_reached` no heatmap.
- Exibir denominador explicito: `463 / 1441` em vez de apenas percentual.

### 6) Alertas recomendados
- TLD critico sem sucesso por mais de 1 dia: `.com`, `.net`, `.org`, `.info`, `.br`, `.ch`.
- `not_reached_today > 0`.
- ciclo `interrupted` ou `running` sem heartbeat recente.
- OpenINTEL travado impedindo inicio do CZDS.
- Databricks batch sem marker R2 para qualquer TLD esperado.

## Queries recomendadas para fechamento do incidente

```sql
-- TLDs habilitados que nao tiveram nenhuma tentativa no dia
WITH enabled AS (
  SELECT source, tld, priority
  FROM ingestion_tld_policy
  WHERE is_enabled = true
),
attempted AS (
  SELECT DISTINCT source, tld
  FROM ingestion_run
  WHERE started_at::date = DATE '2026-04-30'
)
SELECT e.source, e.tld, e.priority
FROM enabled e
LEFT JOIN attempted a ON a.source = e.source AND a.tld = e.tld
WHERE a.tld IS NULL
ORDER BY e.source, e.priority, e.tld;
```

```sql
-- Classificacao por status no dia usando politica como denominador
WITH enabled AS (
  SELECT source, tld, priority
  FROM ingestion_tld_policy
  WHERE is_enabled = true
),
day_runs AS (
  SELECT DISTINCT ON (source, tld)
    source, tld, phase, status, reason_code, error_message, started_at, finished_at
  FROM ingestion_run
  WHERE started_at::date = DATE '2026-04-30'
  ORDER BY source, tld, started_at DESC
)
SELECT
  e.source,
  COUNT(*) AS enabled_total,
  COUNT(d.tld) AS attempted,
  COUNT(*) FILTER (WHERE d.status = 'success') AS success,
  COUNT(*) FILTER (WHERE d.status = 'failed') AS failed,
  COUNT(*) FILTER (WHERE d.status = 'running') AS running,
  COUNT(*) FILTER (WHERE d.tld IS NULL) AS not_started
FROM enabled e
LEFT JOIN day_runs d ON d.source = e.source AND d.tld = e.tld
GROUP BY e.source
ORDER BY e.source;
```

```sql
-- Ultimo sucesso dos TLDs criticos
SELECT p.source, p.tld, p.priority,
       MAX(r.finished_at)::date AS last_success_date
FROM ingestion_tld_policy p
LEFT JOIN ingestion_run r
  ON r.source = p.source
 AND r.tld = p.tld
 AND r.status = 'success'
WHERE p.tld IN ('com', 'net', 'org', 'info', 'abb', 'agency', 'ch')
GROUP BY p.source, p.tld, p.priority
ORDER BY p.source, p.priority, p.tld;
```

## Impacto
- O indicador de “100%” pode transmitir falso positivo operacional.
- Risco de perda de cobertura em TLDs relevantes (inclusive `.com`) mesmo com UI aparentemente “verde”.

## Recomendações objetivas
1. Alterar o cálculo do `%` diário para usar `ingestion_tld_policy (is_enabled=true)` como denominador, cruzando com sucesso no dia.
2. Exibir dois indicadores separados na UI:
   - `% execução do dia (activity-based)`
   - `% cobertura sobre política habilitada (policy-based)`
3. Criar alerta explícito para TLD habilitado sem sucesso há `N` dias (ex.: CZDS > 2 dias, OpenINTEL > 7 dias).
4. Priorizar reprocessamento imediato de TLDs críticos fora do limiar (`.com`, `.net`, `.org`, `.info`, etc.).
5. Publicar no painel um “backlog de TLDs habilitados sem run no dia” para evitar interpretação incorreta do 100%.

## Observação de método
Este relatório foi produzido com base em evidências locais de auditoria e no código da aplicação. Para fechamento final de incidente em produção, recomenda-se reexecutar as queries diretamente no banco produtivo do dia **30/04/2026** e anexar o resultado bruto no ticket.
