# ADR-001: Redesign da tabela `domain` para pipeline de ingestao otimizado

- **Status:** Proposta
- **Data:** 2026-04-23
- **Autores:** Marcos Lira, Claude (Opus 4.6)
- **Deciders:** Marcos Lira
- **Contexto tecnico:** PostgreSQL 16, particionamento LIST por TLD, GIN trigram index, pipeline Databricks + R2

---

## Contexto

A tabela `domain` e a fonte central do produto. Contem todos os dominios conhecidos e e consultada por:

1. **Similarity scan** — queries de trigram (`label % :brand`), substring (`LIKE`), exact match e punycode para detectar typosquatting/spoofing
2. **Ingestao** — bulk writes de tres fontes: CZDS (zone files gTLD), OpenINTEL (snapshots ccTLD), CertStream (CT logs real-time)
3. **Watermark delta** — scans incrementais que leem apenas dominios novos desde o ultimo scan

### Modelo atual

```sql
CREATE TABLE domain (
    name          VARCHAR(253)     NOT NULL,
    tld           VARCHAR(24)      NOT NULL,
    label         VARCHAR          NOT NULL,
    first_seen_at TIMESTAMPTZ      NOT NULL,
    last_seen_at  TIMESTAMPTZ      NOT NULL,
    PRIMARY KEY (name, tld)
) PARTITION BY LIST (tld);

-- Indices (herdados por particao)
CREATE INDEX ix_domain_label_trgm  ON domain USING gin (label gin_trgm_ops);
CREATE INDEX ix_domain_first_seen  ON domain (tld, first_seen_at DESC);
CREATE INDEX ix_domain_last_seen   ON domain (tld, last_seen_at DESC);
```

### Problemas identificados

| # | Problema | Impacto |
|---|----------|---------|
| P1 | `last_seen_at` atualizado a cada ingestao em TLDs grandes | UPDATE de 170M rows no .com toca GIN (immutable rebuild), transformando runs de 30min em 74h |
| P2 | `first_seen_at` TIMESTAMPTZ ocupa 8 bytes; precisamos apenas da resolucao de dia para watermark | ~680MB desperdicados so na particao .com (170M x 4 bytes extra) |
| P3 | `ix_domain_first_seen (tld, first_seen_at)` tem `tld` redundante | Dentro da particao `.com`, toda row tem `tld = 'com'`. A primeira coluna do indice e constante — desperidicio de ~50% do tamanho do indice |
| P4 | `ix_domain_last_seen` so serve se `last_seen_at` existir | Indice inteiro eliminavel se `last_seen_at` for removido |
| P5 | Staging table (`domain_stage`) sera desnecessaria com Databricks produzindo deltas | Complexidade de codigo mantida sem necessidade |
| P6 | Nao ha tracking de dominios removidos da zona | Similarity matches de dominios mortos nunca sao limpos |

### Forcas de design

- **Escrita:** ingestao diaria de 160M+ rows (zone files), ~50K/min (CertStream), snapshots ccTLD
- **Leitura:** similarity queries com GIN trigram em particoes de ate 170M rows
- **Watermark:** delta scans precisam ler apenas dominios novos desde o ultimo scan
- **Pipeline futuro:** Databricks faz download/diff e salva delta pronto no R2; backend so faz INSERT
- **Custo:** PostgreSQL em instancia limitada — cada byte por row importa em tabelas de centenas de milhoes

---

## Decisao

### Novo modelo

```sql
-- ================================================================
-- domain: registro canonico de dominios existentes
-- Append-only para novos dominios. Sem UPDATE de rows existentes.
-- ================================================================
CREATE TABLE domain (
    name        VARCHAR(253)    NOT NULL,
    tld         VARCHAR(24)     NOT NULL,
    label       VARCHAR         NOT NULL,
    added_day   INTEGER         NOT NULL,   -- formato YYYYMMDD (ex: 20260423)
    PRIMARY KEY (name, tld)
) PARTITION BY LIST (tld);

-- GIN trigram: essencial para similarity queries
CREATE INDEX ix_domain_label_trgm ON domain
    USING gin (label gin_trgm_ops);

-- Btree para watermark delta scans (sem tld — redundante dentro da particao)
CREATE INDEX ix_domain_added_day ON domain (added_day);
```

```sql
-- ================================================================
-- domain_removed: log de dominios que desapareceram das zonas
-- Fonte para limpeza periodica de similarity matches obsoletos.
-- ================================================================
CREATE TABLE domain_removed (
    name        VARCHAR(253)    NOT NULL,
    tld         VARCHAR(24)     NOT NULL,
    removed_day INTEGER         NOT NULL,   -- dia em que desapareceu
    PRIMARY KEY (name, tld)
) PARTITION BY LIST (tld);

CREATE INDEX ix_domain_removed_day ON domain_removed (removed_day);
```

