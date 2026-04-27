# 009 — Análise Completa e Plano de Execução

> **Data:** 2026-04-27  
> **Contexto:** Revisão da ADR-002 + resolução dos 7 incidentes catalogados + melhorias de arquitetura

---

## 1. Revisão da ADR-002

### Veredito: Arquitetura sólida, com lacunas de contrato operacional

A ADR-002 é **bem escrita** e coerente com a ADR-001. Os princípios estão corretos:
- Delta por TLD como unidade operacional ✅
- Append-only com `ON CONFLICT DO NOTHING` ✅
- Separação de auditoria (`ingestion_run`) do dado de produto (`domain`) ✅
- R2 como contrato operacional (não cache) ✅
- Fases canônicas SKIP / LOAD_ONLY / FULL_RUN ✅

### Lacunas identificadas na ADR-002

| # | Lacuna | Impacto | Gravidade |
|---|--------|---------|-----------|
| L1 | ADR declara `ON CONFLICT DO NOTHING` mas o loader usa `COPY` direto sem dedup | Reruns falham com `duplicate key` — contradiz a promessa de idempotência | **Crítico** |
| L2 | ADR não especifica contrato mínimo que o notebook Databricks deve cumprir para ser considerado `SUCCESS` | Databricks retorna `SUCCESS` sem gravar marker no R2 | **Crítico** |
| L3 | ADR não define o que acontece quando `delta_removed` falha mas `delta_added` já foi aplicado | Banco fica em estado parcial sem mecanismo de recuperação | **Alto** |
| L4 | ADR separa auditoria de dado de produto, mas não conecta o pipeline canônico ao `openintel_tld_status` | Sucesso real de ingestão não reconcilia a tabela derivada → UI incorreta | **Alto** |
| L5 | ADR não especifica limites de tamanho de batch nem estratégia de particionamento para Databricks | Batches grandes causam OOM (OpenINTEL 302 TLDs) e rate-limit (CZDS 1101 TLDs) | **Alto** |
| L6 | ADR menciona heartbeat mas não define como a UI diferencia "ciclo ativo na fase de markers" de "nenhum run running" | `running_active_count=0` com ciclo real em andamento | **Médio** |
| L7 | ADR não define timezone canônico para "status do dia" | Backend usa UTC, frontend usa dia local do navegador → contradições visuais | **Médio** |

### Recomendação para a ADR-002

A ADR-002 deveria ser evoluída para status **Aceita** com um addendum contendo:
1. Contrato mínimo de artefatos que o notebook deve produzir
2. Estratégia de idempotência no loader (staging table)
3. Política de particionamento de batches Databricks
4. Definição do timezone canônico para observabilidade
5. Comportamento esperado em carga parcial (added ok, removed falhou)

---

## 2. Diagnóstico Root-Cause dos 7 Incidentes

### Incidente 1 — OOM no OpenINTEL batch grande (302 TLDs)

```
Run: 167790765356821
Erro: Execution ran out of memory
```

**Root cause:** O notebook processa todos os TLDs em um único job Databricks serverless. Com 302 TLDs, a materialização simultânea de snapshots + diff excede a memória disponível.

**Solução proposta:**
- Implementar política de batch-size no submitter: `DATABRICKS_OPENINTEL_BATCH_SIZE=50`
- Classificar TLDs por volume estimado (query `domain_count` por TLD) e separar TLDs grandes em batches menores
- Considerar batch-size dinâmico: `batch_size = max(10, min(50, total_memory_budget / avg_tld_size))`

**Complexidade:** Média  
**Arquivo principal:** `ingestion/databricks/submitter.py`, `pipeline.py` L627-719

---

### Incidente 2 — Rate limit ICANN no CZDS batch grande (1101 TLDs)

```
Run: 346005775360656
Erro: 429 Client Error em https://account-api.icann.org/api/authenticate
```

**Root cause:** O notebook autenticando individualmente para cada TLD do batch, sem reutilizar token. 1101 autenticações simultâneas ou sequenciais rápidas saturaram o rate limit da ICANN.

