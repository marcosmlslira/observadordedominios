# Proposta: Redesign da Tabela `domain`

> Data: 2026-03-21 | Status: Proposta aprovada, pendente implementação
> Pré-requisito: Ler `docs/czds-ingestion-optimization-study.md` para o diagnóstico completo

---

## 1. Contexto e Motivação

A tabela `domain` foi projetada com 9 colunas, UUID como PK, 5 índices, status string e soft-delete explícito. Com apenas 3 TLDs (net, org, info) e 31M rows, já ocupa **7.3 GB** (dados + índices). A projeção para `.com` (160M domínios) levaria a **~44 GB** — insustentável para a infra atual.

Além disso, a ingestão atual executa 5 passos por batch (staging → upsert → update status → soft-delete → commit), gerando overhead significativo de I/O e tempo.

### Problema arquitetural

A tabela `domain` tenta ser duas coisas ao mesmo tempo:

1. **Registro de presença no zone file** — "este nome apareceu no zone do CZDS hoje"
2. **Entidade canônica do produto** — "o que sabemos sobre este domínio"

Isso gera complexidade desnecessária: staging table, upsert com status, soft-delete massivo por TLD, e ambiguidade quando múltiplas fontes (CZDS, NSEC, CT Logs) escrevem na mesma tabela.

### Insight chave

O zone file CZDS **é a verdade completa** para aquele TLD. Se `example.net` está no zone file, ele está ativo. Se não está, não está. **A presença no zone file É o status** — não precisa de flag.

A mesma lógica vale para NSEC zone walking: o resultado do walk é a lista completa.

---

## 2. Schema Atual vs. Proposto

### Schema ATUAL (9 colunas, ~113 bytes/row)

```sql
CREATE TABLE domain (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(253) UNIQUE NOT NULL,
    tld           VARCHAR(24) NOT NULL,
    status        VARCHAR(16) NOT NULL DEFAULT 'active',  -- 'active' | 'deleted'
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at  TIMESTAMPTZ NOT NULL,
    deleted_at    TIMESTAMPTZ,
    created_at    TIMESTAMPTZ NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL
);

-- 5 índices (4 após fix R1):
-- domain_pkey        (id)            ~1.2 GB
-- domain_name_key    (name) UNIQUE   ~1.9 GB
-- ix_domain_status_tld (status, tld) ~372 MB
-- ix_domain_tld_last_seen (tld, last_seen_at DESC) ~314 MB
```

### Schema PROPOSTO (4 colunas, ~42 bytes/row)

```sql
CREATE TABLE domain (
    name          VARCHAR(253) NOT NULL,
    tld           VARCHAR(24)  NOT NULL,
    first_seen_at TIMESTAMPTZ  NOT NULL,
    last_seen_at  TIMESTAMPTZ  NOT NULL,
    PRIMARY KEY (name)
) PARTITION BY LIST (tld);

-- Uma partição por TLD ingerido
CREATE TABLE domain_net  PARTITION OF domain FOR VALUES IN ('net');
CREATE TABLE domain_org  PARTITION OF domain FOR VALUES IN ('org');
CREATE TABLE domain_info PARTITION OF domain FOR VALUES IN ('info');
-- Novas partições criadas conforme TLDs são habilitados
```

**Índice adicional por partição (1 apenas):**

```sql
-- Criado automaticamente em cada partição pelo partitioning:
-- PK em (name) — herda da tabela pai

-- Índice adicional para queries temporais:
CREATE INDEX ix_domain_tld_last_seen ON domain (tld, last_seen_at DESC);
```

### Colunas removidas e justificativa

| Coluna removida | Justificativa |
|---|---|
| `id` (UUID) | `name` é a PK natural. Nenhuma FK referencia `domain.id` em produção. A tabela `domain_observation` tem 0 rows e não será populada com o design atual (ver seção 7). |
| `status` | Derivável: domínio está "ativo" se `last_seen_at >= data do último sync`. Eliminando status, eliminamos também o UPDATE massivo de soft-delete por run. |
| `deleted_at` | Redundante com `status` removido. A data em que o domínio "saiu" é implicitamente `last_seen_at` (última vez que foi visto ativo). |
| `created_at` | Verificado por amostragem: 100% dos rows têm `created_at == first_seen_at`. São semanticamente idênticos nesta tabela. |
| `updated_at` | Verificado por amostragem: 100% dos rows têm `updated_at == last_seen_at`. São semanticamente idênticos nesta tabela. |