### Resumo de mudancas

| Aspecto | Antes | Depois |
|---------|-------|--------|
| `first_seen_at` | TIMESTAMPTZ (8 bytes) | `added_day` INTEGER (4 bytes) |
| `last_seen_at` | TIMESTAMPTZ (8 bytes) | Eliminado |
| `ix_domain_first_seen` | `(tld, first_seen_at DESC)` | `(added_day)` — sem tld |
| `ix_domain_last_seen` | `(tld, last_seen_at DESC)` | Eliminado |
| Tracking de remocao | Inexistente | `domain_removed` table |
| Economia estimada (.com) | — | **~4.5 GB** (dados + indices) |
| Comportamento de UPDATE | `last_seen_at` atualizado a cada run | Append-only, `ON CONFLICT DO NOTHING` |

---

## Alternativas consideradas e rejeitadas

### A1: Particionar por source (CZDS / OpenINTEL / CertStream)

**Proposta:** sub-particoes por fonte dentro de cada TLD para permitir escritas simultaneas sem contencao.

**Rejeitada porque:**

1. **Duplicacao de dados** — o mesmo dominio `example.com` aparece no CZDS (zone file) e no CertStream (certificado emitido). Com PK `(name, tld, source)`, teriamos rows duplicadas.
2. **Zero partition pruning** — similarity queries filtram por `tld` e `label`, nunca por `source`. O PostgreSQL varreria todas as sub-particoes de cada TLD.
3. **DISTINCT obrigatorio** — toda query precisaria de deduplicacao, matando performance em particoes de 170M+ rows.
4. **Indice GIN duplicado** — cada sub-particao herdaria seu proprio GIN trigram index, multiplicando custo de armazenamento e manutencao.
5. **Concorrencia ja resolvida** — fontes diferentes tipicamente escrevem em TLDs diferentes (CZDS → gTLDs, OpenINTEL → ccTLDs). Quando escrevem no mesmo TLD, PostgreSQL usa row-level locking, nao table-level. Advisory locks no OpenINTEL worker ja previnem contencao real.

**Se source tracking for necessario**, o campo correto e na tabela `ingestion_run` (que ja existe), nao na tabela `domain`. Apos o filtro de similaridade retornar ~5000 candidatos, o enriquecimento pode consultar de qual fonte o dominio foi descoberto.

### A2: Particionar por data (RANGE por dia/mes)

**Proposta:** particoes por data de ingestao para watermark nativo via partition pruning.

**Rejeitada porque:**

1. **Multiplicacao de particoes** — 50 TLDs x 365 dias = 18.250 particoes/ano. PostgreSQL gerencia, mas o overhead de planejamento de queries (partition pruning check) cresce linearmente.
2. **Similarity queries perdem pruning por TLD** — a query `WHERE tld = 'com' AND label % 'google'` varreria todas as particoes de data, cada uma com seu proprio GIN index. Dramaticamente pior que o modelo atual.
3. **GIN index fragmentado** — em vez de um GIN compacto por TLD, teriamos centenas de GIN pequenos. GIN indexes sao mais eficientes quando maiores (melhor compactacao de posting lists).
4. **Watermark via btree e suficiente** — `WHERE added_day > 20260422` com btree index faz Index Scan eficiente. O custo de scan e O(log N) + delta rows, nao O(N).

### A3: Tabela separada para `.com`

**Proposta:** isolar `.com` (170M rows) em tabela propria para reduzir impacto em queries de outros TLDs.

**Rejeitada porque:**

1. **TLD partitioning ja isola** — queries em `.org` nunca tocam a particao `.com`. O PostgreSQL faz partition pruning automatico via `WHERE tld = :tld`.
2. **Toda query de similarity precisaria de UNION** — o codigo duplicaria toda logica para consultar `domain` + `domain_com`. O `search_candidates` (cross-TLD) ficaria especialmente complexo.
3. **GIN funciona** — mesmo com 170M rows, queries trigram no `.com` completam em < 10 min (com timeout configurado). O gargalo e escrita, nao leitura.
4. **Com delta do Databricks, a escrita no .com fica rapida** — ~2-3M inserts/dia com `ON CONFLICT DO NOTHING`, sem tocar GIN para os 167M existentes.

### A4: Eliminar a coluna `label`

**Proposta:** derivar label de `name` via expressao `LEFT(name, LENGTH(name) - LENGTH(tld) - 1)` para economizar espaco.

**Rejeitada porque:**

