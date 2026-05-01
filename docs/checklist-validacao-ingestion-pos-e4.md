# Checklist Técnico — Validação das alterações de ingestão (API)

## Objetivo
Validar, via API, as alterações recentes de ingestão após disparo de ciclo manual, confirmando:
- execução do ciclo,
- rastreabilidade por TLD,
- cobertura de política vs execução,
- reason codes e diagnósticos esperados.

## Pré-requisitos
- Ambiente com backend atualizado e migrações aplicadas.
- Token de admin válido para API.
- Base URL da API de produção/homologação.

Exemplo de variáveis:
```bash
export API_BASE="https://api.observadordedominios.com.br"
export TOKEN="<admin_jwt>"
export H_AUTH="Authorization: Bearer $TOKEN"
```

## 1) Sanidade inicial (antes do ciclo)
1. Verificar saúde:
```bash
curl -s "$API_BASE/health"
```
Esperado: resposta `ok`.

2. Verificar status de ciclo:
```bash
curl -s -H "$H_AUTH" "$API_BASE/v1/ingestion/cycle-status"
```
Esperado: payload com `czds_cycle`, `schedules`, `health`.

3. Ler últimos ciclos:
```bash
curl -s -H "$H_AUTH" "$API_BASE/v1/ingestion/cycles?limit=5"
```
Esperado: lista não vazia ou vazia com schema válido.

## 2) Disparar ciclo manual
1. Acionar ciclo:
```bash
curl -s -X POST -H "$H_AUTH" "$API_BASE/v1/ingestion/trigger/daily-cycle"
```
Esperado:
- `status = "accepted"` ou
- `status = "already_running"` (se já houver ciclo ativo).

2. Se `already_running`, ir para seção 3.

## 3) Acompanhar execução
1. Poll de ciclo a cada 30-60s:
```bash
curl -s -H "$H_AUTH" "$API_BASE/v1/ingestion/cycle-status"
```
Esperado durante execução:
- `czds_cycle.is_active = true` em algum momento,
- `current_tld` preenchido em algum momento,
- contadores de progresso avançando.

2. Poll de resumo por fonte:
```bash
curl -s -H "$H_AUTH" "$API_BASE/v1/ingestion/summary"
```
Esperado:
- `running_now` > 0 durante execução,
- atualização de `last_run_at`/`last_status`.

3. Poll de incidentes (janela curta):
```bash
curl -s -H "$H_AUTH" "$API_BASE/v1/ingestion/incidents?hours=2&limit=100"
```
Esperado:
- se houver falha, `reason_code` consistente (`databricks_*`, `pg_load_error`, `r2_marker_missing`, `stale_recovered`, etc).

## 4) Validação após término
1. Confirmar último ciclo finalizado:
```bash
curl -s -H "$H_AUTH" "$API_BASE/v1/ingestion/cycles?limit=1"
```
Esperado:
- `status` do ciclo em `succeeded`, `failed` ou `interrupted`,
- contadores (`tld_success`, `tld_failed`, `tld_skipped`, `tld_load_only`) coerentes.

2. Validar heatmap:
```bash
curl -s -H "$H_AUTH" "$API_BASE/v1/ingestion/heatmap?days=1"
```
Esperado:
- linhas por TLD com estados faseados,
- presença de sinais de execução do dia.

3. Validar daily summary:
```bash
curl -s -H "$H_AUTH" "$API_BASE/v1/ingestion/daily-summary?from_date=$(date +%F)&to_date=$(date +%F)"
```
Esperado:
- métricas por fonte do dia atual,
- `pg_complete_pct` coerente com os status do dia.

4. Validar cobertura de política:
```bash
curl -s -H "$H_AUTH" "$API_BASE/v1/ingestion/policy-coverage?date=$(date +%F)"
```
Esperado:
- `enabled_total`, `attempted_today`, `success_today`, `failed_today`, `not_reached_today`,
- `policy_coverage_pct` coerente com numerador/denominador.

## 5) Validação de TLDs críticos
Consultar status por fonte:
```bash
curl -s -H "$H_AUTH" "$API_BASE/v1/ingestion/tld-status?source=czds"
curl -s -H "$H_AUTH" "$API_BASE/v1/ingestion/tld-status?source=openintel"
```
Checar especificamente:
- `.com`, `.net`, `.org`, `.info`, `.abb`, `.agency`, `.ch`.

Esperado:
- estado do dia refletido corretamente,
- `last_reason_code` e timestamps atualizados quando houver tentativa.

## 6) Critérios objetivos de aprovação
Marcar como **Aprovado** quando todos os itens abaixo forem verdadeiros:
1. Trigger manual aceito ou ciclo já em execução confirmado.
2. `cycle-status` mostra progresso e finalização consistente.
3. `cycles` registra o novo ciclo com contadores coerentes.
4. `incidents` apresenta `reason_code` quando há falha (sem erro genérico mudo).
5. `policy-coverage` retorna e diferencia cobertura de política vs execução.
6. TLDs críticos têm estado rastreável no dia (sucesso, falha, running, not_reached).

## 7) Evidências a anexar no fechamento
- Resposta JSON de:
  - `trigger/daily-cycle`,
  - `cycle-status` (início, meio, fim),
  - `cycles?limit=1`,
  - `daily-summary` do dia,
  - `policy-coverage` do dia,
  - `incidents` da janela testada.
- Lista dos TLDs críticos com estado final observado.

## 8) Falhas comuns e interpretação rápida
- `already_running` no trigger: comportamento esperado se um ciclo já está ativo.
- `policy-coverage` indisponível: backend ainda sem endpoint no ambiente alvo (deploy parcial).
- Muitos `not_reached_today`: ciclo interrompido, janela curta, ou gargalo operacional.
- `databricks_*` reason codes: erro na submissão/execução Databricks; usar URL da run para diagnóstico.
