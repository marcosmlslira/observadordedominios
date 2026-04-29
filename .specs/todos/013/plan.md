# TODO 013 — Ingestão dual-fase: visibilidade R2 ↔ PostgreSQL e reprocessamento granular por TLD

> **Status:** proposta
> **Criado em:** 2026-04-29
> **Autor:** Marcos Lira + Claude (Opus 4.7)
> **Relaciona-se com:**
> - [ADR-001 — domain table redesign](../../../docs/adr/001-domain-table-redesign.md)
> - [ADR-002 — daily TLD update architecture](../../../docs/adr/002-ingestion-daily-tld-update-architecture.md)
> - [TODO 010 — catálogo de problemas](../010/plan.md) (forense)
> - [TODO 011 — ingestão "boring"](../011/plan.md) (resiliência estrutural)
> - [TODO 012 — incidente 29/04](../012/plan.md) (sintomas atuais)

---

## 1. Por que este plano existe

O ADR-002 modela ingestão diária em **duas fases independentes mas conectadas**:

1. **Fase R2** — produzir o delta (`delta_added`, `delta_removed`) e gravar o marker em R2.
2. **Fase PG** — carregar o delta no PostgreSQL via particão do TLD.

O usuário verbalizou esse mesmo modelo:

> *"costumo visualizar o processo em 3 fases: ingestão para o R2 do delta… e importe para o PostgreSQL. Vejo esses processos como independentes mas conectados, por exemplo nesse momento eu acredito que tem arquivos no R2 que ainda não foram importados para o PostgreSQL, nisso eu precisaria ter visibilidade e conseguir reexecutar só para aquele TLD."*

Hoje, no entanto:

| Sintoma | Causa estrutural |
|---|---|
| O heatmap mostra **um único status por célula** (`success` / `failed` / `delayed` / …), derivado por heurística no client (`page.tsx:346-376`). | O modelo de dados não tem campos separados para **R2-OK** vs **PG-OK**. A UI mistura `ingestion_run.status` (PG) com `openintel_tld_status.status` (R2) e perde precisão. |
| Não existe ação "reprocessar este TLD/dia" na UI. | Backend só expõe `POST /trigger/daily-cycle` (ciclo inteiro). Não há `POST /tld/<source>/<tld>/reload` para forçar `LOAD_ONLY` em um TLD específico. |
| Erros chegam diluídos: o card "Incidentes" lista por `run_id`, mas a célula falha silenciosa. | `reason_code` existe em `ingestion_run` mas não é exibido no hover da célula em formato útil; e não distingue **falha em R2** de **falha em PG**. |
| Não há agregado por dia (cabeçalho da coluna). | Backend não expõe `GET /daily-summary?date=YYYY-MM-DD` retornando `% TLDs OK / duração / domínios novos`. |
| Quando 1 TLD falha, o operador não sabe se isso bloqueou o ciclo ou se foi isolado. | O orchestrator **já isola erros por TLD** (`pipeline.py:822-833`), mas a UI não comunica isso. |

A meta deste TODO:

> **Tornar visível na UI a separação R2 ↔ PG, permitir reprocessar um TLD individualmente, e fornecer agregados por coluna (data) para diagnóstico imediato — sem reescrever o orchestrator.**

---

## 2. O que NÃO está em escopo

- **Resiliência estrutural** (eliminar DDL do hot-path, memory limits, stack isolado): coberto por **TODO 011**. Este plano assume que 011 já estabilizou o caminho de carga.
- **Schema do `domain` / `domain_removed`**: já definido pelo ADR-001 e em produção.
- **Mudanças nas fontes (CZDS / OpenINTEL / CertStream / Databricks notebooks)**: o contrato atual de R2 (`marker_key`, `delta_key`, `current.parquet`) permanece.
- **Migrar tudo para Databricks**: a política `execution_mode_for_source` continua respeitada por TLD.

---

## 3. Modelo conceitual proposto

### 3.1. Cada (source, tld, snapshot_date) tem **dois status independentes**

```text
                  ┌──────────────┐                ┌──────────────┐
   delta build →  │   R2 phase   │ marker grava → │   PG phase   │ → ingestion_run
                  └──────────────┘                └──────────────┘
                  pending|ok|failed                pending|ok|failed
                  no_snapshot                      load_only_pending
```