---

## 3. Impacto no Pipeline de Ingestão

### Pipeline ATUAL (5 passos por batch de 50k)

```
1. INSERT batch na staging table (stg_zone_domain_{run_id})
2. INSERT ... ON CONFLICT na tabela domain (upsert com status='active', deleted_at=NULL)
3. UPDATE ingestion_run SET domains_seen = ...
4. COMMIT
5. [Após todos batches] UPDATE domain SET status='deleted' WHERE tld=:tld AND NOT IN staging
```

Arquivos envolvidos:
- `backend/app/services/use_cases/apply_zone_delta.py`
- `backend/app/repositories/domain_repository.py` (4 métodos: `create_staging_table`, `bulk_insert_staging`, `bulk_upsert_domain`, `apply_delta`)

### Pipeline PROPOSTO (1 passo por batch)

```
1. INSERT ... ON CONFLICT (name) DO UPDATE SET last_seen_at = :ts
2. UPDATE ingestion_run SET domains_seen = ...
3. COMMIT
```

**Eliminados:**
- Criação de staging table temporária
- Insert na staging table
- Passo de soft-delete (`UPDATE domain SET status='deleted' WHERE ...`)

### SQL do upsert simplificado

```sql
INSERT INTO domain (name, tld, first_seen_at, last_seen_at)
SELECT unnest(:names), :tld, :ts, :ts
ON CONFLICT (name) DO UPDATE
SET last_seen_at = EXCLUDED.last_seen_at
```

Apenas 1 statement. Sem staging. Sem soft-delete.

---

## 4. Como Derivar "Ativo" e "Deletado"

A informação de status passa a ser derivada de `last_seen_at` comparado com a data do último sync bem-sucedido, que já existe em `ingestion_checkpoint.last_successful_run_at`.

### Queries de referência

```sql
-- Domínios ativos de um TLD (vistos no último sync)
SELECT d.name
FROM domain d
JOIN ingestion_checkpoint c
  ON c.tld = d.tld AND c.source = 'czds'
WHERE d.tld = 'net'
  AND d.last_seen_at >= c.last_successful_run_at;

-- Versão simplificada (passando a data direto)
SELECT name FROM domain
WHERE tld = 'net'
  AND last_seen_at >= '2026-03-19T18:47:07+00:00';

-- Domínios que saíram do zone file (não vistos no último sync)
SELECT name FROM domain
WHERE tld = 'net'
  AND last_seen_at < '2026-03-19T18:47:07+00:00';

-- Domínios recém-registrados (apareceram nos últimos 7 dias)
SELECT name FROM domain
WHERE tld = 'net'
  AND first_seen_at >= now() - interval '7 days';

-- Domínios que desapareceram recentemente (estavam ativos, agora não)
SELECT name FROM domain
WHERE tld = 'net'
  AND last_seen_at >= now() - interval '48 hours'
  AND last_seen_at < (
    SELECT last_successful_run_at
    FROM ingestion_checkpoint
    WHERE source = 'czds' AND tld = 'net'
  );
```

### Impacto no Similarity Service

O endpoint `POST /v1/similarity/search` tem o campo `include_deleted: false`. Com o novo schema:

```sql
-- ANTES (com status):
WHERE status = 'active' AND tld IN ('com', 'net', 'org')

-- DEPOIS (sem status):
WHERE last_seen_at >= :cutoff_date AND tld IN ('com', 'net', 'org')
```

A `cutoff_date` pode ser calculada uma vez no service layer (MIN dos checkpoints dos TLDs solicitados) e passada à query. Performance equivalente com índice em `(tld, last_seen_at DESC)`.

---

## 5. Partitioning por TLD

### Por que particionar?

| Benefício | Descrição |
|---|---|
| **Isolamento de I/O** | VACUUM, REINDEX e maintenance operam por partição, não na tabela inteira |
| **Queries otimizadas** | `WHERE tld = 'net'` faz partition pruning — só acessa a partição relevante |
| **Escalabilidade** | Adicionar `.com` (160M rows) é criar uma partição, sem impactar as existentes |
| **Drop facilitado** | Remover um TLD = DROP da partição (instantâneo vs DELETE de milhões de rows) |
| **Índices menores** | Cada partição tem seus próprios índices — mais eficientes que um B-tree gigante |

### Como gerenciar partições

Partições devem ser criadas quando um TLD é habilitado em `czds_tld_policy`. Sugestão de lógica no `sync_czds_tld`:

