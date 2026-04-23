# 008 — Pipeline de Ingestão Automatizado: Orquestrador + Observabilidade

## Problema

O pipeline de ingestão (CZDS + OpenINTEL via `ingestion/` package) funciona manualmente, mas não existe automação de ponta a ponta. Nenhum cron dispara as execuções, nenhum componente conecta os passos (executar runner → aguardar → carregar PostgreSQL → registrar resultado), e os registros de `ingestion_run` no banco nunca são preenchidos — deixando o painel admin sem dados reais.

## Abordagem

Criar um **Orchestrator** dentro do package `ingestion/` que conhece toda a sequência: buscar TLDs → executar runners (local ou Databricks conforme tamanho) → load PG → gravar `ingestion_run`. O orchestrator roda como serviço Docker (`obs_ingestion_worker`) com APScheduler interno.

## Motor canônico

> **`ingestion/` é o único motor de ingestão.** Tudo que estiver em `backend/app/services/use_cases/sync_czds_tld.py`, `sync_openintel_tld.py` etc. é **legado** e deve ser deprecado/removido quando este plano estiver completo.

## Diagnóstico de Aderência (estado atual vs. ideal)

| Requisito | Status | Observação |
|---|---|---|
| CZDS: download + diff com anterior | ✅ Completo | `czds_runner.py` já faz isso |
| OpenINTEL: download de snapshots | ✅ Completo | `openintel_runner.py` já faz isso |
| Schema ADR-001 aplicado | ✅ Completo | `domain.added_day`, `domain_removed`, append-only |
| Delta loader ADR-001 compliant | ✅ Completo | `ON CONFLICT DO NOTHING`, `added_day` INTEGER |
| Cargas resilientes por TLD | ✅ Completo | try/except por TLD em todos os runners |
| Idempotência R2 (etapa 1) | ✅ Completo | marker `success.json` no R2 |
| Idempotência PostgreSQL (etapa 2) | ✅ Completo | `ON CONFLICT DO NOTHING` |
| Separação de etapas R2 → PG | ✅ Arquitetado | `load` command independente do runner |
| Painel admin — estrutura frontend | ✅ Existe | `/admin/ingestion` com cards por fonte |
| API de observabilidade | ✅ Existe | `/v1/ingestion/runs`, `/summary`, `/cycle-status` |
| Modelo `IngestionRun` | ✅ Existe | Tabela com status, contadores, error_message |
| Ordenação por prioridade (coluna) | ✅ Parcial | Coluna `priority` em `ingestion_tld_policy` existe |
| **Agendamento diário automático** | ❌ Faltando | Nenhum cron/worker dispara o pipeline |
| **Orquestrador end-to-end** | ❌ Faltando | Ninguém conecta os 4 passos |
| **Roteamento local vs Databricks** | ❌ Faltando | CLI bloqueia LARGE_TLDS localmente mas não roteia automaticamente |
| **Todos os TLDs CZDS (~1.400+)** | ❌ Faltando | Só roda o que é passado manualmente |
| **Todos os TLDs OpenINTEL (~200+)** | ❌ Faltando | Lista hardcoded de ~11 TLDs |
| **Ordem OpenINTEL → CZDS → .com** | ❌ Faltando | Prioridade existe na tabela mas não é aplicada |
| **`ingestion_run` populado** | ❌ Faltando | Runners/loader nunca gravam no banco |
| **Load automático pós-runner** | ❌ Faltando | Ninguém chama `load` após runner terminar |
| **Visibilidade no painel** | ❌ Indireto | Dados não chegam ao banco → painel mostra vazio |
| **Similarity scan pós-ingestão** | ❌ Faltando | Nenhum trigger de scan após novos domínios serem carregados |
| **Cleanup de matches de domínios removidos** | ❌ Faltando | `domain_removed` existe mas similarity nunca consome |
| **Deprecação do pipeline legado** | ❌ Faltando | `sync_czds_tld.py` / `sync_openintel_tld.py` coexistem |

---

## Problemas Críticos Identificados na Revisão

### P1 — Dois pipelines divergentes (CRÍTICO)

**Problema:** O backend tem um pipeline legado (`sync_czds_tld.py`, `sync_openintel_tld.py`) que:
- Faz download + apply delta direto no PostgreSQL
- Popula `ingestion_run` corretamente
- Usa advisory locks para concorrência
- É chamado pela API e pelo frontend

