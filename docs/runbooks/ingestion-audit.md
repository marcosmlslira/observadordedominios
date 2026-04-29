# Auditoria de Completude de Ingestão

> Processo recorrente para garantir que 100% dos TLDs disponíveis no OpenINTEL
> e CZDS foram ingeridos no R2 e no PostgreSQL, com volumes coerentes.
>
> **Cadência recomendada:** execute as camadas 0–2 diariamente (após o ciclo das 04h UTC),
> a camada 3 semanalmente e a camada 4 mensalmente.

---

## Visão geral das camadas

```
[Fonte externa]
  CZDS API (ICANN)          OpenINTEL catálogo
       │                           │
       ▼                           ▼
  Camada 0 — Catálogo: TLDs autorizados vs. ingestion_tld_policy
       │
       ▼
  Camada 1 — R2: marker success.json presente por TLD por data de snapshot
       │
       ▼
  Camada 2 — PostgreSQL: runs phase='pg'/'full' success por TLD por data
       │
       ▼
  Camada 3 — Coerência: contagens de domínios no PG vs. ingestion_run.domains_seen
       │
       ▼
  Camada 4 — Continuidade: sem gaps > limiar por TLD nos últimos 30 dias
```

---

## Camada 0 — Catálogo: o que está autorizado vs. o que está configurado

**Objetivo:** confirmar que nenhum TLD autorizado nas fontes externas está
faltando na `ingestion_tld_policy`. Divergências aqui significam TLDs que nunca
serão processados.

### 0.1 CZDS — TLDs autorizados pelo ICANN

```bash
# Liste TLDs autorizados via API CZDS e compare com o que está na policy
docker exec <backend_container> python3 -c "
import os, psycopg2
from ingestion.config.settings import get_settings
from ingestion.sources.czds.client import CZDSClient

cfg = get_settings()
client = CZDSClient(cfg)
token = client.authenticate()
authorized = client.authorized_tlds(token)

conn = psycopg2.connect(cfg.database_url)
with conn.cursor() as cur:
    cur.execute(\"SELECT tld FROM ingestion_tld_policy WHERE source='czds' AND is_enabled\")
    in_policy = {r[0] for r in cur.fetchall()}

not_seeded = authorized - in_policy
not_authorized = in_policy - authorized

print(f'Autorizados pela ICANN: {len(authorized)}')
print(f'Na policy (habilitados): {len(in_policy)}')
print(f'Autorizados mas NÃO na policy: {sorted(not_seeded)[:20]}')
print(f'Na policy mas NÃO mais autorizados: {sorted(not_authorized)[:20]}')
"
```

**Esperado:** `not_seeded` e `not_authorized` vazios.  
**Ação se falhar:** rodar `python -m ingestion seed-policies --source czds`

### 0.2 OpenINTEL — TLDs do catálogo vs. policy

```sql
-- TLDs na policy OpenINTEL habilitados
SELECT count(*) AS total_habilitados,
       count(*) FILTER (WHERE priority <= 100) AS zonefile,
       count(*) FILTER (WHERE priority BETWEEN 101 AND 300) AS web_small,
       count(*) FILTER (WHERE priority > 300) AS web_large
FROM ingestion_tld_policy
WHERE source = 'openintel' AND is_enabled = true;
```

**Esperado:** ~150 total (10 zonefile + 130+ web_small + 2 web_large: br, de).

### 0.3 TLDs desabilitados sem motivo explícito

```sql
-- TLDs na policy mas desabilitados — precisam de justificativa
SELECT source, tld, priority, updated_at
FROM ingestion_tld_policy
WHERE is_enabled = false
ORDER BY source, priority;
```

**Ação:** se houver TLDs desabilitados sem ser intencional, reabilitar via API
(`PATCH /v1/ingestion/tld-policy/{source}/{tld}`) ou pelo painel admin.

---

## Camada 1 — R2: presença do marker por TLD

**Objetivo:** confirmar que todos os TLDs habilitados têm um marker `success.json`
no R2 para o snapshot mais recente esperado. O marker é o "contrato" entre R2 e
o loader do PostgreSQL — sem ele o PG não pode ser carregado.

> **Proxy confiável:** a tabela `ingestion_run` com `phase IN ('r2','full')` e
> `status = 'success'` equivale a "marker existe no R2". Não é necessário listar
> objetos do S3 para a auditoria rotineira.

### 1.1 Cobertura R2 do dia — quantos TLDs têm marker hoje