**Solução proposta:**
1. **Imediata:** Reutilizar token de autenticação ICANN no notebook (session token com TTL)
2. **Backoff:** Implementar retry com exponential backoff + jitter para 429
3. **Batch-size:** Limitar `DATABRICKS_CZDS_BATCH_SIZE=100` para distribuir carga
4. **Concorrência:** Serializar downloads por bloco com cooldown entre grupos

**Complexidade:** Média  
**Arquivo principal:** Notebook Databricks CZDS

---

### Incidente 3 — `removed_day` nulo no delta_removed (.com e .blog)

```
Runs: 935176740101302 (.com), 763318525078691 (.blog)
Erro: null value in column "removed_day" violates not-null constraint
```

**Root cause:** O notebook Databricks gera o parquet de `delta_removed` sem preencher a coluna `removed_day`. O loader (`delta_loader.py` L346-354) usa `added_day` como fallback para domain, mas para `domain_removed` a coluna `removed_day` **não** é derivada automaticamente — ela vem direta do parquet com `\N`.

**Solução proposta (no loader, não no notebook):**
```python
# delta_loader.py — _load_shard_worker
# Para columns de domain_removed, sanitizar removed_day nulo
if "removed_day" in args.columns and "added_day" not in args.columns:
    if "removed_day" in df.columns:
        df = df.with_columns(
            pl.when(pl.col("removed_day").is_null())
            .then(pl.lit(args.added_day))
            .otherwise(pl.col("removed_day"))
            .alias("removed_day")
        )
```

**Complementar:** Corrigir o notebook para preencher `removed_day` na origem.

**Complexidade:** Baixa  
**Arquivo principal:** `ingestion/loader/delta_loader.py` L158-211

---

### Incidente 4 — Rerun falha por `duplicate key` (idempotência quebrada)

```
TLD: openintel/at
Erro: duplicate key value violates unique constraint "domain_at_pkey"
```

**Root cause:** O `_load_shard_worker` faz `COPY` direto na partição (`cur.copy_expert(COPY partition FROM STDIN)`). COPY não suporta `ON CONFLICT DO NOTHING`. Quando os mesmos dados já existem (rerun do snapshot), a PK é violada.

**Este é o bug mais crítico do pipeline.** Ele invalida completamente a semântica de `LOAD_ONLY` e qualquer rerun de recuperação. A ADR-002 assume idempotência que o código não implementa.

**Solução proposta — Staging table por execução:**

```python
def _load_shard_worker(args: _ShardArgs) -> int:
    """COPY → temp table, then INSERT ... ON CONFLICT DO NOTHING into partition."""
    # ... (leitura do parquet igual) ...
    
    conn = psycopg2.connect(args.database_url)
    try:
        with conn.cursor() as cur:
            # Criar temp table com mesma estrutura
            temp = f"_stage_{args.partition}_{args.shard_idx}"
            cur.execute(f"""
                CREATE TEMP TABLE {temp} (LIKE {args.partition} INCLUDING DEFAULTS)
                ON COMMIT DROP
            """)
            
            # COPY para temp (rápido, sem constraints)
            cur.copy_expert(
                f"COPY {temp} ({col_list}) FROM STDIN"
                f" WITH (FORMAT text, DELIMITER E'\\t', NULL '\\N')",
                buf,
            )
            
            # INSERT com dedup
            cur.execute(f"""
                INSERT INTO {args.partition} ({col_list})
                SELECT {col_list} FROM {temp}
                ON CONFLICT DO NOTHING
            """)
            inserted = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    return inserted
```

**Impacto de performance:** Marginal. O overhead de temp table é insignificante comparado ao I/O de R2 + rebuild de índices.

**Complexidade:** Média  
**Arquivo principal:** `ingestion/loader/delta_loader.py` L158-211

---

### Incidente 5 — `openintel_tld_status` não reconcilia após sucesso

```
TLD: openintel/ae → success com 140830 rows
openintel_tld_status: last_ingested_snapshot_date=NULL, last_probe_outcome=new_snapshot_pending_or_failed
```

