# Análise de Performance — CZDS Ingestor

> Gerado em: 2026-04-03
> Base: dados reais de produção (`obs` PostgreSQL, logs do worker)
> Revalidado em código em: 2026-04-08 (sem acesso direto ao banco/logs de produção neste ciclo)

---

## Revalidação (2026-04-08)

### Escopo de validação
- Validação estática feita no código e configuração versionada deste repositório.
- Itens dependentes de estado runtime (ex.: run travado específico de `.com`, throughput real do dia, tamanho atual de índices em produção) continuam **não verificáveis** sem consulta ao ambiente produtivo.

### O que permanece válido
| Hipótese original | Status em 2026-04-08 | Evidência no repositório |
|---|---|---|
| `CZDS_RUNNING_STALE_MINUTES = 60` pode matar runs longos | ✅ Confirmado | `backend/app/core/config.py` mantém `60`; `infra/stack.yml` e `infra/stack.dev.yml` não sobrescrevem |
| Batch fixo de 50k | ✅ Confirmado | `_BATCH_SIZE = 50_000` em `backend/app/services/use_cases/apply_zone_delta.py` |
| Processamento serial por TLD no worker | ✅ Confirmado | `for tld in tlds` em `backend/app/worker/czds_ingestor.py` |
| Reuso de arquivo local por até 24h pode perpetuar `.gz` ruim após falha | ✅ Confirmado | `sync_czds_tld` reutiliza `/data/czds/{tld}.zone.gz` se `mtime < 24h`; remoção só no sucesso |
| PostgreSQL sem tuning explícito no stack | ✅ Confirmado | `infra/stack.yml` e `infra/stack.dev.yml` não definem `shared_buffers`, `work_mem`, `max_wal_size`, etc. |

### O que precisa ser tratado como parcialmente válido
| Hipótese original | Reavaliação | Observação |
|---|---|---|
| "Com timeout=60, `.com` será morto durante execução normal de 4–6h" | ⚠️ Parcial | O código faz heartbeat (`touch_run`) em etapas e `update_progress` a cada batch; timeout de 60 tende a atingir runs realmente travados, não necessariamente runs longos saudáveis. |
| "Run fantasma de `.com` há 4+ dias" | ❓ Não verificável agora | Era verdadeiro no recorte de 2026-03-29 do documento; requer query atual em produção para confirmar persistência. |

### Detalhes adicionais que não estavam no documento original

#### 1) Quarentena automática de TLD (novo mitigador operacional)
- Há política de quarentena para TLD com erro 403/404 via `czds_tld_policy`.
- Config padrão:
  - `CZDS_TLD_FORBIDDEN_SUSPEND_HOURS = 168`
  - `CZDS_TLD_NOT_FOUND_SUSPEND_HOURS = 168`
- Isso reduz retries inúteis para TLD sem acesso/autorização.

#### 2) Pré-validação de autorização antes do download
- O fluxo consulta `list_authorized_tlds()` antes de baixar a zone.
- Se o TLD não estiver na lista atual da conta, o run falha cedo (404 lógico), evitando tráfego e tentativa desnecessária.

#### 3) Ordenação inteligente dos TLDs no worker
- O worker ordena por `tld_domain_count_mv` crescente (menores primeiro), com fallback para env.
- Isso melhora tempo de bootstrap parcial, embora o loop ainda seja serial.

#### 4) Proteções de consistência já presentes
- Lock por TLD com advisory lock (`pg_try_advisory_lock`), evitando execução paralela concorrente para mesmo TLD.
- Cleanup de artefato S3 órfão quando run falha após upload.
- Cleanup do cache local apenas em sucesso (reduz lixo em cenário saudável, mas mantém risco de reuso de arquivo corrompido no cenário de falha).

#### 5) Risco operacional adicional (fora do foco de performance, mas crítico)
- `infra/stack.dev.yml` contém credenciais CZDS em texto plano.
- Recomendado mover para secrets/variáveis externas e rotacionar credenciais.

---

## Resumo Executivo

O pipeline de ingestão CZDS funciona bem para a maioria dos TLDs (80+ TLDs em ~4.6h), mas possui **dois gargalos críticos** que impedem a operação correta:

1. **`.com` nunca completa** — 170M+ domínios com PostgreSQL mal configurado (128MB `shared_buffers`) causa quedas de conexão/OOM durante upserts em índices de 13GB
2. **PostgreSQL subdimensionado** — configurações padrão para uma base de 50GB com 192M+ registros

---

## Estado Atual de Produção

### Banco de Dados
| Métrica | Valor |
|---|---|
| Tamanho total do banco | **50 GB** |
| Total de domínios | **192.903.497** |
| TLDs habilitados | **103** |
| `shared_buffers` | **128 MB** ⚠️ |
| `work_mem` | **4 MB** ⚠️ |
| `maintenance_work_mem` | **64 MB** ⚠️ |
| `max_connections` | 100 |