```sql
-- Por fonte: TLDs com r2 ok hoje vs. total habilitado
WITH today_r2 AS (
    SELECT DISTINCT source, tld
    FROM ingestion_run
    WHERE phase IN ('r2', 'full')
      AND status = 'success'
      AND COALESCE(snapshot_date, started_at::date) = CURRENT_DATE
),
enabled AS (
    SELECT source, tld FROM ingestion_tld_policy WHERE is_enabled = true
)
SELECT
    e.source,
    count(*)                                      AS total_habilitados,
    count(r.tld)                                  AS r2_ok_hoje,
    count(*) - count(r.tld)                       AS r2_faltando,
    round(count(r.tld)::numeric / count(*) * 100, 1) AS cobertura_pct
FROM enabled e
LEFT JOIN today_r2 r ON r.source = e.source AND r.tld = e.tld
GROUP BY e.source
ORDER BY e.source;
```

**Esperado:** `r2_faltando = 0` ou justificado (TLDs sem snapshot no dia — ex.:
OpenINTEL lags 2–5 dias, então `snapshot_date` pode ser D-3).

### 1.2 TLDs com R2 faltando — lista nominal

```sql
-- Lista dos TLDs habilitados sem R2 bem-sucedido nos últimos 3 dias
WITH recent_r2 AS (
    SELECT DISTINCT source, tld
    FROM ingestion_run
    WHERE phase IN ('r2', 'full')
      AND status = 'success'
      AND COALESCE(snapshot_date, started_at::date) >= CURRENT_DATE - 3
)
SELECT p.source, p.tld, p.priority
FROM ingestion_tld_policy p
LEFT JOIN recent_r2 r ON r.source = p.source AND r.tld = p.tld
WHERE p.is_enabled = true
  AND r.tld IS NULL
ORDER BY p.source, p.priority;
```

**Ação para TLDs faltando:**
- `czds/small-tld`: verificar logs do ciclo; disparar `/tld/{source}/{tld}/run`
- `czds/net,org,info,...`: verificar job Databricks no workspace
- `openintel/*`: verificar URL do snapshot no catálogo OpenINTEL; pode ser lag normal

### 1.3 Verificação direta de marker no R2 (confirma física)

```bash
# Para um TLD específico: verifica marker real no S3/R2
docker exec <worker_container> python3 -c "
from ingestion.config.settings import get_settings
from ingestion.storage.r2 import R2Storage
from ingestion.storage.layout import Layout
from datetime import date, timedelta

cfg = get_settings()
storage = R2Storage(cfg)
layout = Layout(cfg.r2_prefix)

source = 'czds'   # ou 'openintel'
tld    = 'com'    # alterar conforme necessidade
today  = date.today()

for delta in range(7):
    d = today - timedelta(days=delta)
    key = layout.marker_key(source, tld, d)
    exists = storage.exists(key)
    print(f'{d}  marker={key.split(\"/\")[-2:]}  exists={exists}')
    if exists:
        break
"
```

---

## Camada 2 — PostgreSQL: R2 → PG carregado por TLD

**Objetivo:** para cada TLD com marker R2 presente, confirmar que o PostgreSQL foi
carregado com sucesso (`phase IN ('pg','full')` + `status = 'success'`).

### 2.1 Visão geral dual-fase hoje (a partir da view)

```sql
-- Resumo por fonte: quantos TLDs em cada combinação de r2/pg status
SELECT
    source,
    r2_status,
    pg_status,
    count(*) AS tlds
FROM tld_daily_status_v
WHERE day = CURRENT_DATE
GROUP BY source, r2_status, pg_status
ORDER BY source, r2_status, pg_status;
```

**Combinações esperadas após um ciclo completo:**

| r2_status | pg_status | Significa |
|-----------|-----------|-----------|
| `success` | `success` | Completo ✅ |
| `success` | `running` | PG ainda carregando ⏳ |
| `success` | `failed`  | PG falhou — reprocessar ⚠️ |
| `success` | `NULL`    | PG nunca rodou para este snapshot ⚠️ |
| `failed`  | `NULL`    | R2 falhou — investigar ❌ |
| `NULL`    | `success` | PG-only reload (normal pós-auditoria) |

### 2.2 TLDs com R2 ok mas PG ainda pendente

```sql
-- R2 ok no snapshot mais recente, PG ainda não carregado
WITH latest_r2 AS (
    SELECT DISTINCT ON (source, tld)
        source, tld,
        COALESCE(snapshot_date, started_at::date) AS snap_date
    FROM ingestion_run
    WHERE phase IN ('r2', 'full')
      AND status = 'success'
    ORDER BY source, tld, started_at DESC
),
latest_pg AS (
    SELECT DISTINCT ON (source, tld)
        source, tld, status AS pg_status
    FROM ingestion_run
    WHERE phase IN ('pg', 'full')
    ORDER BY source, tld, started_at DESC
)
SELECT
    r.source,
    r.tld,
    r.snap_date,
    COALESCE(p.pg_status, 'never_run') AS pg_status
FROM latest_r2 r
LEFT JOIN latest_pg p ON p.source = r.source AND p.tld = r.tld
WHERE COALESCE(p.pg_status, 'never_run') != 'success'
ORDER BY r.source, r.snap_date DESC, r.tld;
```

