# Status — 015

**Status atual:** `in_progress`

**Criado em:** 2026-05-02

**Prioridade:** alta

## Escopo

Diagnóstico e direção técnica para TLDs `OpenINTEL zonefile` grandes que falham no pipeline atual, usando `CZDS` grande como grupo de controle para separar limitação do ambiente versus limitação do parser.

## Status Atual

- `jp` validado com sucesso no Databricks
- `ee` validado com sucesso no Databricks
- `ch` confirmado com falha por `OOM / exit 137`
- `fr` reportado com erro pelo operador
- `se` submetido para validação
- `info` (`czds`) validado com sucesso no Databricks
- `org` (`czds`) validado com sucesso no Databricks
- observabilidade de `run_id`/URL Databricks foi implementada localmente, pendente deploy

## Riscos Abertos

- o parser atual continua memory-hungry para `zonefiles` grandes
- não existe opção prática de subir memória/capacidade no ambiente atual
- ainda há risco operacional enquanto `ch`/`fr` permanecerem no ciclo sem mitigação
- ainda falta fechar a classificacao final de `fr` e `se` para saber se o problema e isolado ou recorrente entre `zonefiles` grandes

## Próximas Ações

1. concluir o resultado final de `fr` e `se`
2. consolidar matriz comparativa `OpenINTEL` vs `CZDS`
3. decidir exclusão temporária de TLDs problemáticos do ciclo
4. especificar ou implementar parser incremental

## Histórico

| Data | Status | Responsável | Nota |
|------|--------|-------------|------|
| 2026-05-02 | in_progress | codex | Documento criado a partir da investigação em produção sobre `OpenINTEL zonefile` grande e Databricks |
| 2026-05-02 | in_progress | codex | Testes de controle com `CZDS:info` e `CZDS:org` concluídos com sucesso no Databricks, reduzindo a hipótese de limitação genérica do ambiente |