**Estado da célula no heatmap = combinação dos dois status:**

| R2 phase | PG phase | Cor / símbolo | Significado |
|---|---|---|---|
| `ok` | `ok` | verde sólido | Tudo carregado |
| `ok` | `pending` | amarelo (R2 pronto, aguardando PG) | LOAD_ONLY a executar |
| `ok` | `failed` | laranja com badge "PG" | R2 ok, PG falhou — clicar para reprocessar PG-only |
| `failed` | `pending` | vermelho com badge "R2" | Falhou na origem (Databricks/CZDS); precisa rerun completo |
| `pending` | `pending` | cinza | Não executou ainda |
| `no_snapshot` | — | cinza tracejado | Fonte não disponibilizou snapshot do dia |

A célula passa a ter **dois indicadores visuais** (split-cell ou ponto duplo), e o tooltip detalha cada fase.

### 3.2. Cabeçalho da coluna (eixo X = data) traz agregados do dia

Por data exibida:
- `% TLDs com PG-OK` (ex.: `92% • 145/158`)
- duração total do ciclo (`started_at` mais antigo até `finished_at` mais recente)
- domínios `INSERTed` somados (do `ingestion_run`)
- contadores de falha por fase (`R2: 3 / PG: 2`)

### 3.3. Reprocessamento granular

Três ações possíveis sobre uma célula:

| Ação | Quando faz sentido | Endpoint |
|---|---|---|
| **Reload PG do R2** | R2-ok + PG-failed/pending | `POST /v1/ingestion/tld/{source}/{tld}/reload?snapshot_date=YYYY-MM-DD` |
| **Rerun completo (R2 + PG)** | R2-failed | `POST /v1/ingestion/tld/{source}/{tld}/run?snapshot_date=YYYY-MM-DD` |
| **Marcar como `no_snapshot`** | Falsa falha (fonte realmente não tem dados) | `POST /v1/ingestion/tld/{source}/{tld}/dismiss?snapshot_date=YYYY-MM-DD&reason=...` |

Todas chamam o `ingestion_worker` via `INGESTION_TRIGGER_URLS` e respeitam `X-Ingestion-Token` (introduzido em 011 §3.7).

---

## 4. Mudanças necessárias

### 4.1. Backend — modelo de dados

#### 4.1.1. Estender `ingestion_run` com fase explícita

Já existem `status`, `reason_code`, `snapshot_date`. Falta o campo que separa "que fase falhou":

```sql
-- Nova migration 037_ingestion_run_phase.py
ALTER TABLE ingestion_run
    ADD COLUMN phase TEXT NOT NULL DEFAULT 'pg'
        CHECK (phase IN ('r2', 'pg', 'full'));
-- 'r2'   → run só de produção do delta+marker (Databricks/local diff)
-- 'pg'   → run de carga PG a partir de R2 (LOAD_ONLY)
-- 'full' → run que cobriu R2+PG sequencialmente (caminho local atual)
```

> **Por quê:** hoje uma falha de Databricks e uma falha de `COPY` no Postgres geram `ingestion_run` com `status=failed` indistinguíveis no nível de schema — o `reason_code` resolve, mas é texto livre. Tornar `phase` uma coluna estruturada permite contagens triviais e permite agregar duas fases do mesmo dia (uma `run` para R2, outra para PG).

**Convenção operacional após a migration:**
- caminho local pequeno (TLDs pequenos): cria 1 run com `phase='full'` (compatibilidade).
- caminho Databricks: cria 1 run `phase='r2'` (heartbeat durante o submit) + 1 run `phase='pg'` por TLD após o load.
- reload manual: cria 1 run `phase='pg'`.

#### 4.1.2. View `tld_daily_status_v` — uma linha por (source, tld, date) com os dois status