**Ação:** para cada TLD listado, disparar reload via API:
```bash
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "$BASE/v1/ingestion/tld/{source}/{tld}/reload"
```

### 2.3 Partições do PostgreSQL existem para todos os TLDs ativos

```sql
-- TLDs com runs de sucesso mas sem partição na tabela domain
WITH active_tlds AS (
    SELECT DISTINCT source, tld
    FROM ingestion_run
    WHERE status = 'success'
      AND phase IN ('pg', 'full')
      AND started_at > now() - interval '30 days'
),
existing_partitions AS (
    SELECT relname
    FROM pg_class
    WHERE relkind = 'r'
      AND relname LIKE 'domain_%'
)
SELECT a.source, a.tld,
       'domain_' || replace(a.tld, '.', '_') AS expected_partition,
       (p.relname IS NOT NULL) AS partition_exists
FROM active_tlds a
LEFT JOIN existing_partitions p
       ON p.relname = 'domain_' || replace(a.tld, '.', '_')
WHERE p.relname IS NULL
ORDER BY a.source, a.tld;
```

**Ação se falhar:** criar partição manualmente ou via migração. Sem a partição,
o loader falha silenciosamente na fase de INSERT.

---

## Camada 3 — Coerência de quantidades

**Objetivo:** confirmar que o volume de domínios no PostgreSQL é coerente com o
que foi processado nos runs e com snapshots anteriores. Desvios grandes indicam
truncamento, duplicatas ou runs incompletos.

### 3.1 Volume total por TLD no PostgreSQL

```sql
-- Contagem atual por TLD (via materialized view, atualizada pelo ciclo)
SELECT
    m.tld,
    m.count                     AS pg_count,
    r.domains_seen              AS last_snapshot_count,
    r.snapshot_date             AS last_snapshot_date,
    round((m.count::numeric / NULLIF(r.domains_seen, 0) - 1) * 100, 2) AS desvio_pct
FROM tld_domain_count_mv m
LEFT JOIN LATERAL (
    SELECT domains_seen, snapshot_date
    FROM ingestion_run
    WHERE tld = m.tld
      AND status = 'success'
      AND domains_seen > 0
    ORDER BY started_at DESC
    LIMIT 1
) r ON true
WHERE r.domains_seen IS NOT NULL
ORDER BY abs(m.count::numeric / NULLIF(r.domains_seen, 0) - 1) DESC NULLS LAST
LIMIT 30;
```

**Esperado:** `desvio_pct` próximo de 0 para TLDs estáveis (zone files mudam <2%/dia).  
**Alerta:** desvio > 10% merece investigação — pode indicar run parcial ou
snapshot corrompido.

> ⚠️ O `domains_seen` representa o total no snapshot R2 (all active domains),
> enquanto `pg_count` é a tabela incremental (acumulado via delta). Para TLDs
> novos (primeira carga), `pg_count ≈ domains_seen`. Para TLDs com histórico longo,
> `pg_count` pode ser menor se domains_removed ainda não foi aplicado.

### 3.2 TLDs sem nenhum domínio no PostgreSQL

```sql
-- TLDs com run de sucesso mas count = 0 na MV
SELECT
    ir.source,
    ir.tld,
    ir.domains_inserted,
    ir.domains_seen,
    mv.count AS pg_count,
    ir.started_at
FROM (
    SELECT DISTINCT ON (source, tld)
        source, tld, domains_inserted, domains_seen, started_at
    FROM ingestion_run
    WHERE status = 'success' AND phase IN ('pg', 'full')
    ORDER BY source, tld, started_at DESC
) ir
LEFT JOIN tld_domain_count_mv mv ON mv.tld = ir.tld
WHERE COALESCE(mv.count, 0) = 0
  AND ir.domains_seen > 0
ORDER BY ir.source, ir.tld;
```

**Esperado:** vazio. Qualquer linha aqui indica que o delta Parquet foi processado
mas nenhum domínio foi inserido — possível falha silenciosa no COPY ou partição
incorreta.

### 3.3 Variação diária de domínios por TLD (anomalias de volume)