**Root cause:** O pipeline canônico (`ingestion/orchestrator/pipeline.py`) **nunca** atualiza `openintel_tld_status`. Essa tabela só é escrita pelo módulo legado `sync_openintel_tld.py` (que está deprecado, L1-6). O pipeline novo registra sucesso apenas em `ingestion_run`.

**Solução proposta (2 alternativas):**

**Opção A — Reconciliação inline no pipeline (recomendada):**
Após `finish_run(..., status="success")`, inserir lógica para atualizar `openintel_tld_status`:

```python
# pipeline.py — após finish_run com success para source="openintel"
if source == "openintel" and db_url:
    _reconcile_openintel_status(db_url, tld, snap_str)
```

**Opção B — Derivar `openintel_tld_status` a partir de `ingestion_run`:**
View materializada ou consulta que calcula o status a partir de `ingestion_run`. Elimina a tabela derivada como fonte de verdade.

**Recomendação:** Opção A no curto prazo (menos invasiva), Opção B no médio prazo (elimina dual-write).

**Complexidade:** Baixa (Opção A), Média (Opção B)  
**Arquivo principal:** `ingestion/orchestrator/pipeline.py` L276-286, L357-365

---

### Incidente 6 — Databricks SUCCESS sem marker R2 (openintel/ag)

```
Run Databricks: 217457305683193 → SUCCESS
Pipeline: reason_code=r2_marker_missing
```

**Root cause:** O estado `TERMINATED/SUCCESS` do Databricks indica que o **job completou sem exceção no driver**, mas não garante que o **notebook gravou todos os artefatos esperados**. O marker é o último artefato gravado; se o notebook falhou silenciosamente no upload do marker (ou escreveu em prefixo errado), o loader encontra sucesso remoto sem dados consumíveis.

**Solução proposta:**

1. **Validação pós-Databricks reforçada:**
   - Após SUCCESS do Databricks, verificar:
     - marker existe no prefixo esperado
     - pelo menos 1 parquet de delta existe
   - Se não: `reason_code = "databricks_contract_violation"`

2. **No notebook:** Adicionar validação explícita antes de gravar o marker:
   - Contar rows escritas em parquet
   - Só gravar marker se `delta_count > 0` ou `delta_removed_count >= 0`
   - Logar `snapshot_date` usado no prefixo do R2

3. **Diagnóstico:** Verificar no R2 se os parquets foram gravados com snapshot_date diferente do esperado

**Complexidade:** Média  
**Arquivo principal:** Notebook Databricks, `pipeline.py` L317-388

---

### Incidente 7 — Carga parcial (added ok, removed falhou) → estado inconsistente

```
TLD: czds/blog
domain_blog: 490 rows carregados ✅
domain_removed_blog: falhou (removed_day nulo) ❌
ingestion_run: failed
```

**Root cause:** O `load_delta` executa `delta_added` e `delta_removed` sequencialmente sem transação atômica entre eles. Quando `delta_removed` falha, `delta_added` já foi commitado. O `_safe_reattach` reconecta as partições, mas os dados de `domain` já estão no banco.

**Solução proposta — Recuperação automática em 2 níveis:**

**Nível 1 — Sanitização preventiva (corrige Incidente 3):**
Resolver `removed_day` nulo no loader antes do COPY (elimina a causa mais comum).

**Nível 2 — Retry parcial inteligente:**
```python
# No load_delta, após falha de removed:
except Exception as exc:
    if added_loaded > 0 and "removed" in str(exc).lower():
        # Added já foi commitado — tentar recuperar removed separadamente
        try:
            # Sanitizar e retentar apenas removed
            removed_loaded = _retry_removed_with_sanitization(...)
            return {
                "added_loaded": added_loaded,
                "removed_loaded": removed_loaded,
                "status": "recovered",
                "recovery_type": "removed_only",
            }
        except Exception:
            # Marcar como carga parcial para auditoria
            return {
                "added_loaded": added_loaded,
                "removed_loaded": 0,
                "status": "partial",
                "partial_error": str(exc),
            }
    raise
```

**Nível 3 — Reason codes explícitos no pipeline:**
- `partial_load_recovered` — added ok + removed sanitizado e retentado com sucesso
- `partial_load_added_only` — added ok + removed falhou irreversivelmente
- `pg_load_error` — ambos falharam