```sql
CREATE OR REPLACE VIEW tld_daily_status_v AS
WITH per_phase AS (
    SELECT
        source, tld,
        COALESCE(snapshot_date, started_at::date) AS day,
        phase,
        -- vence: success > running > failed > skipped
        FIRST_VALUE(status) OVER w AS phase_status,
        FIRST_VALUE(reason_code) OVER w AS phase_reason,
        FIRST_VALUE(error_message) OVER w AS phase_error,
        FIRST_VALUE(started_at) OVER w AS phase_started,
        FIRST_VALUE(finished_at) OVER w AS phase_finished,
        FIRST_VALUE(domains_inserted) OVER w AS phase_inserted,
        FIRST_VALUE(domains_deleted) OVER w AS phase_deleted
    FROM ingestion_run
    WINDOW w AS (
        PARTITION BY source, tld, COALESCE(snapshot_date, started_at::date), phase
        ORDER BY (status='success') DESC, started_at DESC
    )
)
SELECT DISTINCT
    source, tld, day,
    MAX(phase_status) FILTER (WHERE phase IN ('r2','full'))      AS r2_status,
    MAX(phase_reason) FILTER (WHERE phase IN ('r2','full'))      AS r2_reason,
    MAX(phase_status) FILTER (WHERE phase IN ('pg','full'))      AS pg_status,
    MAX(phase_reason) FILTER (WHERE phase IN ('pg','full'))      AS pg_reason,
    MAX(phase_error)  FILTER (WHERE phase_status='failed')       AS last_error,
    MAX(phase_finished) - MIN(phase_started)                     AS total_duration,
    SUM(phase_inserted) FILTER (WHERE phase IN ('pg','full'))    AS domains_inserted,
    SUM(phase_deleted)  FILTER (WHERE phase IN ('pg','full'))    AS domains_deleted
FROM per_phase
GROUP BY source, tld, day;
```

> **Insight de modelagem:** view materializada não é necessária no v1 — a query roda sobre `ingestion_run` que tem índice em `(source, tld, started_at DESC)`. Se virar gargalo, vira MV com refresh por trigger.

#### 4.1.3. Endpoints novos no `ingestion.py`

| Método | Path | Resposta |
|---|---|---|
| `GET` | `/v1/ingestion/heatmap?source=czds&days=14` | matriz `[{tld, days: [{date, r2_status, pg_status, r2_reason, pg_reason, error, duration_seconds, inserted}]}]` |
| `GET` | `/v1/ingestion/daily-summary?date=YYYY-MM-DD&source=czds` | `{tld_total, pg_ok, pg_failed, r2_ok, r2_failed, no_snapshot, duration_seconds, domains_inserted}` |
| `POST` | `/v1/ingestion/tld/{source}/{tld}/reload` | dispara LOAD_ONLY no worker |
| `POST` | `/v1/ingestion/tld/{source}/{tld}/run` | dispara FULL_RUN no worker |
| `POST` | `/v1/ingestion/tld/{source}/{tld}/dismiss` | grava run sintético com `reason_code='operator_dismissed'` |

Schema novo em `app/schemas/ingestion.py`:

```python
class TldDailyStatus(BaseModel):
    date: date
    r2_status: Literal["ok","pending","failed","no_snapshot","running"]
    pg_status: Literal["ok","pending","failed","running","skipped"]
    r2_reason: str | None
    pg_reason: str | None
    error: str | None
    duration_seconds: int | None
    domains_inserted: int

class HeatmapTldRow(BaseModel):
    tld: str
    source: str
    domain_count: int
    days: list[TldDailyStatus]

class DailySummary(BaseModel):
    date: date
    source: str
    tld_total: int
    r2_ok: int; r2_failed: int
    pg_ok: int; pg_failed: int; pg_pending: int
    no_snapshot: int
    duration_seconds: int | None
    domains_inserted: int
    pg_complete_pct: float  # pg_ok / tld_total
```

#### 4.1.4. Schema fix de `TldStatusCategory` (P03 do TODO 012)

Antes deste plano: adicionar `"partial"` e `"never_attempted"` em `app/schemas/czds_ingestion.py:TldStatusCategory`. **É pré-requisito** — sem isso o painel inteiro derruba.

### 4.2. Worker — orchestrator e endpoint HTTP

#### 4.2.1. Endpoints HTTP novos no `scheduler.py`

```
POST /tld/reload  body={source, tld, snapshot_date}  → enfileira LOAD_ONLY
POST /tld/run     body={source, tld, snapshot_date}  → enfileira FULL_RUN
GET  /tld/queue                                       → lista pending
```

Isolados por `X-Ingestion-Token` (já em 011). Cada handler chama `pipeline._process_tld_local(...)` ou `pipeline._load_tld_from_r2(...)` em uma thread dedicada para não bloquear o scheduler principal.