```sql
-- Variação diária em domains_inserted: detecta runs com volume anômalo
WITH daily AS (
    SELECT
        source, tld,
        COALESCE(snapshot_date, started_at::date) AS day,
        SUM(domains_inserted)                      AS inserted,
        SUM(domains_deleted)                       AS deleted
    FROM ingestion_run
    WHERE status = 'success'
      AND phase IN ('pg', 'full')
      AND started_at >= CURRENT_DATE - 30
    GROUP BY source, tld, day
),
stats AS (
    SELECT
        source, tld,
        avg(inserted)   AS avg_inserted,
        stddev(inserted) AS std_inserted
    FROM daily
    GROUP BY source, tld
    HAVING count(*) >= 3  -- pelo menos 3 dias para ter linha de base
)
SELECT
    d.source, d.tld, d.day,
    d.inserted,
    round(s.avg_inserted)          AS media_diaria,
    round(s.std_inserted)          AS desvio_padrao,
    round((d.inserted - s.avg_inserted) / NULLIF(s.std_inserted, 0), 1) AS z_score
FROM daily d
JOIN stats s ON s.source = d.source AND s.tld = d.tld
WHERE abs((d.inserted - s.avg_inserted) / NULLIF(s.std_inserted, 0)) > 3
ORDER BY abs((d.inserted - s.avg_inserted) / NULLIF(s.std_inserted, 0)) DESC;
```

**Esperado:** poucos ou nenhum resultado. Z-score > 3 = volume muito fora do
padrão histórico — investigar se houve problema no snapshot da fonte.

### 3.4 Refresh da materialized view (se houver divergência)

```sql
-- Forçar refresh da tld_domain_count_mv após investigação
REFRESH MATERIALIZED VIEW CONCURRENTLY tld_domain_count_mv;
```

---

## Camada 4 — Continuidade histórica (gaps por TLD)

**Objetivo:** nenhum TLD habilitado deve ficar sem ingestão além do limiar tolerável
— 2 dias para CZDS, 7 dias para OpenINTEL (que tem lag de 2–5 dias por design).

### 4.1 Dias desde o último sucesso por TLD

```sql
-- Dias sem run bem-sucedido desde o último, por TLD
WITH last_ok AS (
    SELECT DISTINCT ON (source, tld)
        source,
        tld,
        COALESCE(snapshot_date, started_at::date) AS last_ok_date
    FROM ingestion_run
    WHERE status = 'success'
      AND phase IN ('r2', 'pg', 'full')
    ORDER BY source, tld, started_at DESC
),
policy AS (
    SELECT source, tld FROM ingestion_tld_policy WHERE is_enabled = true
)
SELECT
    p.source,
    p.tld,
    l.last_ok_date,
    CURRENT_DATE - l.last_ok_date                                  AS dias_sem_run,
    CASE p.source
        WHEN 'czds'      THEN (CURRENT_DATE - l.last_ok_date) > 2
        WHEN 'openintel' THEN (CURRENT_DATE - l.last_ok_date) > 7
        ELSE false
    END                                                             AS fora_do_limiar
FROM policy p
LEFT JOIN last_ok l ON l.source = p.source AND l.tld = p.tld
WHERE l.last_ok_date IS NULL
   OR CASE p.source
          WHEN 'czds'      THEN (CURRENT_DATE - l.last_ok_date) > 2
          WHEN 'openintel' THEN (CURRENT_DATE - l.last_ok_date) > 7
          ELSE false
      END
ORDER BY p.source, dias_sem_run DESC NULLS FIRST;
```

**Esperado:** vazio (zero TLDs fora do limiar).

### 4.2 Distribuição de gaps — visão de calendário

```sql
-- Para cada TLD: conta quantos dias nos últimos 30 tiveram run ok
WITH ok_days AS (
    SELECT DISTINCT
        source, tld,
        COALESCE(snapshot_date, started_at::date) AS ok_day
    FROM ingestion_run
    WHERE status = 'success'
      AND phase IN ('r2', 'pg', 'full')
      AND started_at >= CURRENT_DATE - 30
)
SELECT
    p.source,
    p.tld,
    count(o.ok_day)                          AS dias_ok,
    30 - count(o.ok_day)                     AS dias_sem_run,
    round(count(o.ok_day)::numeric / 30 * 100, 0) AS cobertura_30d_pct
FROM ingestion_tld_policy p
LEFT JOIN ok_days o ON o.source = p.source AND o.tld = p.tld
WHERE p.is_enabled = true
GROUP BY p.source, p.tld
HAVING count(o.ok_day)::numeric / 30 < 0.7  -- < 70% de cobertura nos últimos 30 dias
ORDER BY cobertura_30d_pct ASC;
```