O pipeline novo (`ingestion/`) é completamente separado:
- Escreve deltas no R2 (Parquet)
- Usa Databricks para TLDs grandes
- **Nunca toca `ingestion_run`**
- **É invisível para o frontend**

**Resolução:** Este plano deve:
1. Fazer o pipeline `ingestion/` popular `ingestion_run`
2. Deprecar o pipeline legado no backend
3. Remover ou desabilitar endpoints que usam o pipeline legado

### P2 — Roteamento local vs Databricks não existe (CRÍTICO)

**Problema:** O plano original dizia "submete Databricks um a um" para todos os TLDs. Mas:
- ~1.380 dos ~1.400 TLDs CZDS são **pequenos** (< 200MB) e podem rodar localmente no worker
- O CLI já bloqueia LARGE_TLDS de rodarem localmente, mas não roteia automaticamente
- Submeter 1.400 jobs Databricks por dia é proibitivamente caro e lento
- **Databricks Free tier** tem limite de 1 cluster ativo — muitos jobs individuais podem enfileirar ou falhar

**Resolução:** O orchestrator deve:
- TLDs em `LARGE_TLDS` → submeter ao Databricks **em batch** (um notebook processa N TLDs sequencialmente)
- `.com` → job Databricks dedicado (sempre isolado, sempre último)
- Demais TLDs → executar localmente no worker (via `czds_runner` / `openintel_runner`)
- Após ambos os paths: chamar `delta_loader` → gravar `ingestion_run`

**Batching Databricks:** Em vez de 1 job por TLD grande, agrupar em 2-3 jobs:
- **Batch 1:** OpenINTEL large TLDs (de, uk, br, fr, etc.)
- **Batch 2:** CZDS large TLDs exceto .com (net, org, info, biz, etc.)
- **Batch 3:** .com (isolado)
- Cada notebook recebe lista de TLDs via parâmetro e os processa sequencialmente
- Respeita o limite de 1 cluster do Free tier

### P3 — Desconexão ingestão → similarity (IMPORTANTE)

**Problema:** Após carregar novos domínios, nenhum trigger dispara similarity scans. O sistema de similarity usa `added_day >= watermark_day` para encontrar novos domínios, mas:
- Os scans são manuais ou via job queue separado
- Se ninguém agendar scan após ingestão, novos domínios suspeitos ficam invisíveis

**Resolução:** Após o ciclo diário de ingestão completar, o orchestrator deve:
- Chamar a API de similarity scan jobs ou enfileirar scans delta para TLDs que receberam novos domínios
- Ou, no mínimo, notificar que há novos domínios para scanear

### P4 — Domínios expirados não refletem nas ameaças detectadas (IMPORTANTE)

**Problema:** `domain_removed` registra domínios que saíram da zona, mas nenhum componente consome essa informação para atualizar os similarity matches (ameaças). Resultado:
- Matches de domínios que saíram da zona persistem como ameaças **ativas** indefinidamente
- Gera falsos positivos — o cliente é alertado sobre domínios que já não existem
- Se o domínio voltar à zona (re-registro), não há mecanismo de reativação

**Princípio:** A tabela `domain` permanece **append-only** (ADR-001 sagrado). O tratamento de expiração acontece na camada de **ameaças** (`similarity_match`).

**Resolução — flag na tabela `similarity_match`:**
1. Adicionar coluna `domain_expired_day INTEGER NULL` à tabela `similarity_match`
   - `NULL` = domínio ativo na zona (default)
   - `YYYYMMDD` = dia em que o domínio desapareceu da zona
2. Etapa pós-ingestão: cruzar `domain_removed` com `similarity_match`:
   - `UPDATE similarity_match SET domain_expired_day = dr.removed_day FROM domain_removed dr WHERE sm.domain_name = dr.name AND sm.tld = dr.tld AND sm.domain_expired_day IS NULL`
3. Reativação: quando um domínio reaparece na zona (nova ingestão):
   - O domínio é removido de `domain_removed` (`DELETE FROM domain_removed WHERE (name, tld) IN (:reappeared)`)
   - `UPDATE similarity_match SET domain_expired_day = NULL WHERE domain_name = :name AND tld = :tld AND domain_expired_day IS NOT NULL`