#### 4.2.2. Refactor mínimo no `pipeline.py` para gravar `phase`

- `_process_tld_local` (caminho FULL, local): grava `phase='full'`.
- `_submit_databricks_batch`: grava `phase='r2'` no início, `finish_run` com `phase='r2'` quando o batch retorna; depois cria runs `phase='pg'` em `_load_tld_from_r2`.
- `_load_tld_from_r2` standalone: grava `phase='pg'`.

Mudança mecânica em `run_recorder.create_run` para aceitar `phase: str = "full"`.

#### 4.2.3. Resiliência por TLD — confirmar comportamento atual

Hoje (`pipeline.py:822-833`) o loop `for tld in small_tlds` já é per-TLD com `try/except` em `_process_tld_local`. **Nada a mudar aqui** — só validar com teste do Sprint 5 (§5.5).

Pontos onde **uma falha pode impactar outros TLDs** e precisam ser revistos:
1. `_submit_databricks_batch`: hoje uma falha no batch marca **todos os TLDs do chunk** como erro (`pipeline.py:511-522`). Precisa: parsing fino do retorno do Databricks para identificar quais TLDs gravaram marker e quais não — os com marker entram em `_load_tld_from_r2` normalmente; só os sem marker viram falha.
2. `_load_tld_from_r2` quando chamado em loop após batch: se um TLD falhar no PG, os outros continuam — **já é o comportamento** (`pipeline.py:543-555`). Validar.

### 4.3. Frontend — `/admin/ingestion`

#### 4.3.1. Nova fonte de dados única

Trocar a chamada paralela de `getOpenintelStatus + getTldStatus(czds) + getTldStatus(openintel) + ingestion/runs` por **uma única** chamada `GET /v1/ingestion/heatmap`. Isso elimina o cruzamento client-side em `page.tsx:319-432` e reduz latência da página.

A página continua chamando `summary`, `domain-counts`, `cycles`, `incidents`, `cycle-status`.

#### 4.3.2. Componente `<HeatmapCell>` redesenhado

```tsx
// Em vez de um único status, recebe r2_status e pg_status:
<div className="cell">
  <span className={dotR2(r2_status)} />
  <span className={dotPG(pg_status)} />
  {pg_status === 'ok' && <span>{formatCount(inserted)}</span>}
  {pg_status === 'failed' && <Alert />}
</div>
```

Visualmente, optar por **split horizontal**: metade superior = R2, metade inferior = PG. Tooltip exibe:
```
.com — 22/04
R2: ok (databricks 18m32s)
PG: failed — pg_load_error (server closed the connection)
Inserted: 0  Removed: 0
[Reload PG] [Rerun] [Dismiss]
```

#### 4.3.3. Cabeçalho de coluna (eixo X = data)

Componente novo `<DateHeader>` posicionado em cima de cada coluna:

```
22/04
92% ✓
1h 04m
2.1M new
3 ⚠️
```

Linha 1: data. Linha 2: `% TLDs com PG-OK`. Linha 3: duração do ciclo. Linha 4: domínios inseridos no dia. Linha 5: nº de TLDs com falha (clicável → filtra a matriz).

Dados vêm de `GET /v1/ingestion/daily-summary?date=...` (uma chamada por coluna visível, batched no servidor).

#### 4.3.4. Ações por célula

Click esquerdo na célula → popover com:
- detalhes (R2 + PG separados, reason codes legíveis, error message expansível)
- 3 botões: **Reload PG** (visível se R2-ok + PG-fail), **Rerun completo**, **Dismiss**

Cada ação faz o POST e atualiza o estado otimisticamente (`pg_status='running'`).

#### 4.3.5. Filtros novos

- Filtro **"Fase em falha"**: `qualquer | só R2 | só PG | ambas`
- Filtro **"Pendente de PG"** (R2-ok + PG-pending): mostra só os TLDs onde basta reload — útil pro caso real do usuário "tem coisa no R2 não importada".

---

## 5. Plano de execução em sprints

### Sprint 1 — Fix imediato (bloqueante; horas, não dias)

**Objetivo:** parar a sangria do TODO 012 (P03 + P01) antes de evoluir o restante.