**Complexidade:** Alta  
**Arquivo principal:** `ingestion/loader/delta_loader.py` L258-393

---

## 3. Problemas de Observabilidade (Fase 4 do plan.md)

### P1 — Desalinhamento temporal UTC vs local

**Problema:** `/v1/ingestion/tld-status` filtra por `started_at::date = today` em UTC. O heatmap no frontend agrupa por dia local do navegador. Um run às 22h BRT (01h UTC do dia seguinte) aparece no heatmap como "hoje" mas no tld-status como "amanhã".

**Solução:**
- Backend deve aceitar `timezone` como query param e ajustar o recorte
- Ou: frontend deve enviar datas em UTC explicitamente
- **Preferência:** Backend sempre retornar timestamps ISO com timezone; frontend converte para exibição

### P2 — `never_run` vs `sem execução hoje`

**Problema:** O status `never_run` é usado tanto para "nunca existiu run" quanto "não rodou hoje". São semânticas diferentes.

**Solução:** Separar em:
- `never_attempted` — nenhum `ingestion_run` histórico existe
- `no_run_today` — existe histórico mas nada hoje
- `healthy` / `degraded` / `failed` — baseado em janela configurável

### P3 — Marker R2 não exposto na UI

**Problema:** O painel não mostra se existe marker no R2 para um dado `source + tld + snapshot_date`. Isso dificulta auditar casos de `LOAD_ONLY` e `r2_marker_missing`.

**Solução:** Adicionar ao endpoint `/v1/ingestion/tld-status`:
```json
{
  "marker_present": true,
  "marker_snapshot_date": "2026-04-20",
  "marker_checked_at": "2026-04-27T01:00:00Z",
  "inferred_phase": "load_only"
}
```

---

## 4. Plano de Execução Priorizado

### Fase A — Correções Críticas (bloqueiam qualquer rerun seguro)

| # | Item | Dependência | Complexidade | Arquivos |
|---|------|-------------|-------------|----------|
| A1 | **Idempotência do loader** — staging table + ON CONFLICT DO NOTHING | Nenhuma | Média | `delta_loader.py` |
| A2 | **Sanitização de `removed_day` nulo** no loader | Nenhuma | Baixa | `delta_loader.py` |
| A3 | **Reconciliação `openintel_tld_status`** após sucesso no pipeline canônico | Nenhuma | Baixa | `pipeline.py` |

**A1 é pré-requisito para qualquer rerun em produção.** Sem isso, `LOAD_ONLY` e qualquer recuperação automática estão quebrados.

### Fase B — Resiliência de Batches Databricks

| # | Item | Dependência | Complexidade | Arquivos |
|---|------|-------------|-------------|----------|
| B1 | **Batch-size configurável** para OpenINTEL e CZDS | Nenhuma | Média | `submitter.py`, `pipeline.py` |
| B2 | **Token reuse** para CZDS no notebook | Nenhuma | Média | Notebook CZDS |
| B3 | **Validação pós-Databricks** — checar parquets + marker antes de declarar sucesso | A1 | Média | `pipeline.py` |

### Fase C — Observabilidade Correta

| # | Item | Dependência | Complexidade | Arquivos |
|---|------|-------------|-------------|----------|
| C1 | **Separar `never_attempted` de `no_run_today`** no tld-status | Nenhuma | Baixa | `ingestion.py` (router) |
| C2 | **Timezone canônico** — resolver contradição UTC vs local | Nenhuma | Média | Router + frontend page |
| C3 | **Marker R2 no tld-status** — expor marker_present/phase inferida | B3 | Média | Router + frontend |
| C4 | **Estado de carga parcial** na UI | A2 | Baixa | Frontend |

### Fase D — Recuperação Automática

| # | Item | Dependência | Complexidade | Arquivos |
|---|------|-------------|-------------|----------|
| D1 | **Retry parcial** — removed-only quando added já foi aplicado | A1, A2 | Alta | `delta_loader.py`, `pipeline.py` |
| D2 | **Reason codes estendidos** — `partial_load_recovered`, `databricks_contract_violation` | D1 | Baixa | `pipeline.py`, `run_recorder.py` |