```python
def _ensure_partition(db: Session, tld: str) -> None:
    """Cria partição para o TLD se não existir."""
    partition_name = f"domain_{tld.replace('-', '_')}"
    exists = db.execute(text(
        "SELECT 1 FROM pg_class WHERE relname = :name"
    ), {"name": partition_name}).scalar()

    if not exists:
        db.execute(text(
            f"CREATE TABLE {partition_name} PARTITION OF domain "
            f"FOR VALUES IN (:tld)"
        ), {"tld": tld})
        db.commit()
        logger.info("Created partition %s for TLD=%s", partition_name, tld)
```

Chamar no início de `sync_czds_tld`, antes do upsert.

### Constraint de PK com partitioning

O PostgreSQL exige que a partition key faça parte da PK em tabelas particionadas. Como particionamos por `tld` e a PK é `name`:

**Opção A** — PK composta `(name, tld)`:
```sql
PRIMARY KEY (name, tld)
```
Funciona, mas `name` já é globalmente único (não existem dois domínios com mesmo nome e TLDs diferentes).

**Opção B** — PK em `name` + partition key como coluna regular:
Não é possível no PostgreSQL nativo. A partition key DEVE estar na PK.

**Recomendação:** Usar `PRIMARY KEY (name, tld)`. O `tld` é redundante na PK (pois `name` já contém o TLD como sufixo), mas é obrigatório pelo PostgreSQL para partitioning. O overhead é mínimo (~4 bytes a mais no índice PK).

---

## 6. Compatibilidade com Multi-Fonte (CZDS + NSEC + Futuras)

### Cenário atual e planejado

| Fonte | Tipo | TLDs | Overlap |
|---|---|---|---|
| **CZDS** | Zone file completo (snapshot) | gTLDs: com, net, org, info... | — |
| **NSEC** | Zone walk completo (snapshot) | ccTLDs: br, ... | Mínimo com CZDS |
| **CT Logs** (futuro) | Eventos individuais | Todos | Alto — domínios já em CZDS/NSEC |
| **pDNS** (futuro) | Eventos individuais | Todos | Alto — domínios já em CZDS/NSEC |

### Como cada fonte escreve no `domain`

**Fontes de snapshot (CZDS, NSEC):** upsert massivo, batch de 50k.
```sql
INSERT INTO domain (name, tld, first_seen_at, last_seen_at)
SELECT unnest(:names), :tld, :ts, :ts
ON CONFLICT (name) DO UPDATE
SET last_seen_at = GREATEST(domain.last_seen_at, EXCLUDED.last_seen_at)
```

Usar `GREATEST` garante que se duas fontes escrevem para o mesmo domínio, `last_seen_at` mantém a data mais recente. `first_seen_at` não é atualizado no conflito (preserva a data original).

**Fontes de evento (CT Logs, pDNS):** insert individual ou micro-batch.
```sql
INSERT INTO domain (name, tld, first_seen_at, last_seen_at)
VALUES (:name, :tld, :ts, :ts)
ON CONFLICT (name) DO UPDATE
SET last_seen_at = GREATEST(domain.last_seen_at, EXCLUDED.last_seen_at)
```

Mesma lógica. A diferença é o volume por operação.

### Quando "ativo" depende da fonte

Se `.net` some do CZDS mas aparece via CT Log, qual é o status?

Com o schema proposto, `last_seen_at` reflete a **mais recente de qualquer fonte**. Isso significa:
- Se CT Log viu `example.net` hoje mas CZDS não vê mais → `last_seen_at` = hoje → "ativo"
- Isso é **correto do ponto de vista do produto**: o domínio existe, apenas saiu do zone file (pode significar mudança de NS, não necessariamente remoção)

Se for necessário distinguir "ativo no zone file" vs "ativo em CT Log", a solução é a tabela `domain_source` (ver seção 8).

---

## 7. Decisão sobre `domain_observation`

### Status atual

A tabela `domain_observation` existe no schema mas tem **0 rows**. Nunca foi populada.

### Análise de custo se fosse populada

| Cenário | Rows/dia | Tamanho/dia | Tamanho/mês |
|---|---|---|---|
| 3 TLDs (net, org, info) | 31M | ~3.7 GB | ~111 GB |
| + .com | 191M | ~22.8 GB | ~684 GB |

**Insustentável** com o design atual (1 observation por domínio por run).

### Recomendação

