# Relatório de Auditoria de Ingestão (Produção)

- Data da execução (UTC): 2026-04-29 22:29
- Ambiente: produção (`saasbox` / Docker Swarm)
- Runbook base: `docs/runbooks/ingestion-audit.md`
- Executor: Codex

## Pré-validação de acesso

- Acesso SSH sem senha confirmado via host `saasbox` (`~/.ssh/config` com `IdentityFile ~/.ssh/id_rsa_saasbox`).
- Serviços de produção alcançáveis:
  - `https://observadordedominios.com.br` -> HTTP 200
  - `https://api.observadordedominios.com.br/health` -> HTTP 200
- Serviços Swarm do stack observador ativos para auditoria:
  - `observador_backend 1/1`
  - `observador_frontend 1/1`
  - `observador_postgres 1/1`
  - `observador-ingestion_ingestion_worker 1/1`

## Resultado executivo

Status geral do ciclo diário em **2026-04-29 (UTC)**: **não saudável**.

Resumo (`executive_summary`):

| source | total_habilitados | completos | pg_pendente | r2_falhou | rodando | sem_atividade_hoje | pct_completo |
|---|---:|---:|---:|---:|---:|---:|---:|
| czds | 1125 | 0 | 0 | 1 | 0 | 1124 | 0.0 |
| openintel | 316 | 0 | 0 | 0 | 1 | 315 | 0.0 |

Critério do runbook (`pct_completo >= 95%`) **não atendido**.

## Achados por camada

### Camada 0 - Catálogo/policy

#### 0.1 CZDS autorizado vs policy

- `authorized_count=1097`
- `policy_enabled_count=1125`
- `not_seeded_count=0`
- `not_authorized_count=28`
- Amostra `not_authorized`: `ai, airtel, au, bzh, ca, co, de, es, eu, fr, io, it, nl, uk, us, ...`

Interpretação: não faltam TLDs autorizados na policy, mas há 28 TLDs habilitados na policy sem autorização atual no CZDS.

#### 0.2 OpenINTEL habilitados

| source | total_habilitados | zonefile | web_small | web_large |
|---|---:|---:|---:|---:|
| openintel | 316 | 72 | 241 | 2 |

Interpretação: volume acima do baseline aproximado descrito no runbook (~150), sugerindo expansão de escopo (ou necessidade de atualizar referência esperada).

#### 0.3 TLDs desabilitados

- Resultado: **0 linhas** (`is_enabled=false`).

### Camada 1 - Cobertura R2

#### 1.1 Cobertura do dia

| source | total_habilitados | r2_ok_hoje | r2_faltando | cobertura_pct |
|---|---:|---:|---:|---:|
| czds | 1125 | 0 | 1125 | 0.0 |
| openintel | 316 | 0 | 316 | 0.0 |

#### 1.2 Faltantes últimos 3 dias

- `czds`: **479** TLDs sem sucesso `r2/full`
- `openintel`: **256** TLDs sem sucesso `r2/full`
- Amostra (CZDS): `aaa, aarp, anquan, anz, app, art, associates, ...`

### Camada 2 - R2 -> PG

#### 2.1 Dual-phase hoje (`tld_daily_status_v`)

| source | r2_status | pg_status | tlds |
|---|---|---|---:|
| czds | failed | failed | 1 |
| openintel | running | running | 1 |

#### 2.2 R2 ok mas PG não-success (último estado por TLD)

- `certstream`: 1
- `czds`: 6
- `openintel`: 93

#### 2.3 Partições ausentes (últimos 30 dias)

- `certstream`: 1
- `crtsh`: 10
- `czds`: 85
- `openintel`: 59

Interpretação: risco real de falha/silêncio no loader para TLDs/feeds sem partição física esperada.

### Camada 3 - Coerência de quantidades

Bloqueio técnico encontrado:

- `ERROR: materialized view "tld_domain_count_mv" has not been populated`

Impacto:

- Não foi possível validar os itens 3.1 e 3.2 (desvio e TLD com count zero) usando a MV.
- Item 3.3 (z-score) executou e retornou múltiplas anomalias; a evidência bruta foi capturada na execução.

### Camada 4 - Continuidade histórica

#### 4.1 Fora do limiar

- `czds`: **763** TLDs fora do limiar (>2 dias)
- `openintel`: **256** TLDs fora do limiar (>7 dias)

#### 4.2 Cobertura 30d < 70%

- `czds`: **1125** TLDs
- `openintel`: **316** TLDs

#### 4.3 Nunca tiveram sucesso

- `czds`: **9** TLDs
- `openintel`: **13** TLDs
- Total: **22** TLDs

## Conclusão

A auditoria de produção indica **incompletude severa de ingestão** no recorte diário e degradacão histórica ampla, com os seguintes focos principais:

1. Cobertura R2 diária zerada para CZDS/OpenINTEL no dia auditado.
2. Alto volume de TLDs sem sucesso recente (3 dias) e fora de limiar histórico.
3. Déficit de partições no PostgreSQL para fontes ativas.
4. `tld_domain_count_mv` não populada, bloqueando parte da validação de coerência.

## Recomendações imediatas

1. Executar `REFRESH MATERIALIZED VIEW CONCURRENTLY tld_domain_count_mv;` e rerodar camada 3 completa.
2. Corrigir backlog de partições ausentes (`domain_*`) para fontes com atividade recente.
3. Rodar ações de recuperação por TLD conforme runbook:
   - `POST /v1/ingestion/tld/{source}/{tld}/run`
   - `POST /v1/ingestion/tld/{source}/{tld}/reload`
4. Revisar policy CZDS para os 28 TLDs habilitados não autorizados atualmente.
5. Investigar scheduler/ciclos da data auditada (04h UTC) para explicar `pct_completo=0.0`.

## Evidências

- SQL consolidado: `.tmp_ingestion_audit.sql`
- Saída consolidada: `.tmp_ingestion_audit_output.txt`
- Resumo complementar: `.tmp_ingestion_audit_summary.sql`
- Checagem CZDS: `.tmp_czds_check.py`

---

## Execução das recomendações imediatas (2026-04-29 UTC)

Ações executadas em produção:

1. `REFRESH MATERIALIZED VIEW tld_domain_count_mv` executado com sucesso.
   - Estado final: `ispopulated=true`.
2. Correção de partições ausentes aplicada para TLDs ativos (últimos 30 dias).
   - Estado final: `missing_domain=0` e `missing_removed=0`.
3. Recuperação operacional via API:
   - `reload` disparado para 99 TLDs (`r2_ok` com `pg != success`) em `czds/openintel`.
   - `run` disparado para 22 TLDs que nunca tiveram sucesso.
4. Policy CZDS alinhada com autorização real do CZDS API.
   - Estado final: `enabled_after=1097`, `disabled_after=28`.

### Revalidação rápida pós-ação

| source | total_habilitados | completos | pg_pendente | r2_falhou | rodando | sem_atividade_hoje | pct_completo |
|---|---:|---:|---:|---:|---:|---:|---:|
| czds | 1097 | 9 | 0 | 1 | 6 | 1081 | 0.8 |
| openintel | 316 | 0 | 0 | 11 | 3 | 302 | 0.0 |

Observação: os `run/reload` foram aceitos e colocados para processamento; os indicadores ainda refletem janela de execução em andamento.