4. UI: matches com `domain_expired_day IS NOT NULL` mostram badge "domínio expirado" — **não são deletados**
5. O cliente mantém visibilidade histórica das ameaças, mesmo após expiração

### P5 — Idempotência R2 ↔ PG desincronizada (MODERADO)

**Problema:** O marker `success.json` no R2 é escrito quando o runner termina, independente do load PG. Cenário de falha:
1. Runner conclui → marker R2 escrito ✓
2. Load PG falha (timeout, disco, etc.) ✗
3. Próximo run: vê marker → skip TLD inteiro
4. Dados nunca chegam ao PostgreSQL

**Resolução:** O orchestrator deve verificar **ambos** antes de considerar um TLD como "done":
- Marker R2 existe? (etapa 1 ok)
- `ingestion_run` com `status=success` para este TLD+data? (etapa 2 ok)
- Se marker existe mas run não → skip runner, executar apenas load

### P6 — OpenINTEL com TLDs hardcoded (MODERADO)

**Problema:** `settings.py` tem `openintel_tlds = "ac,br,uk,de,fr,se,nu,ch,li,sk,ee"`. Só 11 dos ~200 TLDs disponíveis. Mudar requer deploy.

**Resolução:** O orchestrator deve ler TLDs habilitados de `ingestion_tld_policy` (que já existe). A lista hardcoded passa a ser apenas fallback/seed inicial.

### P7 — Naming mismatch CLI vs DB (MENOR)

**Problema:** CLI retorna `{"added": N, "removed": N}` mas DB tem `domains_inserted`, `domains_deleted`. O `run_recorder` precisa fazer o mapeamento.

**Resolução:** Padronizar os nomes no `RunStats` para alinhar com `IngestionRun`, ou fazer mapeamento explícito no recorder.

---

## Fases de Implementação (Revisadas)

### Fase 0 — Deprecar pipeline legado _(pré-requisito)_

**0A** — Marcar `sync_czds_tld.py` e `sync_openintel_tld.py` como deprecated
- Adicionar log warning se chamados
- Desabilitar endpoints da API que os disparam (ou redirecionar para o novo pipeline)
- **Não deletar ainda** — manter como referência até pipeline novo estar validado

**0B** — Seed de `ingestion_tld_policy` com todos os TLDs
- CZDS: buscar lista completa da API CZDS e popular `ingestion_tld_policy` com `source=czds`
- OpenINTEL: popular com os ~200 ccTLDs disponíveis (source=openintel)
- Definir `priority` corretamente (menores primeiro, .com último)
- Marcar todos como `is_enabled=true` inicialmente

---

### Fase 1 — Conectar `ingestion_run` ao pipeline _(desbloqueia o painel)_

**1A** — Criar `ingestion/ingestion/observability/run_recorder.py`
- Função `record_run(db_url, source, tld, status, started_at, finished_at, domains_inserted, domains_deleted, error_message)`
- Faz INSERT no `ingestion_run` via SQLAlchemy direto (sem depender do backend)
- Mapeamento explícito: `RunStats.added_count → domains_inserted`, `RunStats.removed_count → domains_deleted`
- Usado pelo orchestrator após cada TLD concluir (runner + load)

**1B** — Modificar `delta_loader.py` para retornar contadores estruturados
- Já retorna `{added_loaded, removed_loaded, status}` — garantir que esses valores chegam ao recorder
- Adicionar `snapshot_date` ao retorno para cross-reference

**1C** — Garantir que `load` CLI chama o recorder após o load
- Parâmetro `--record` (default: false quando chamado manualmente, true quando chamado pelo orchestrator)

---

### Fase 2 — Orquestrador CLI (`orchestrate` subcommand)

**2A** — Criar `ingestion/ingestion/orchestrator/pipeline.py`

- `run_cycle(settings, sources=None)`: orquestração master
  1. Lê TLDs habilitados de `ingestion_tld_policy` (via DB direto)
  2. Ordena por prioridade (menores primeiro, .com último)
  3. Executa OpenINTEL primeiro, depois CZDS
  4. Para cada TLD:
     - **Verificar idempotência**: marker R2 + `ingestion_run` success?
       - Ambos ok → skip
       - Marker R2 ok, DB não → só faz load
       - Nenhum → executa runner + load
     - **Rotear execução**:
       - TLD em `LARGE_TLDS` → submeter ao Databricks, aguardar, fazer load
       - TLD fora de `LARGE_TLDS` → executar runner localmente, fazer load
     - **Gravar `ingestion_run`** via run_recorder
     - **Resiliência**: try/except por TLD, erro não para o ciclo
  5. Após ciclo completo: emitir sumário (TLDs ok / fail / skip)