**Não popular `domain_observation` para fontes de snapshot (CZDS, NSEC).** O audit trail para essas fontes é:
- `domain.first_seen_at` / `last_seen_at` — timeline
- `ingestion_run` — métricas por execução
- Zone file artifact no S3 — raw data completo

Se futuramente for necessário tracking de **mudanças** (domínios que entraram ou saíram entre dois zone files), usar uma tabela de **deltas** (apenas mudanças, não observações completas):

```sql
CREATE TABLE domain_change (
    domain_name VARCHAR(253) NOT NULL,
    tld         VARCHAR(24) NOT NULL,
    source      VARCHAR(32) NOT NULL,
    change_type VARCHAR(8) NOT NULL,   -- 'added' | 'removed'
    observed_at TIMESTAMPTZ NOT NULL,
    run_id      UUID,
    PRIMARY KEY (domain_name, source, observed_at)
) PARTITION BY LIST (source);
```

Isso captura apenas os **deltas** (~0.1-1% dos domínios por run), não o snapshot completo.

Para fontes de evento (CT Logs, pDNS), o modelo append-only faz sentido e o volume é manejável.

---

## 8. Tabela `domain_source` (futura, YAGNI por ora)

Se/quando for necessário saber **qual fonte** viu cada domínio e **quando**:

```sql
CREATE TABLE domain_source (
    domain_name VARCHAR(253) NOT NULL REFERENCES domain(name) ON DELETE CASCADE,
    source      VARCHAR(32) NOT NULL,
    first_seen_at TIMESTAMPTZ NOT NULL,
    last_seen_at  TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (domain_name, source)
);
```

**Não implementar agora.** Implementar apenas quando a segunda fonte de ingestão (NSEC ou CT Logs) entrar em produção e houver necessidade real de filtrar por fonte.

Razão: YAGNI. CZDS é a única fonte hoje. Adicionar esta tabela agora duplicaria o storage sem benefício.

---

## 9. Comparação de Impacto

### Storage

| Métrica | Schema Atual | Schema Proposto | Economia |
|---|---|---|---|
| Bytes/row | ~113 | ~42 | -63% |
| Colunas | 9 | 4 | -5 colunas |
| Índices por partição | 4 | 2 (PK + tld_last_seen) | -2 índices |
| **31M rows (3 TLDs)** | **7.3 GB** | **~2.4 GB** | **-4.9 GB (-67%)** |
| **191M rows (+ .com)** | **~44 GB** | **~14 GB** | **-30 GB (-68%)** |
| **206M rows (10 TLDs)** | **~157 GB** | **~51 GB** | **-106 GB (-68%)** |

### Performance de ingestão

| Operação | Schema Atual | Schema Proposto |
|---|---|---|
| Passos por batch | 5 (staging + upsert + status + soft-delete + commit) | 2 (upsert + commit) |
| Staging table | Sim (criação + insert + join para delete) | Não necessária |
| Soft-delete pass | UPDATE em milhões de rows por run | Nenhum |
| Índices a manter por INSERT | 4-5 | 2 |

### Queries afetadas

| Query | Antes | Depois |
|---|---|---|
| Domínios ativos | `WHERE status = 'active'` | `WHERE last_seen_at >= :checkpoint` |
| Domínios removidos | `WHERE status = 'deleted'` | `WHERE last_seen_at < :checkpoint` |
| Similarity search | `WHERE status = 'active' AND tld IN (...)` | `WHERE last_seen_at >= :cutoff AND tld IN (...)` |
| Recém-registrados | `WHERE first_seen_at >= :date` | `WHERE first_seen_at >= :date` (sem mudança) |

---

## 10. Migration Strategy

### Pré-requisitos

- R1 já aplicado (drop `ix_domain_name`) ✅
- R2 já aplicado (cleanup orphan artifacts) ✅
- R4 já aplicado (cleanup cache local) ✅
- Backup do banco antes de iniciar

### Passos da migration

#### Migration 005: Criar nova estrutura particionada