| # | Ação | Arquivo | Validação | Endereça |
|---|---|---|---|---|
| 1.1 | Adicionar `"partial"` e `"never_attempted"` ao `TldStatusCategory` | `backend/app/schemas/czds_ingestion.py` | `curl /v1/ingestion/tld-status?source=openintel` retorna 200 | **TODO 012 P03** |
| 1.2 | Pool de conexão + retry com backoff em `_load_shard_worker` (`OperationalError`) | `ingestion/loader/delta_loader.py` | Teste sintético derrubando conexão durante COPY → run termina com `reason_code='db_disconnected_recovered'` (não `pg_load_error`) | **TODO 012 P01** |
| 1.3 | Coletar logs do Postgres em 02:30 e 09:55 UTC do incidente 29/04 + verificar restart history do container | `ssh ubuntu@158.69.211.109` | Documentar causa real em `.specs/todos/012/forensics.md` | **TODO 012 P01 (diagnóstico)** |
| 1.4 | Deploy backend + worker | — | painel `/admin/ingestion` para de quebrar; runs em `net`/`org` deixam de matar shards | — |

### Sprint 2 — Modelo de dados dual-fase

| # | Ação | Validação |
|---|---|---|
| 2.1 | Migration 037 — `ingestion_run.phase` (default `'full'` para retro-compat) | `\d ingestion_run` mostra coluna; rows existentes têm `phase='full'` |
| 2.2 | View `tld_daily_status_v` | `SELECT * FROM tld_daily_status_v WHERE day=CURRENT_DATE LIMIT 5` retorna r2_status + pg_status |
| 2.3 | `run_recorder.create_run` aceita `phase` | testes unitários do recorder |
| 2.4 | `pipeline.py` grava `phase` correto em cada caminho | rodar ciclo CZDS pequeno + DataBricks; `SELECT phase, count(*) FROM ingestion_run GROUP BY phase` mostra distribuição esperada |

### Sprint 3 — API dual-fase

| # | Ação | Validação |
|---|---|---|
| 3.1 | `GET /v1/ingestion/heatmap` | resposta tem `days[].r2_status`, `pg_status` |
| 3.2 | `GET /v1/ingestion/daily-summary` | resposta agrega corretamente; `pg_complete_pct` bate com SQL manual |
| 3.3 | `POST /tld/{source}/{tld}/reload` | dispara worker, novo `ingestion_run` com `phase='pg'` aparece |
| 3.4 | `POST /tld/{source}/{tld}/run` | dispara worker, gera `phase='r2'` + `phase='pg'` |
| 3.5 | `POST /tld/{source}/{tld}/dismiss` | grava run sintético, célula vira `no_snapshot` na próxima leitura |

### Sprint 4 — Worker endpoints granulares

| # | Ação | Validação |
|---|---|---|
| 4.1 | `POST /tld/reload` no scheduler | reproduz `_load_tld_from_r2` para um (source, tld, date) específico |
| 4.2 | `POST /tld/run` no scheduler | reproduz `_process_tld_local` ou `_submit_databricks_batch([tld])` |
| 4.3 | Auth `X-Ingestion-Token` (depende de 011 §3.7) | curl sem token → 401; com token → 202 |
| 4.4 | Fila in-memory + endpoint `GET /tld/queue` | endpoint lista 0..N pendentes |

### Sprint 5 — UI heatmap dual

| # | Ação | Validação |
|---|---|---|
| 5.1 | Substituir fetches paralelos por `GET /heatmap` | network tab mostra 1 request em vez de 4 |
| 5.2 | `<HeatmapCell>` com split R2/PG | visual + tooltip corretos para cada combinação |
| 5.3 | `<DateHeader>` com agregados por dia | clica em "3 ⚠️" → filtro `attention` |
| 5.4 | Popover com 3 botões de ação | reload dispara request, célula vira running, depois ok |
| 5.5 | Filtro "Pendente de PG" | seleciona só TLDs com R2-ok + PG-pending |

### Sprint 6 — Hardening do isolamento por TLD + Databricks contract

Endereça **TODO 012 P02** (R2 marker missing após Databricks para 9 TLDs: `au, ca, de, es, eu, fr, it, nl, uk`).