### Fase E — Testes

| # | Item | Dependência | Complexidade | Arquivos |
|---|------|-------------|-------------|----------|
| E1 | **Teste de idempotência** — rerun do mesmo snapshot sem erro | A1 | Média | Tests |
| E2 | **Teste de sanitização** — removed_day nulo → snapshot_date | A2 | Baixa | Tests |
| E3 | **Teste de carga parcial** — added ok + removed falha → recovery | D1 | Média | Tests |
| E4 | **Teste de stale recovery** — run running sem heartbeat → failed | Nenhuma | Baixa | Tests |

---

## 5. Ordem de Execução Recomendada

```
A1 (Idempotência) ──→ D1 (Retry Parcial) ──→ D2 (Reason codes)
                  ╲                        ╲
A2 (Sanitizar)  ──→ D1                 ──→ E3 (Teste carga parcial)
              ╲
               ──→ C4 (Estado parcial UI)

A3 (Reconciliar openintel) ──→ C3 (Marker R2 na UI)
B1 (Batch-size) ──→ B3 (Validação pós-Databricks) ──→ C3
A1 ──→ E1 (Teste idempotência)
A2 ──→ E2 (Teste sanitização)
```

**Sequência sugerida:**  
`A1 → A2 → A3 → E1 → E2 → B1 → B2 → B3 → C1 → C2 → D1 → D2 → E3 → C3 → C4 → E4`

---

## 6. Addendum Proposto para ADR-002

Sugiro adicionar uma seção **"Contratos Operacionais"** à ADR-002 com:

### CO-1: Contrato de Artefatos do Notebook

O notebook Databricks, para ser considerado `SUCCESS` pelo loader, **deve** produzir no R2:

1. `{prefix}/{source}/delta/snapshot_date={date}/tld={tld}/*.parquet` — pelo menos 1 arquivo
2. `{prefix}/{source}/delta_removed/snapshot_date={date}/tld={tld}/*.parquet` — 0 ou mais arquivos
3. `{prefix}/{source}/markers/snapshot_date={date}/tld={tld}/done` — marker obrigatório
4. O campo `removed_day` em todo parquet de delta_removed **deve** estar preenchido com o `snapshot_date` (INTEGER YYYYMMDD)

### CO-2: Contrato de Idempotência do Loader

O `load_delta` **deve** ser seguro para rerun do mesmo `(source, tld, snapshot_date)`:
- Usar `COPY → staging table → INSERT ON CONFLICT DO NOTHING`
- Nunca falhar por `duplicate key` em dados já existentes

### CO-3: Limites de Batch Databricks

| Fonte | Batch máximo | Observação |
|-------|-------------|------------|
| OpenINTEL | 50 TLDs | Evita OOM em serverless |
| CZDS | 100 TLDs | Evita rate limit ICANN |
| CZDS `.com` | 1 (solo) | Sempre isolado |

### CO-4: Timezone Canônico

Toda referência a "hoje" ou "dia atual" na camada de observabilidade **deve** usar UTC. O frontend converte para exibição local e indica o timezone na UI.

---

## 7. Resumo de Impacto

| Métrica | Antes | Depois |
|---------|-------|--------|
| Rerun seguro do mesmo snapshot | ❌ Falha com `duplicate key` | ✅ Idempotente |
| Carga parcial (added ok, removed falhou) | ❌ Estado inconsistente, manual | ✅ Recuperação automática |
| `openintel_tld_status` após sucesso | ❌ Stale com erro legado | ✅ Reconciliado automaticamente |
| Batch OOM OpenINTEL | ❌ 302 TLDs em 1 run | ✅ Batches de 50 |
| Batch rate limit CZDS | ❌ 1101 TLDs sem token reuse | ✅ Token reutilizado + batches de 100 |
| UI "Sem execução" com histórico | ❌ Falso negativo | ✅ `no_run_today` vs `never_attempted` |
| Marker R2 visível na UI | ❌ Parcial (só OpenINTEL) | ✅ Unificado CZDS + OpenINTEL |