```sql
-- 1. Criar tabela particionada
CREATE TABLE domain_new (
    name          VARCHAR(253) NOT NULL,
    tld           VARCHAR(24)  NOT NULL,
    first_seen_at TIMESTAMPTZ  NOT NULL,
    last_seen_at  TIMESTAMPTZ  NOT NULL,
    PRIMARY KEY (name, tld)
) PARTITION BY LIST (tld);

-- 2. Criar partições para TLDs existentes
CREATE TABLE domain_new_net  PARTITION OF domain_new FOR VALUES IN ('net');
CREATE TABLE domain_new_org  PARTITION OF domain_new FOR VALUES IN ('org');
CREATE TABLE domain_new_info PARTITION OF domain_new FOR VALUES IN ('info');

-- 3. Criar índice temporal em cada partição (automático via tabela pai)
CREATE INDEX ix_domain_new_tld_last_seen ON domain_new (tld, last_seen_at DESC);

-- 4. Migrar dados (em batches para não bloquear)
INSERT INTO domain_new (name, tld, first_seen_at, last_seen_at)
SELECT name, tld, first_seen_at, last_seen_at
FROM domain;

-- 5. Renomear tabelas (requer lock exclusivo breve)
ALTER TABLE domain RENAME TO domain_old;
ALTER TABLE domain_new RENAME TO domain;

-- 6. Renomear partições para consistência
ALTER TABLE domain_new_net  RENAME TO domain_net;
ALTER TABLE domain_new_org  RENAME TO domain_org;
ALTER TABLE domain_new_info RENAME TO domain_info;

-- 7. Dropar tabela antiga (após validação)
-- DROP TABLE domain_old;  -- executar manualmente após confirmar que tudo funciona
```

#### Nota sobre o passo 4 (migração de dados)

Com 31M rows, o `INSERT ... SELECT` pode levar alguns minutos. Para ambientes de produção com zero-downtime, considerar migração em batches:

```sql
-- Em batches de 1M por TLD:
INSERT INTO domain_new (name, tld, first_seen_at, last_seen_at)
SELECT name, tld, first_seen_at, last_seen_at
FROM domain
WHERE tld = 'net'
LIMIT 1000000 OFFSET 0;
-- ... repetir com OFFSET incremental
```

### Alterações no código Python

#### `backend/app/models/domain.py`

```python
"""Domain entity — canonical global domain record."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.orm import relationship

from app.models.base import Base


class Domain(Base):
    __tablename__ = "domain"

    name = Column(String(253), primary_key=True)
    tld = Column(String(24), nullable=False, primary_key=True)  # part of PK for partitioning
    first_seen_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    last_seen_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_domain_tld_last_seen", "tld", last_seen_at.desc()),
    )
```

#### `backend/app/repositories/domain_repository.py`

```python
"""Repository for domain bulk operations — simplified upsert without staging."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class DomainRepository:
    """Bulk upsert de domínios. Sem staging table, sem soft-delete."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def bulk_upsert(self, domain_names: list[str], tld: str, now: datetime) -> int:
        """Upsert batch na tabela domain. Retorna count de nomes processados."""
        if not domain_names:
            return 0

        unique_names = list(set(domain_names))

        self.db.execute(text("""
            INSERT INTO domain (name, tld, first_seen_at, last_seen_at)
            SELECT unnest(:names), :tld, :ts, :ts
            ON CONFLICT (name, tld) DO UPDATE
            SET last_seen_at = GREATEST(domain.last_seen_at, EXCLUDED.last_seen_at)
        """), {"names": unique_names, "tld": tld, "ts": now})

        return len(unique_names)
```

**Métodos removidos:** `create_staging_table`, `bulk_insert_staging`, `apply_delta`.

#### `backend/app/services/use_cases/apply_zone_delta.py`

```python
"""Use case: apply zone delta — parse zone file and upsert to DB."""

from __future__ import annotations

import gzip
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.repositories.domain_repository import DomainRepository

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50_000


def _parse_zone_stream(path: Path, tld: str):
    """Generator: yield normalised second-level domain names from gzipped zone file."""
    seen_in_batch: set[str] = set()

    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="ascii", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            parts = line.split()
            if len(parts) < 4:
                continue

            owner = parts[0].lower().rstrip(".")
            if not owner.endswith(f".{tld}") and owner != tld:
                continue
            if owner == tld:
                continue

            if owner not in seen_in_batch:
                seen_in_batch.add(owner)
                yield owner

                if len(seen_in_batch) >= 500_000:
                    seen_in_batch.clear()


def apply_zone_delta(
    db: Session,
    *,
    zone_file_path: Path,
    tld: str,
    run_id: uuid.UUID,
) -> dict[str, int]:
    """Parse zone file em streaming e upsert direto no domain."""
    ts = datetime.now(timezone.utc)
    repo = DomainRepository(db)

    batch: list[str] = []
    total_parsed = 0

    for domain_name in _parse_zone_stream(zone_file_path, tld):
        batch.append(domain_name)

        if len(batch) >= _BATCH_SIZE:
            repo.bulk_upsert(batch, tld, ts)
            total_parsed += len(batch)
            logger.info("Upserted %d domains so far...", total_parsed)
            db.execute(
                text("UPDATE ingestion_run SET domains_seen = :total WHERE id = :id"),
                {"total": total_parsed, "id": run_id},
            )
            db.commit()
            batch.clear()

    if batch:
        repo.bulk_upsert(batch, tld, ts)
        total_parsed += len(batch)

    db.execute(
        text("UPDATE ingestion_run SET domains_seen = :total WHERE id = :id"),
        {"total": total_parsed, "id": run_id},
    )
    db.commit()

    logger.info("Total domains upserted: %d", total_parsed)

    # Métricas simplificadas: sem soft-delete, inserted = seen (sem distinção precisa)
    return {
        "seen": total_parsed,
        "inserted": total_parsed,
        "reactivated": 0,
        "deleted": 0,
    }
```

