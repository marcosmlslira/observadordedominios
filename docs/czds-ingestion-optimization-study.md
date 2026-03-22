# Estudo de Otimização — Ingestão CZDS

> Data: 2026-03-19 | Status: Análise concluída, aguardando decisões

---

## 1. Diagnóstico Atual

### 1.1. Tamanho da Tabela `domain`

| Métrica | Valor |
|---|---|
| **Linhas totais** | 31.275.338 |
| **Tamanho da tabela (dados)** | 3.515 MB |
| **Tamanho dos índices** | 5.713 MB |
| **Total (tabela + índices)** | **9.227 MB (~9 GB)** |
| **Banco inteiro** | 11 GB |
| **TLDs ingeridos** | 3 (net, org, info) |

### 1.2. Distribuição por TLD

| TLD | Domínios | % |
|---|---|---|
| net | 12.986.938 | 41.5% |
| org | 12.695.196 | 40.6% |
| info | 5.593.204 | 17.9% |

### 1.3. Anatomia do Espaço (por linha)

| Componente | Bytes | % da linha |
|---|---|---|
| `name` (varchar) | 18 | 15.9% |
| **`id` (UUID)** | **16** | **14.2%** |
| `first_seen_at` | 8 | 7.1% |
| `last_seen_at` | 8 | 7.1% |
| `created_at` | 8 | 7.1% |
| `updated_at` | 8 | 7.1% |
| `status` | 7 | 6.2% |
| `tld` | 4 | 3.5% |
| Tuple header + alignment | 36 | 31.9% |
| **Total por linha** | **~113 bytes** | |

### 1.4. Breakdown dos Índices

| Índice | Tamanho | Observação |
|---|---|---|
| `domain_name_key` (UNIQUE) | 1.933 MB | Constraint unique |
| **`ix_domain_name`** | **1.880 MB** | **DUPLICADO** — redundante com `domain_name_key` |
| `domain_pkey` (UUID) | 1.212 MB | PK em UUID |
| `ix_domain_status_tld` | 372 MB | OK — usado para queries |
| `ix_domain_tld_last_seen` | 314 MB | OK — usado para queries |

### 1.5. Armazenamento MinIO (S3)

| Objeto | Tamanho |
|---|---|
| **6x** `net.zone.gz` (runs falhas + sucesso) | 6 × 355 MB = **2.131 MB** |
| **2x** `org.zone.gz` | 2 × 429 MB = **859 MB** |
| **1x** `info.zone.gz` | 182 MB |
| **Total MinIO** | **3.172 MB (~3.1 GB)** |

### 1.6. Cache Local (`/data/czds/`)

| Arquivo | Tamanho |
|---|---|
| `net.zone.gz` | 356 MB |
| `org.zone.gz` | 430 MB |
| **Total** | **785 MB** |

---

## 2. Problemas Identificados

### P1. Índice duplicado no `name` — 1.9 GB desperdiçado

O model SQLAlchemy declara `index=True` junto com `unique=True`:

```python
name = Column(String(253), unique=True, nullable=False, index=True)
```

Isso cria **dois** índices B-tree idênticos sobre a mesma coluna:
- `domain_name_key` — criado pelo `UNIQUE` constraint
- `ix_domain_name` — criado pelo `index=True`

**Impacto:** 1.880 MB de espaço completamente desperdiçado + overhead em cada INSERT/UPDATE (dois índices para manter).

**Fix:** Remover `index=True` do model e dropar `ix_domain_name` via migration.

### P2. UUID como PK — overhead desnecessário

O `id` UUID consome 16 bytes/linha + 1.212 MB de índice PK. **Porém**, a tabela `domain` é identificada naturalmente pelo `name` (que já é UNIQUE). O UUID existe apenas por convenção — nenhuma FK referencia `domain.id` em produção hoje (a `domain_observation` existe mas tem **0 rows**).

**Opções:**
- **Curto prazo:** Manter UUID, mas considerar `BIGSERIAL` se decidir reprojetar.
- **Longo prazo:** Se `domain_observation` não for usada, remover a tabela e o `id` UUID, usando `name` como PK natural. Economia: ~1.5 GB (table + PK index).

### P3. Artifacts de runs falhas não são limpos no S3

Runs que falharam (net teve 6 tentativas) ainda sobem o zip para o S3 **antes** da fase de parsing. Se o parsing falha, o artifact fica órfão:
- 5 artifacts orphans de `net` = **1.775 MB desperdiçados**

### P4. Sem política de retenção de artifacts no S3