- `run_openintel_cycle(settings)`: wrapper para `run_cycle(sources=["openintel"])`
- `run_czds_cycle(settings)`: wrapper para `run_cycle(sources=["czds"])`

**2B** — Adicionar subcomando `orchestrate` ao `cli.py`
```
python -m ingestion orchestrate --source czds
python -m ingestion orchestrate --source openintel
python -m ingestion orchestrate  # roda ambos na ordem certa
```

**2C** — Batching Databricks (Free tier)
- Agrupar LARGE_TLDS em 2-3 jobs Databricks por ciclo:
  - **Job 1:** LARGE_TLDS do OpenINTEL (de, uk, br, fr, etc.) — notebook recebe lista de TLDs
  - **Job 2:** LARGE_TLDS do CZDS exceto .com (net, org, info, biz, etc.)
  - **Job 3:** .com (isolado, sempre último)
- Cada notebook processa TLDs sequencialmente dentro do mesmo job
- Notebooks já aceitam `--tlds=net,org,info` — adaptar submitter para passar lista
- Respeita limite de 1 cluster ativo do Databricks Free tier
- Se Free tier permitir, jobs 1 e 2 podem rodar sequencialmente no mesmo cluster

**2D** — Concorrência controlada
- TLDs locais: execução sequencial (1 de cada vez) para não sobrecarregar o worker
- TLDs Databricks: sequenciais (1 job por vez — Free tier)
- Load PG: sequencial por TLD para evitar contention no GIN index

---

### Fase 3 — Scheduler Docker (cron automático)

**3A** — Criar `ingestion/scheduler.py`
- Entry point com APScheduler (BackgroundScheduler)
- Cron: `0 4 * * *` UTC (= 1AM UTC-3)
- Chama `run_cycle()` (OpenINTEL → CZDS → .com)
- Logs estruturados de início/fim de ciclo
- Health check endpoint (HTTP /health) para Docker

**3B** — Adicionar serviço ao stack Docker
```yaml
obs_ingestion_worker:
  image: observadordedominios-ingestion:latest
  command: python -m ingestion.scheduler
  environment:
    - R2_ACCOUNT_ID
    - R2_ACCESS_KEY_ID
    - R2_SECRET_ACCESS_KEY
    - CZDS_USERNAME / CZDS_PASSWORD
    - DATABRICKS_HOST / DATABRICKS_TOKEN
    - DATABASE_URL
  deploy:
    restart_policy:
      condition: on-failure
      delay: 30s
```

**3C** — Dockerfile para o ingestion worker (`ingestion/Dockerfile`)

**3D** — Configurar `CZDS_SYNC_CRON` e `OPENINTEL_SYNC_CRON` no `backend/app/core/config.py` para o painel mostrar o próximo horário corretamente

---

### Fase 4 — Pós-ingestão: similarity scan + expiração + limpeza R2

**4A** — Após ciclo de ingestão, enfileirar similarity scans delta
- Para cada TLD que recebeu `domains_inserted > 0`:
  - Chamar API `POST /v1/similarity/scan-jobs` ou inserir diretamente em `similarity_scan_job`
  - Scan tipo "delta" (usa watermark, não re-escaneia tudo)
- Isso garante que novos domínios suspeitos sejam detectados no mesmo dia

**4B** — Marcar ameaças de domínios expirados + reativação
- Criar use case `sync_domain_expiration_to_matches`:
  1. **Expiração:** Cruzar `domain_removed` com `similarity_match`:
     ```sql
     UPDATE similarity_match sm
     SET domain_expired_day = dr.removed_day
     FROM domain_removed dr
     WHERE sm.domain_name = dr.name AND sm.tld = dr.tld
       AND sm.domain_expired_day IS NULL
     ```
  2. **Reativação:** Domínios que reapareceram na ingestão de hoje:
     - Identificar domínios que foram inseridos hoje (`added_day = :today`) e existem em `domain_removed`
     - `DELETE FROM domain_removed WHERE (name, tld) IN (:reappeared)`
     - `UPDATE similarity_match SET domain_expired_day = NULL WHERE (domain_name, tld) IN (:reappeared) AND domain_expired_day IS NOT NULL`
  3. UI: matches com `domain_expired_day IS NOT NULL` → badge "domínio expirado"
  4. Matches **não são deletados** — cliente mantém visibilidade histórica