**Removido:** criação de staging table, insert em staging, passo de apply_delta com soft-delete.

#### Tabela `domain_observation` — dropar

A tabela tem 0 rows e não será populada. Remover na migration:

```sql
DROP TABLE IF EXISTS domain_observation;
```

Remover o arquivo `backend/app/models/domain_observation.py` e a relationship no model Domain.

---

## 11. Criação Dinâmica de Partições

Quando um novo TLD for habilitado em `czds_tld_policy` ou `nsec_tld_policy`, a partição deve ser criada antes da primeira ingestão.

### Implementação em `sync_czds_tld.py`

```python
def _ensure_partition(db: Session, tld: str) -> None:
    """Cria partição para o TLD se não existir."""
    safe_tld = tld.replace("-", "_")
    partition_name = f"domain_{safe_tld}"

    exists = db.execute(
        text("SELECT 1 FROM pg_class WHERE relname = :name"),
        {"name": partition_name},
    ).scalar()

    if not exists:
        # Usar DDL direto (não parametrizável em prepared statements)
        db.execute(text(
            f"CREATE TABLE {partition_name} PARTITION OF domain "
            f"FOR VALUES IN ('{tld}')"
        ))
        db.commit()
        logger.info("Created partition %s for TLD=%s", partition_name, tld)
```

Chamar `_ensure_partition(db, tld)` no início de `sync_czds_tld`, antes de qualquer upsert.

---

## 12. Rollback Plan

Se algo der errado após a migration:

1. A tabela `domain_old` permanece intacta até DROP manual
2. Renomear de volta: `ALTER TABLE domain RENAME TO domain_new; ALTER TABLE domain_old RENAME TO domain;`
3. Reverter alterações no código (git revert)

**Recomendação:** Manter `domain_old` por 7 dias após a migration. Dropar somente após validação completa do pipeline.

---

## 13. Checklist de Implementação

```
Preparação:
  [ ] Backup do banco (pg_dump ou snapshot)
  [ ] Parar o worker czds_ingestor

Migration:
  [ ] Criar migration 005 com schema particionado
  [ ] Migrar dados de domain → domain_new (pode levar ~5-10 min)
  [ ] Renomear tabelas
  [ ] Dropar domain_observation (0 rows)
  [ ] Aplicar migration via Alembic

Código:
  [ ] Atualizar backend/app/models/domain.py (novo schema)
  [ ] Remover backend/app/models/domain_observation.py
  [ ] Simplificar backend/app/repositories/domain_repository.py (remover staging + soft-delete)
  [ ] Simplificar backend/app/services/use_cases/apply_zone_delta.py (sem staging, sem apply_delta)
  [ ] Adicionar _ensure_partition em sync_czds_tld.py
  [ ] Atualizar backend/app/schemas/czds_ingestion.py se necessário
  [ ] Atualizar imports em __init__.py e main.py

Validação:
  [ ] Rodar ingestão manual para 1 TLD (info, menor)
  [ ] Verificar contadores em ingestion_run
  [ ] Verificar que domain tem os dados corretos
  [ ] Verificar partition pruning com EXPLAIN ANALYZE
  [ ] Rodar 2ª ingestão para validar idempotência
  [ ] Comparar tamanho final vs projeção

Cleanup:
  [ ] DROP TABLE domain_old (após 7 dias)
  [ ] Reiniciar worker czds_ingestor
  [ ] Atualizar docs/czds-ingestion-optimization-study.md com resultados
```