### Execuções CZDS Recentes (27/03/2026 — ciclo completo)

| TLD | Domínios | Duração | Throughput |
|---|---|---|---|
| `com` | ~170M | ❌ **nunca completa** | — |
| `net` | 12.989.448 | 27–36 min | ~6.000–7.900 d/s |
| `org` | 12.700.192 | 26–29 min | ~7.250–8.166 d/s |
| `xyz` | 8.233.021 | 18 min | 7.537 d/s |
| `info` | 5.595.832 | 8–20 min | 4.646–10.665 d/s |
| `shop` | 4.207.853 | 13 min | 5.177 d/s |
| `online` | 3.404.564 | 8 min | 6.982 d/s |
| `app` | 2.313.610 | 15 min | **2.467 d/s** ⚠️ |
| `store` | 2.124.186 | 5.5 min | 6.454 d/s |
| `pro` | 1.117.153 | 3.2 min | 5.898 d/s |

**Ciclo completo (80 TLDs sem .com):** 4.63 horas, 34.181.367 domínios

### Outliers de baixo throughput
| TLD | Throughput | Causa provável |
|---|---|---|
| `press` | 219 d/s | Zone file com muitas linhas irrelevantes / I/O |
| `marketing` | 233 d/s | Idem |
| `software` | 293 d/s | Idem |
| `app` | 2.467 d/s | Partition `domain_app` (798MB total) com índice saturando cache |

---

## Problema #1 — `.com` nunca completa (CRÍTICO)

### Evidências
```
com | failed | 2026-03-28 04:43 → 2026-03-29 15:12 | 2068 min | 125.950.000 domínios
com | failed | 2026-03-27 21:58 → 2026-03-28 04:43 |  405 min |  39.950.000 domínios
com | failed | 2026-03-27 18:35 → 2026-03-27 21:58 |  203 min |  41.850.000 domínios
com | running | 2026-03-29 15:12 → ...             | 6972 min |   0 domínios (travado)
```

O run atual de `.com` está travado há **4+ dias** com 0 domínios inseridos. O worker crashou tentando processar `.co` (`server closed the connection unexpectedly`) e o `.com` ficou "running" indefinidamente.

### Root Cause

**a) PostgreSQL OOM durante upsert massivo**

A partição `domain_com` possui 4 índices:

| Índice | Tamanho |
|---|---|
| `domain_com_pkey` (PRIMARY KEY) | **7.726 MB** |
| `domain_com_label_idx` | **5.715 MB** |
| `domain_com_tld_first_seen_at_idx` | 1.103 MB |
| `domain_com_tld_last_seen_at_idx` | 1.087 MB |
| **Total em índices** | **~15.6 GB** |

Com `shared_buffers = 128MB`, **cada batched upsert** de 50.000 domínios no `.com` exige leitura/escrita aleatória em 15GB de índices que não cabem em memória. O PostgreSQL OOM-killer ou o processo worker cai por exaustão de memória/conexão.

**b) `CZDS_RUNNING_STALE_MINUTES = 60` muito baixo**

O `.com` leva legitimamente 4–6h para completar. Com timeout de 60 minutos, o próximo TLD que tentar chamar `recover_stale_runs` vai matar o run. Mas como `.com` é único no ciclo, ele fica preso como "running" bloqueando novos runs.

**c) Batch size fixo (50.000) para qualquer TLD**

O `_BATCH_SIZE = 50_000` é adequado para TLDs pequenos, mas para `.com` com 170M domínios cada batch dispara um commit + update de índices de 15GB. O overhead acumula exponencialmente.

---

## Problema #2 — PostgreSQL mal configurado para carga atual (CRÍTICO)

### Diagnóstico

```
shared_buffers = 128MB   # padrão PostgreSQL — para banco de 50GB é <0.3% do DB em cache
work_mem = 4MB           # upserts com unnest() de 50k linhas desperdiçam memória de sort
maintenance_work_mem = 64MB  # insuficiente para manter 15GB de índices
effective_cache_size = 4GB   # correto se a máquina tiver 4GB+ de RAM
```

### Recomendação

Assumindo servidor com **8–16 GB de RAM** (ajustar conforme hardware real):