Cada run diária cria um novo objeto no S3. Com 3 TLDs:
- Diário: ~967 MB/dia
- Mensal: ~29 GB/mês
- Anual: ~350 GB/ano

Se expandir para mais TLDs (ex: `com` = ~1.5 GB/zip), escala rapidamente.

### P5. Cache local sem limpeza

Arquivos `.zone.gz` ficam em `/data/czds/` permanentemente. Hoje são 785 MB, mas crescem com cada TLD adicionado e nunca são removidos.

### P6. Colunas `created_at` e `updated_at` redundantes

Para a tabela `domain` especificamente:
- `created_at` ≡ `first_seen_at` (sempre iguais no INSERT)
- `updated_at` ≡ `last_seen_at` (sempre iguais no UPDATE)

São 16 bytes/linha × 31M rows = **~473 MB** armazenando informação duplicada.

### P7. Tabela `domain_observation` — 0 rows, nunca usada

Projetada para audit trail mas nunca populada. Se fosse populada com 1 observation/domain/run, seriam **31M rows por run diário** — insustentável.

### P8. Coluna `status` como String vs Boolean

`status` ocupa 7 bytes/linha para armazenar apenas dois valores: `'active'` ou `'deleted'`. Um boolean `is_active` ocuparia 1 byte.

Economia: 6 bytes × 31M = ~178 MB (table) + redução de índice.

---

## 3. Projeção de Crescimento

### Cenário: Adicionar `.com`

| Métrica | Valor Estimado |
|---|---|
| Domínios `.com` | ~160.000.000 |
| Tamanho tabela (dados) | +16.8 GB |
| Tamanho com índices | +43.8 GB |
| Zone file (.gz) | ~1.5 GB |
| S3 diário | +1.5 GB/dia |

### Cenário: 10 TLDs populares

| TLD | Domínios (aprox.) |
|---|---|
| com | 160M |
| net | 13M |
| org | 13M |
| info | 5.5M |
| xyz | 5M |
| online | 2M |
| site | 1.5M |
| top | 4M |
| club | 1M |
| biz | 1M |
| **Total** | **~206M** |

**Estimativa com schema atual:** ~60 GB (dados) + ~97 GB (índices) = **~157 GB total no PostgreSQL**.

**Estimativa com otimizações propostas:** ~86 GB total (-45%).

---

## 4. Recomendações (Ordenadas por Impacto/Esforço)

### R1. ⚡ DROP do índice duplicado `ix_domain_name` [IMEDIATO]

- **Ganho:** 1.880 MB
- **Esforço:** 1 migration, 0 risco
- **Impacto em escrita:** Cada batch upsert de 50k vai ficar mais rápido (1 índice a menos para atualizar)

```sql
DROP INDEX CONCURRENTLY ix_domain_name;
```

### R2. ⚡ Cleanup de artifacts órfãos no S3 [IMEDIATO]

- **Ganho:** ~1.7 GB no MinIO
- **Esforço:** Script one-off + lógica no `sync_czds_tld`
- **Lógica:** Se run falha antes do parsing, deletar o artifact do S3 e o registro `zone_file_artifact`

### R3. 🔧 Política de retenção de artifacts [CURTO PRAZO]

Opções:

| Política | S3/Dia | S3/Mês |
|---|---|---|
| Manter todos (atual) | 967 MB | 29 GB |
| Manter último sucesso/TLD | 967 MB (pico) | ~967 MB |
| Manter últimos 7 dias | 967 MB | 6.8 GB |
| Manter último + 1 mensal | 967 MB | ~2 GB |

**Recomendação:** Manter **último artifact com sucesso por TLD** + **1 snapshot mensal** (1st do mês). Deletar o resto automaticamente após cada sync bem-sucedida.

Lógica sugerida no `sync_czds_tld`, após sucesso:
1. Listar artifacts anteriores do mesmo TLD
2. Manter o mais recente com status `success` (o atual)
3. Manter 1 por mês (o primeiro do mês)
4. Deletar S3 objects + registros DB dos demais

### R4. 🔧 Limpeza do cache local `/data/czds/` [CURTO PRAZO]

O cache local serve para evitar re-download em caso de retry dentro de 24h. Após uma ingestão bem-sucedida, o arquivo pode ser deletado.

Lógica: No `sync_czds_tld`, no bloco de sucesso, deletar `/data/czds/{tld}.zone.gz`.

**Ganho:** Manter `/data/czds/` abaixo de ~500 MB (somente TLDs com sync em andamento).