**4C** — Migração do modelo SimilarityMatch
- Adicionar coluna `domain_expired_day INTEGER NULL` à tabela `similarity_match` (migration Alembic)
- Criar index parcial: `CREATE INDEX ix_match_expired ON similarity_match (domain_expired_day) WHERE domain_expired_day IS NOT NULL`
- Atualizar queries de listagem de ameaças para retornar `domain_expired_day` e permitir filtro (ex: "mostrar apenas ameaças ativas")

**4D** — Política de retenção do R2 (limpeza de arquivos)
- Após **todos** os TLDs de um ciclo estarem com `ingestion_run.status = success`:
  - Limpar delta Parquets antigos: `{source}/{tld}/{date}/delta.parquet` e `delta_removed.parquet` para datas > N dias (sugestão: 7 dias)
  - Limpar markers `success.json` de datas antigas (mesma janela)
  - **Manter** os arquivos `current.parquet` (necessários para o diff do próximo dia)
  - **Manter** o dia atual e o anterior (para retry em caso de falha)
- Implementar como etapa final do `run_cycle()`:
  ```
  cleanup_r2_deltas(storage, layout, retention_days=7)
  ```
- Configurável via env var `R2_RETENTION_DAYS` (default: 7)
- Log de quantos arquivos/bytes foram limpos por ciclo

---

### Fase 5 — Painel admin complementar _(visibilidade por TLD)_

**5A** — Endpoint `GET /v1/ingestion/tld-status?source=czds`
- Retorna todos TLDs habilitados com: último run, status, added, removed, próximo agendamento, erros recentes

**5B** — Atualizar `/admin/ingestion/[source]/page.tsx`
- Tabela de TLDs com: badge de status, sparkbar das últimas 10 execuções, contadores de domínios added/removed, tempo de duração
- Paginação / busca por TLD

**5C** — Widget de "Ciclo diário"
- Progresso: N de M TLDs processados hoje
- Tempo estimado de conclusão
- Taxa de sucesso do ciclo atual

---

## Ordem de execução de TLDs

```
1. OpenINTEL: todos os TLDs habilitados em ingestion_tld_policy (por priority ASC)
2. CZDS: todos os TLDs autorizados, exceto .com (por priority ASC / tamanho estimado ASC)
3. CZDS: .com (último, sempre)
```

### Roteamento de execução

```
Para cada TLD:
  Se TLD ∉ LARGE_TLDS → Local (runner direto no worker + load)
  Se TLD ∈ LARGE_TLDS e TLD ≠ com → Batch Databricks (agrupado com outros LARGE_TLDS)
  Se TLD = com → Job Databricks dedicado (isolado, último)
```

**Critério de LARGE_TLD:** zone file gzip > 200MB (atualmente ~21 TLDs).

TLDs grandes que DEVEM rodar no Databricks (nunca local):
`com, net, org, de, uk, br, info, biz, nl, cn, ru, au, fr, it, es, pl, ca, jp, in, eu, app`

### Batching Databricks (Free tier)

```
Job 1: [de, uk, br, fr, it, es, nl, pl, ...] ← LARGE OpenINTEL ccTLDs (sequencial dentro do job)
Job 2: [net, org, info, biz, eu, app, ...]   ← LARGE CZDS gTLDs exceto .com (sequencial)
Job 3: [com]                                  ← Sempre isolado, sempre último
```

- Total: 3 jobs Databricks por ciclo (em vez de ~21 jobs individuais)
- Jobs rodam sequencialmente (Free tier = 1 cluster)
- Cada notebook recebe `TLDS=net,org,info` e processa em loop

---

## Fluxo completo do ciclo diário