| Parâmetro | Atual | Recomendado | Justificativa |
|---|---|---|---|
| `shared_buffers` | 128MB | **2–4 GB** | 25% da RAM disponível |
| `work_mem` | 4MB | **64–128 MB** | Sort/hash de 50k linhas em unnest |
| `maintenance_work_mem` | 64MB | **512 MB – 1 GB** | Manutenção de índices grandes |
| `max_wal_size` | 1GB | **4–8 GB** | Evita checkpoints frequentes durante bulk load |
| `checkpoint_completion_target` | 0.5 | **0.9** | Distribui escritas de checkpoint |
| `wal_buffers` | auto | **64 MB** | Buffer WAL para bulk inserts |
| `random_page_cost` | 4.0 | **1.1** | Se usando SSD |

---

## Problema #3 — Processamento serial sem paralelismo

O loop em `czds_ingestor.py` processa 1 TLD por vez:

```python
for tld in tlds:
    run_sync_cycle([tld])  # serial
```

**Impacto medido:**
- 80 TLDs de ciclo completo = 4.63h
- TLDs com < 100k domínios terminam em < 30 segundos
- Tempo ocioso entre downloads de TLDs pequenos é significativo

Paralelizar TLDs pequenos (< 1M domínios) poderia reduzir o ciclo de 4.6h para **~2h**.

---

## Problema #4 — Falhas repetidas de `.biz` e `.top` (baixo impacto, mas ruidoso)

```
biz | failed | Compressed file ended before the end-of-stream marker was reached
top | failed | Compressed file ended before the end-of-stream marker was reached
```

Ocorreu 3+ vezes na mesma sessão. O download foi corrompido/interrompido. O worker não faz retry com redownload — tenta reusar o arquivo corrompido em cache.

**Causa:** A lógica de reuso de arquivo local (`if local_path.exists() and mtime < 24h`) reutiliza um `.gz` corrompido em todas as tentativas subsequentes.

---

## Problema #5 — `.com` run fantasma travado há 4+ dias

O run atual de `.com` (`started_at = 2026-03-29 15:12`, `domains_seen = 0`, `status = running`) está completamente parado. O `recover_stale_runs` só é acionado quando `.com` é tentado novamente, mas o cooldown de 24h + o próprio status "running" bloqueiam novos runs.

**Ação imediata necessária:**
```sql
UPDATE ingestion_run
SET status = 'failed',
    finished_at = NOW(),
    updated_at = NOW(),
    error_message = 'Manually failed — stale run stuck for 4+ days'
WHERE tld = 'com' AND status = 'running';
```

---

## Roadmap de Melhorias

### 🔴 Prioridade Alta (implementar agora)

#### 1. Corrigir PostgreSQL config
Editar `postgresql.conf` no container ou via variáveis de ambiente no stack:

```ini
shared_buffers = 2GB
work_mem = 64MB
maintenance_work_mem = 512MB
max_wal_size = 4GB
checkpoint_completion_target = 0.9
wal_buffers = 64MB
random_page_cost = 1.1
```

**Impacto esperado:** Throughput de `.net`/`.org` deve aumentar 20–40%. `.com` pode completar em < 3h.

#### 2. Aumentar `CZDS_RUNNING_STALE_MINUTES` para TLDs grandes

Aumentar de 60 para **480 minutos** (8 horas) via env var. O `.com` precisa de até 6h. O timeout atual causa o loop infinito de stale recovery.

```yaml
# stack.yml / stack.dev.yml
CZDS_RUNNING_STALE_MINUTES: 480
```

#### 3. Limpar o run fantasma do `.com`

Executar o SQL acima manualmente ou via endpoint de admin para liberar o `.com` para um novo ciclo.

---

### 🟡 Prioridade Média (próximo sprint)

#### 4. Batch size adaptativo por tamanho do TLD

```python
# Em apply_zone_delta.py
def _batch_size_for(tld: str, domain_count_estimate: int) -> int:
    if domain_count_estimate > 10_000_000:
        return 100_000  # TLDs gigantes: batch maior reduz overhead de commit
    if domain_count_estimate > 1_000_000:
        return 75_000
    return 50_000  # padrão atual
```

Para `.com`, dobrar o batch de 50k para 100k reduz pela metade o número de commits (3.400 → 1.700 commits), diminuindo overhead de WAL e checkpoint.

#### 5. Corrigir reuso de arquivo corrompido

Em `sync_czds_tld.py`, ao capturar exceção de gzip corrompido, deletar o arquivo local antes do retry:

```python
except (gzip.BadGzipFile, EOFError, zlib.error) as exc:
    # Arquivo corrompido — remover cache e forçar redownload
    if local_path and local_path.exists():
        local_path.unlink()
    # ... fail run normalmente
```

Isso resolve as falhas repetidas de `.biz` e `.top`.

#### 6. Paralelizar TLDs pequenos

Processar em grupos paralelos (ThreadPoolExecutor) TLDs com < 500k domínios. Manter serial TLDs > 1M para não saturar conexões DB/S3.