**Esperado:** vazio ou somente TLDs com lag documentado.  
**Threshold:** < 70% nos últimos 30 dias = TLD com problema recorrente.

### 4.3 TLDs que nunca tiveram nenhuma ingestão bem-sucedida

```sql
-- TLDs habilitados que NUNCA tiveram run de sucesso
SELECT p.source, p.tld, p.priority, p.created_at
FROM ingestion_tld_policy p
WHERE p.is_enabled = true
  AND NOT EXISTS (
      SELECT 1 FROM ingestion_run ir
      WHERE ir.source = p.source
        AND ir.tld = p.tld
        AND ir.status = 'success'
  )
ORDER BY p.source, p.priority;
```

**Esperado:** vazio para fontes maduras. Para fontes recém-configuradas, pode
haver TLDs ainda esperando o primeiro ciclo.

---

## Resumo executivo — query única de status

Execute após o ciclo diário para um resumo rápido da saúde geral:

```sql
WITH
today_summary AS (
    SELECT
        source,
        count(*) FILTER (WHERE r2_status = 'success' AND pg_status = 'success') AS completos,
        count(*) FILTER (WHERE r2_status = 'success' AND pg_status != 'success') AS r2_ok_pg_pendente,
        count(*) FILTER (WHERE r2_status = 'failed')                             AS r2_falhou,
        count(*) FILTER (WHERE r2_status = 'running' OR pg_status = 'running')   AS rodando,
        count(*)                                                                  AS total_com_atividade
    FROM tld_daily_status_v
    WHERE day = CURRENT_DATE
    GROUP BY source
),
enabled_total AS (
    SELECT source, count(*) AS total_habilitados
    FROM ingestion_tld_policy WHERE is_enabled = true GROUP BY source
)
SELECT
    e.source,
    e.total_habilitados,
    COALESCE(t.completos, 0)          AS completos,
    COALESCE(t.r2_ok_pg_pendente, 0)  AS pg_pendente,
    COALESCE(t.r2_falhou, 0)          AS r2_falhou,
    COALESCE(t.rodando, 0)            AS rodando,
    e.total_habilitados
        - COALESCE(t.total_com_atividade, 0) AS sem_atividade_hoje,
    round(
        COALESCE(t.completos, 0)::numeric / e.total_habilitados * 100, 1
    )                                 AS pct_completo
FROM enabled_total e
LEFT JOIN today_summary t ON t.source = e.source
ORDER BY e.source;
```

**Critério de saúde:** `pct_completo >= 95%` = ciclo saudável.

---

## Cadência recomendada

| Camada | Frequência | Quando executar | Responsável |
|--------|------------|-----------------|-------------|
| Resumo executivo | **Diária** | Após ciclo das 04h UTC (verificar às 07h) | Automático / on-call |
| Camada 0 (catálogo) | **Semanal** | Toda segunda-feira | Engenharia |
| Camada 1 (R2 coverage) | **Diária** | Após ciclo; checar às 07h UTC | On-call |
| Camada 2 (PG completude) | **Diária** | Junto com Camada 1 | On-call |
| Camada 3 (quantidades) | **Semanal** | Toda sexta-feira | Engenharia |
| Camada 4 (gaps históricos) | **Mensal** | Primeiro dia útil do mês | Engenharia |

---

## Ações por tipo de falha

| Falha identificada | Ação imediata | Ação raiz |
|--------------------|---------------|-----------|
| TLD não na policy (C0) | `seed-policies` | Verificar se autorização está ativa |
| R2 marker ausente — TLD pequeno (C1) | `POST /tld/{src}/{tld}/run` | Verificar logs do ciclo para o TLD |
| R2 marker ausente — Databricks (C1) | Verificar job no workspace Databricks | Verificar P02 — manifest por TLD |
| R2 ok, PG pendente (C2) | `POST /tld/{src}/{tld}/reload` | Verificar se partição existe (C2.3) |
| Partição PG ausente (C2.3) | Criar partição via `ALTER TABLE domain ATTACH PARTITION` | Verificar migration de seed de partições |
| Volume zero com run ok (C3.2) | Inspecionar delta Parquet no R2 | Verificar loader shard logs |
| Z-score > 3 em volume (C3.3) | Comparar com snapshot anterior no R2 | Verificar fonte (CZDS/OpenINTEL) |
| Gap > limiar (C4) | `POST /tld/{src}/{tld}/run` | Verificar scheduler logs para o TLD |
| TLD nunca ingerido (C4.3) | Verificar prioridade; forçar run manual | Verificar se TLD tem zona ativa |