```
┌─────────────────────────────────────────────────────────────────┐
│                    Ciclo Diário (1AM UTC-3)                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. Ler TLDs habilitados de ingestion_tld_policy                │
│  2. Ordenar por prioridade (menores primeiro, .com último)      │
│                                                                 │
│  ┌─── OpenINTEL (~200 TLDs) ──────────────────────────────┐    │
│  │  Para cada TLD:                                         │    │
│  │    ├─ Checar idempotência (R2 marker + ingestion_run)   │    │
│  │    ├─ Se TLD pequeno → runner local                     │    │
│  │    ├─ Se TLD grande → submit Databricks + poll          │    │
│  │    ├─ Load delta → PostgreSQL (ON CONFLICT DO NOTHING)  │    │
│  │    └─ Gravar ingestion_run (run_recorder)               │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─── CZDS (~1.400 TLDs) ────────────────────────────────┐     │
│  │  Mesma lógica, .com por último                         │     │
│  └────────────────────────────────────────────────────────┘     │
│                                                                 │
│  3. Expiração: cruzar domain_removed × similarity_match         │
│     → marcar ameaças de domínios expirados + reativar           │
│  4. Trigger: enfileirar similarity scans delta para TLDs        │
│     que receberam novos domínios                                │
│  5. Cleanup R2: remover delta Parquets > 7 dias                 │
│     (manter current.parquet para próximo diff)                  │
│  6. Sumário: log + ingestion_run aggregates para painel         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## Considerações técnicas

- O orchestrator precisa de acesso ao banco para ler `ingestion_tld_policy` e escrever `ingestion_run`
- O `ingestion` package já tem `delta_loader.py` com acesso ao PG — reutilizar a conexão
- O submitter Databricks já funciona de forma isolada por TLD — o orchestrator é apenas o loop de orquestração
- CI/CD: o `obs_ingestion_worker` precisa ser adicionado ao `build-push.yml` e ao `docker-stack-infra`
- **Disk space local**: runners CZDS baixam zone files grandes; garantir cleanup de temp files após processamento
- **R2 retention**: delta Parquets acumulam ~500MB-1GB/dia; política de retenção de 7 dias limpa automaticamente; `current.parquet` nunca é apagado
- **Monitoramento**: se o ciclo inteiro falhar, o painel mostrará "último ciclo: N horas atrás" — considerar alerta (email/slack) para falhas totais
- **Primeiro run (backfill)**: o primeiro ciclo com ~1.400 TLDs CZDS será lento (sem "anterior" para diff → tudo é "novo"). Planejar janela de ~24-48h para o primeiro ciclo completo.
- **Advisory locks**: considerar usar advisory locks no load PG para evitar conflito se dois workers rodarem por acidente (mesmo padrão do pipeline legado)

---

## Dependências entre fases

```
Fase 0 (deprecar legado) ─┐
                           ├─→ Fase 1 (run_recorder) ─→ Fase 2 (orchestrator) ─→ Fase 3 (scheduler)
                           │
Fase 4 (similarity + cleanup) ← depende de Fase 2 estar funcional
Fase 5 (painel) ← depende de Fase 1 (dados no ingestion_run)
```

Fases 4 e 5 podem ser desenvolvidas em paralelo com Fase 3.

---

## Riscos e mitigações

| Risco | Impacto | Mitigação |
|-------|---------|-----------|
| Primeiro backfill de 1.400 TLDs CZDS demora 24-48h | Atrasa validação | Rodar primeiro com subset (top 50 TLDs), expandir gradualmente |
| Worker fica sem disco (zone files grandes) | Ciclo para | Cleanup de temp files após cada TLD; monitorar `/tmp` |
| Databricks job falha silenciosamente | TLD não processado | Poll com timeout; se Databricks não responder em 2h, marcar como failed |
| APScheduler perde estado no restart do container | Ciclo duplicado ou perdido | Idempotência R2+DB garante que re-run é seguro; health check para detectar crash |
| Dois workers rodando simultâneamente | Conflito de escrita | Advisory lock por ciclo no início; segundo worker espera ou aborta |
| Databricks Free tier: limite de 1 cluster | Jobs enfileiram ou falham | Batching: 3 jobs sequenciais em vez de 21 individuais |
| R2 acumula GBs de deltas antigos | Custo de storage cresce | Política de retenção automática de 7 dias ao final de cada ciclo |
| UPDATE domain_expired_day em similarity_match | Possível lentidão se muitos matches | Index parcial limita escopo; executar em batch por TLD |