```python
# Exemplo conceitual
small_tlds = [t for t in tlds if estimated_count(t) < 500_000]
large_tlds = [t for t in tlds if estimated_count(t) >= 500_000]

# Processar grandes em série, pequenos em paralelo (max_workers=4)
with ThreadPoolExecutor(max_workers=4) as pool:
    pool.map(sync_one_tld, small_tlds)
for tld in large_tlds:
    sync_one_tld(tld)
```

**Impacto estimado:** Ciclo de 80 TLDs reduziria de 4.6h para ~2h (excluindo .com).

---

### 🟢 Prioridade Baixa (otimização futura)

#### 7. Estratégia de COPY + staging para TLDs acima de 10M domínios

Para `.com`, `.net`, `.org`: usar `COPY` via `psycopg2` + tabela temporária e substituição atômica, em vez de upsert linha-a-linha:

```sql
-- 1. Carregar em staging (sem índices)
COPY domain_staging (name, tld, label) FROM STDIN;

-- 2. Merge atômico
INSERT INTO domain SELECT ... FROM domain_staging
ON CONFLICT (name, tld) DO UPDATE SET last_seen_at = ...;

-- 3. Drop staging
```

O `COPY` é 5–10x mais rápido que `INSERT ... unnest()` para volumes > 10M.

#### 8. Dropar índices não-críticos durante bulk load

Os índices `tld_first_seen_at_idx` e `tld_last_seen_at_idx` não são necessários durante a ingestão. Dropá-los antes e recriá-los após reduziria o overhead de write amplification em 2x para `.com`.

#### 9. Remover índice `label_idx` do `.com` se não for consultado

O `domain_com_label_idx` ocupa **5.7GB**. Se consultas de label em `.com` não existem na aplicação, removê-lo liberaria 5.7GB de disco e aceleraria upserts em ~30%.

---

## Resumo de Impacto Esperado

| Melhoria | Esforço | Impacto |
|---|---|---|
| Fix PostgreSQL config | Baixo (config) | Alto — habilita .com completar |
| Aumentar stale timeout | Mínimo (env var) | Crítico — para .com não ficar preso |
| Corrigir arquivo corrompido | Baixo (2 linhas) | Médio — elimina retries de .biz/.top |
| Batch adaptativo | Baixo (5 linhas) | Médio — 20-30% menos commits em TLDs grandes |
| Paralelismo de TLDs pequenos | Médio | Médio — ciclo cai de 4.6h para ~2h |
| COPY + staging para TLDs > 10M | Alto | Alto — .com potencialmente < 1h |
| Dropar índices durante load | Médio | Alto para .com/.net/.org |

---

## Métricas de Linha de Base (a medir após cada melhoria)

```sql
-- Throughput por TLD (domínios/segundo)
SELECT tld,
  ROUND(domains_seen / EXTRACT(EPOCH FROM (finished_at - started_at))) AS d_per_sec,
  ROUND(EXTRACT(EPOCH FROM (finished_at - started_at))/60, 1) AS min
FROM ingestion_run
WHERE source = 'czds' AND status = 'success'
ORDER BY started_at DESC LIMIT 20;

-- Duração total do ciclo diário
SELECT DATE(started_at),
  ROUND(EXTRACT(EPOCH FROM (MAX(finished_at) - MIN(started_at)))/3600, 2) AS hours,
  COUNT(*) AS tlds, SUM(domains_seen) AS domains
FROM ingestion_run
WHERE source = 'czds' AND status = 'success'
GROUP BY 1 ORDER BY 1 DESC;
```

### Queries adicionais para revalidar "a realidade permanece" em produção

```sql
-- 1) Verificar se ainda existe run CZDS travado (qualquer TLD)
SELECT tld, status, started_at, updated_at, finished_at, domains_seen, error_message
FROM ingestion_run
WHERE source = 'czds' AND status = 'running'
ORDER BY started_at ASC;

-- 2) Idade em minutos dos runs running (para avaliar stale timeout)
SELECT
  tld,
  ROUND(EXTRACT(EPOCH FROM (NOW() - updated_at))/60, 1) AS minutes_since_heartbeat,
  ROUND(EXTRACT(EPOCH FROM (NOW() - started_at))/60, 1) AS minutes_since_start,
  domains_seen
FROM ingestion_run
WHERE source = 'czds' AND status = 'running'
ORDER BY minutes_since_heartbeat DESC;

-- 3) Falhas recorrentes de gzip/corrupção por TLD
SELECT tld, count(*) AS failures, max(started_at) AS last_failure
FROM ingestion_run
WHERE source = 'czds'
  AND status = 'failed'
  AND error_message ILIKE '%end-of-stream%'
GROUP BY tld
ORDER BY failures DESC, last_failure DESC;
```