1. **GIN index nao funciona em expressoes complexas** — `CREATE INDEX USING gin ((LEFT(name, ...)) gin_trgm_ops)` e possivel mas: a expressao e avaliada para cada row no build do indice, tornando manutencao mais lenta; o planner pode nao reconhecer a expressao na query como match do indice.
2. **Toda query precisaria repetir a expressao** — `WHERE LEFT(name, LENGTH(name) - LENGTH(tld) - 1) % :brand` em vez de `WHERE label % :brand`. Mais fragil e propenso a erros.
3. **Custo real e baixo** — `label` e substring de `name`, compartilhando grande parte do armazenamento via TOAST. O overhead incremental nao justifica a complexidade.

### A5: Source como coluna SMALLINT na tabela domain

**Proposta:** adicionar `source SMALLINT NOT NULL DEFAULT 0` para saber a origem de cada dominio (0=czds, 1=openintel, 2=certstream).

**Rejeitada porque:**

1. **Um dominio pode ter multiplas fontes** — `example.com.br` pode aparecer no OpenINTEL (zona .com.br) e no CertStream (certificado). Qual source gravar? O primeiro? O ultimo? Array?
2. **Nao agrega valor para similarity** — nenhuma query de similaridade filtra ou ordena por source.
3. **Overhead desnecessario** — 2 bytes/row x 170M = 340MB so no .com, para um campo que nunca e consultado no hot path.
4. **Tracking de fonte ja existe** — `ingestion_run` registra qual fonte gerou cada batch, com timestamps e metricas. Consultar "de onde veio este dominio" e uma JOIN sob demanda, nao um custo permanente.

---

## Consequencias

### Positivas

- **~4.5 GB de economia** so na particao `.com` (dados + indices eliminados)
- **Writes 2-3x mais rapidos** — sem UPDATE de `last_seen_at`, sem manutencao do indice `ix_domain_last_seen`
- **Pipeline simplificado** — Databricks produz delta, backend faz `INSERT ... ON CONFLICT DO NOTHING`
- **`domain_stage` pode ser deprecada** quando pipeline Databricks estiver operacional
- **Deteccao de remocao** — `domain_removed` permite limpar similarity matches de dominios mortos
- **Watermark preservado** — `added_day` com btree e funcionalmente equivalente a `first_seen_at` para delta scans

### Negativas

- **Perda de granularidade temporal** — `added_day` tem resolucao de dia vs `first_seen_at` que tinha resolucao de microsegundo. Para watermark isso e irrelevante (scans rodam 1x/dia). Para auditoria detalhada, consultar `ingestion_run`.
- **Perda de `last_seen_at`** — nao se sabe "quando foi a ultima vez que vimos este dominio na zona". Mitigado por `domain_removed` (se desapareceu, quando desapareceu).
- **Migracao de dados** — conversao de `first_seen_at` para `added_day` em 300M+ rows requer janela de manutencao ou migracao progressiva por particao.
- **Ajuste no similarity_repository** — queries que referenciam `first_seen_at` e `last_seen_at` precisam ser atualizadas.

### Neutras

- **`label` permanece** — nenhuma mudanca necessaria nas queries de similarity
- **Particionamento LIST por TLD permanece** — sem impacto na infra de particoes existente
- **GIN trigram index permanece** — sem impacto na performance de leitura de similarity

---

## Plano de migracao (alto nivel)

1. **Criar nova migracao Alembic** com `added_day` e sem `last_seen_at` / indices antigos
2. **Migrar dados por particao** — `UPDATE domain SET added_day = TO_CHAR(first_seen_at, 'YYYYMMDD')::int WHERE tld = :tld` (uma particao por vez para evitar lock prolongado)
3. **Criar `domain_removed`** na mesma migracao
4. **Atualizar `similarity_repository.py`** — trocar `first_seen_at` por `added_day` em todas as queries
5. **Atualizar `SimilarityScanCursor`** — `watermark_at` TIMESTAMPTZ → `watermark_day` INTEGER
6. **Atualizar `domain_repository.py`** — `bulk_upsert` passa a usar `ON CONFLICT DO NOTHING` em vez de `DO UPDATE SET last_seen_at`
7. **Deprecar `domain_stage`** quando pipeline Databricks estiver em producao
8. **Drop das colunas/indices antigos** em migracao posterior (apos validacao em producao)

---

## Referencias

- [czds-ingestion-optimization-study.md](../czds-ingestion-optimization-study.md) — estudo original do gargalo de 74h no .com
- [domain-table-redesign-proposal.md](../domain-table-redesign-proposal.md) — proposta anterior de redesign
- [domain-infrastructure-master-plan.md](../domain-infrastructure-master-plan.md) — plano geral de infraestrutura de dominios
- [similarity-analysis-architecture.md](../similarity-analysis-architecture.md) — arquitetura do sistema de similaridade
- Spec Databricks: [spec_databricks_orchestration_and_partitioned_domains.md](../../.specs/features/domain-database/spec_databricks_orchestration_and_partitioned_domains.md)