### R5. 🔧 Remover colunas `created_at` / `updated_at` do `domain` [MÉDIO PRAZO]

- **Ganho:** ~473 MB (table) + redução proporcional no tuple overhead
- **Esforço:** Migration + ajustar queries que referenciam essas colunas
- **Nota:** `first_seen_at` e `last_seen_at` já carregam toda a informação temporal necessária para esta tabela

### R6. 🔧 `status` String → Boolean `is_active` [MÉDIO PRAZO]

- **Ganho:** ~178 MB (table) + índice menor
- **Esforço:** Migration + ajustar queries
- **Alternativa:** Se futuramente precisar de mais status (ex: `suspended`), manter como String mas usar `CHAR(1)` com enum (`A`/`D`/`S`)

### R7. 🏗️ Não popular `domain_observation` [DECISÃO ARQUITETURAL]

Se a tabela for populada com o design atual (1 row por domínio por run), com `.com`:
- 160M rows/dia
- ~18 GB/dia
- **540 GB/mês**

**Recomendação:** Não popular esta tabela. O `domain.last_seen_at` + `domain.first_seen_at` já rastreiam a timeline. Se for necessário tracking histórico de presença/ausência em zone files, usar uma abordagem de bitmask ou tabela de **mudanças** (apenas domínios que entraram ou saíram), não uma tabela append-only de toda observação.

### R8. 🏗️ Considerar `BIGSERIAL` em vez de UUID para `domain.id` [LONGO PRAZO]

- **Ganho:** ~237 MB (table) + ~606 MB (PK index) = ~843 MB
- **Esforço:** Requer migration pesada (recriar PK, alterar FKs)
- **Trade-off:** UUID é melhor para sistemas distribuídos, BIGSERIAL é melhor para single-node com alto volume

### R9. 🏗️ Considerar table partitioning por TLD [LONGO PRAZO]

Se expandir para 10+ TLDs com 200M+ domínios:
- Particionar `domain` por `tld` (LIST partitioning)
- Cada partição tem seus próprios índices
- Permite VACUUM, reindex e drop por partição
- Soft-delete delta fica mais eficiente (opera numa partição só)

---

## 5. Resumo de Ganhos Estimados

### Ações imediatas (0 risco, ganho direto)

| Ação | Ganho Estimado |
|---|---|
| R1. Drop `ix_domain_name` | -1.880 MB no PostgreSQL |
| R2. Cleanup artifacts órfãos | -1.775 MB no MinIO |
| **Subtotal** | **-3.655 MB (~3.6 GB)** |

### Ações de curto prazo

| Ação | Ganho Estimado |
|---|---|
| R3. Retenção de artifacts | -2 GB/mês no MinIO |
| R4. Limpeza cache local | -785 MB volume Docker |

### Ações de médio prazo

| Ação | Ganho Estimado |
|---|---|
| R5. Remover created_at/updated_at | -473 MB |
| R6. Status → boolean | -178 MB |

### Ações de longo prazo (para escalar 10+ TLDs)

| Ação | Ganho Estimado |
|---|---|
| R7. Não popular domain_observation | Evita 540 GB/mês com .com |
| R8. BIGSERIAL vs UUID | -843 MB |
| R9. Partitioning por TLD | Manutenção eficiente em escala |

---

## 6. Upload do zone file: upload antes ou depois do parsing?

Hoje o flow é: **download → upload S3 → parse → delta**. Se o parsing falha, o S3 já tem o artifact.

**Proposta:** Inverter para **download → parse → delta → upload S3 (se sucesso)**. Vantagens:
- Zero artifacts órfãos
- S3 só recebe artifacts de runs com sucesso
- Reduz I/O em caso de falha

**Trade-off:** Se precisar do zone file para debugging de uma falha, ele estará disponível apenas no cache local (`/data/czds/`). Solução: manter o cache local por 48h mesmo em caso de falha.

---

## 7. Priorização Recomendada

```
Sprint 1 (imediato):
  ✅ R1 — Drop índice duplicado
  ✅ R2 — Cleanup artifacts órfãos
  ✅ R4 — Limpeza cache local após sucesso

Sprint 2 (próxima iteração):
  🔧 R3 — Política de retenção S3
  🔧 R6 — Inverter ordem (parse antes de upload)

Sprint 3 (antes de adicionar .com):
  🏗️ R5 — Remover created_at/updated_at
  🏗️ R8 — Avaliar BIGSERIAL
  🏗️ R9 — Partitioning por TLD
```