| # | Ação | Validação | Endereça |
|---|---|---|---|
| 6.1 | Refactor `_submit_databricks_batch`: ler retorno do notebook em formato estruturado (`{tld: {marker_written, parquets_written, error}}`) em vez de tratar o batch como atômico | falha de 1 TLD no notebook gera `phase='r2'` `failed` com `reason_code='databricks_per_tld_error'` apenas para aquele TLD; outros do chunk seguem para PG load | **TODO 012 P02** |
| 6.2 | Notebook Databricks (`czds_ingestion.py`, `openintel_ingestion.py`) deve gravar **manifesto JSON** no R2 ao final do job: `manifest.json` com lista de `(tld, status, marker_path, parquet_count, bytes_written, error?)` | inspecionar R2 após próximo run: `manifest.json` presente; conteúdo bate com `ingestion_run` recém criados | **TODO 012 P02 — contrato explícito** |
| 6.3 | `_load_tld_from_r2` consulta o manifesto (não só o marker) antes de tentar carregar — se manifesto diz "TLD falhou no notebook", marca direto como `databricks_per_tld_error` sem tentar listar parquets | reproduzir cenário: manifesto com 1 TLD `failed`; loader pula esse TLD com `reason_code` correto, segue carregando os outros | **TODO 012 P02** |
| 6.4 | Alarme: quando `errors > 0` ao final de um ciclo, postar incidente estruturado em `ingestion_cycle.notes` (campo novo, JSONB) listando os reason codes agregados | `SELECT notes FROM ingestion_cycle ORDER BY started_at DESC LIMIT 1` retorna lista de incidentes do ciclo | **TODO 012 P02 — observabilidade** |
| 6.5 | Teste de fogo: matar 1 TLD em `LARGE_TLDS` durante batch (mock no notebook) | outros TLDs do batch carregam normalmente; UI mostra só o TLD afetado em vermelho | — |
| 6.6 | Métrica `tld_failed_isolated_total{phase, reason}` no `/metrics` | Prometheus expõe; alerta dispara se valor > 5/dia | — |

---

## 5b. Mapeamento explícito dos problemas do TODO 012

| Problema TODO 012 | Como este plano resolve | Sprint |
|---|---|---|
| **P01** — `psycopg2.OperationalError: server closed the connection unexpectedly` em `_parallel_load_shards` (TLDs `net`, `org`) | Pool de conexão `ThreadedConnectionPool` no loader + retry com backoff (`tenacity`) em `_load_shard_worker` para `OperationalError`. Run não falha cataclismicamente: ou recupera com `reason_code='db_disconnected_recovered'`, ou marca `phase='pg' status='failed' reason_code='db_disconnected'` deixando R2 intacto para reload manual via UI. | **1.2** |
| **P01 (diagnóstico)** — falta de evidência de logs do Postgres no horário do incidente | Coleta forense formal antes de fix; documenta em `.specs/todos/012/forensics.md` se foi OOM, restart, max_connections, ou idle timeout. Influencia decisão de pool size. | **1.3** |
| **P02** — R2 marker ausente após Databricks para 9 TLDs ccTLD (`au, ca, de, es, eu, fr, it, nl, uk`) | (1) Notebook passa a gravar **manifesto JSON estruturado** no R2 com status por TLD. (2) Orchestrator parseia o retorno por TLD, não por batch. (3) Loader consulta manifesto antes de tentar carregar. (4) UI mostra falha **somente no TLD afetado**, com botão "Rerun" individual. (5) `notes` em `ingestion_cycle` agrega incidentes. | **6.1–6.4** |
| **P03** — `TldStatusItem` rejeita `"partial"` → API 500 derruba `/admin/ingestion` | Adicionar `"partial"` e `"never_attempted"` ao `TldStatusCategory`. Dropado em produção em **horas**, não esperar Sprint 5 | **1.1** |

> **Princípio aplicado de ADR-002 §"Reexecução segura":** após este plano, P02 deixa de exigir rerun do Databricks inteiro. Operador vê o TLD vermelho, clica **Reload PG** se manifesto indica que parquets existem, ou **Rerun** apenas para o TLD específico se nem isso aconteceu — sem refazer o batch dos 50 TLDs do chunk.

---

## 6. Checklist de aceite (UX)

A página `/admin/ingestion` está completa quando:

- [ ] Em cada célula, vejo **dois indicadores** (R2 + PG) com cores distintas.
- [ ] No tooltip da célula, vejo motivo separado por fase + última mensagem de erro.
- [ ] Em cima de cada coluna de data: `% TLDs OK`, duração do ciclo, total de domínios novos, nº de falhas.
- [ ] Clicar em uma célula com R2-ok + PG-fail abre popover com botão **"Reload PG"** que dispara reprocessamento sem rodar Databricks.
- [ ] Filtro "Pendente de PG" lista só TLDs com R2 pronto e PG faltando.
- [ ] Falha em 1 TLD do dia **não** marca outros TLDs como falha — cada TLD tem status independente.
- [ ] O botão "Reload PG" cria um `ingestion_run` com `phase='pg'` que aparece na lista de runs.
- [ ] Após `Reload PG` bem-sucedido, a célula transita `failed → running → ok` em < 30s sem refresh manual (polling 10s).
- [ ] Em caso de incidente como o de 29/04: **a UI mostra exatamente quais TLDs falharam em qual fase**, com motivo distinto entre "Databricks não escreveu marker" e "Postgres caiu durante COPY".
- [ ] O operador consegue, **só pela UI**, reprocessar os 9 TLDs do P02 individualmente sem rodar o batch Databricks inteiro.

---

## 7. Riscos

| Risco | Mitigação |
|---|---|
| Migration 037 trava produção (table lock em `ALTER TABLE ADD COLUMN ... DEFAULT`) | Postgres 16 faz ADD COLUMN com default constante sem rewrite — confirmado. Validar em staging. |
| View `tld_daily_status_v` ficar lenta com 10k+ TLDs × 30 dias | Criar índice composto `(source, tld, snapshot_date, status)` em `ingestion_run` se p95 > 200ms. Materializar se p95 > 1s. |
| Endpoint `POST /tld/.../reload` pode ser disparado em loop pelo operador, sobrecarregando worker | Rate limit no backend: 1 reload por (source, tld, date) por 60s. Worker já tem fila serializada. |
| `phase` sendo retro-preenchido como `'full'` em runs antigas vai dar leitura imprecisa em days passados | Aceitável: todos os runs antigos eram do caminho local (que é de fato `'full'`). Para Databricks novos, a granularidade entra a partir do deploy. Documentar cutover date no runbook. |
| Cabeçalho de coluna chamando 14 endpoints `/daily-summary` | Endpoint aceita range: `GET /daily-summary?from=...&to=...` retorna lista. Uma única chamada para o range visível. |

---

## 8. Decisões pendentes do owner

- [ ] Aprovar adição da coluna `phase` (modelagem; ADR-001 não fala dela explicitamente, mas é metadata operacional, não dado de produto — alinha com ADR-002 §D1).
- [ ] Confirmar que TODO 011 será concluído antes do Sprint 4 (dependência forte no `X-Ingestion-Token`).
- [ ] Decidir formato visual final da célula: **split horizontal** vs. **dois pontinhos lado a lado**. (Recomendação: split horizontal — mais legível em densidade alta.)
- [ ] Confirmar que o operador pode acionar `Dismiss` (operação de "marcar como sem snapshot") — implicação é que isso bloqueia novas tentativas para aquele dia até reset manual.

---

## 9. Como este plano se encaixa nos ADRs

| ADR | Relação |
|---|---|
| **ADR-001** | Não toca `domain` nem `domain_removed`. Adiciona `ingestion_run.phase` que é tabela de auditoria operacional, fora do dado de produto — alinhado com §D1 do ADR-002. |
| **ADR-002** | Implementa fielmente a arquitetura de duas fases descrita em §"Arquitetura alvo" e §"Fases canonicas por TLD". A coluna `phase` é a materialização do triplo `(source, tld, snapshot_date)` × fase já presente no texto do ADR. Endpoints de reload por TLD implementam o critério de aceite §3 ("uma falha de carga local pode ser recuperada sem recalcular o snapshot remoto"). |

---

## 10. Encerramento

Este TODO fecha quando:
- Os 6 sprints estão `done` com validações verdes.
- O checklist de UX (§6) passa em produção.
- O usuário confirma que consegue **ver e reprocessar** TLDs com R2-ok + PG-pending sem abrir psql nem usar curl.

Após o fechamento, **TODO 010 e TODO 012 podem ir a `done`** — os sintomas que catalogam ficam estruturalmente endereçados (010: visibilidade; 012: P03 fix em Sprint 1, P01/P02 ficam em TODO 011).
