# Domain Infrastructure — Master Plan

> Data: 2026-03-21 | Autor: Claude (análise técnica) + Marco (decisões de produto)
> Status: Aprovado para implementação
> Documentos relacionados:
> - `docs/czds-ingestion-optimization-study.md` — diagnóstico inicial (2026-03-19)
> - `docs/domain-table-redesign-proposal.md` — redesign da tabela domain
> - `docs/similarity-analysis-architecture.md` — arquitetura de similaridade
> - `docs/tipos-analises-dominios.md` — tipos de análise e técnicas

---

## Sumário Executivo

A infraestrutura de domínios do Observador de Domínios precisa de uma reestruturação para suportar o core do produto: **detecção de domínios suspeitos por similaridade, abuso de marca e risco**.

### Estado atual

| Métrica | Valor |
|---|---|
| Domínios na base | 31.275.338 (3 TLDs: net, org, info) |
| Tamanho PostgreSQL | 9.8 GB (após otimizações R1/R2/R4) |
| Tabela domain | 7.3 GB (dados + 4 índices) |
| Schema | 9 colunas, UUID PK, status string, soft-delete explícito |
| Capacidade de similaridade | **Nenhuma** — não há índice trigram, embedding ou normalização |
| Projeção para .com (160M) | ~44 GB (inviável no schema atual) |

### Estado alvo

| Métrica | Valor |
|---|---|
| Schema domain | 5 colunas, name PK natural, partitioned por TLD |
| Tamanho 31M (3 TLDs) | ~5.1 GB (com label + GIN trigram) |
| Tamanho 200M (10 TLDs) | ~33 GB |
| Capacidade de similaridade | **Completa** — trigram, Levenshtein, substring, typosquatting, homograph |
| Query de similaridade | < 100ms por brand × TLD (com GIN index) |
| Ingestão | 1 passo por batch (vs 5 atuais), sem staging table, sem soft-delete |

### Economia total

| Componente | Antes | Depois | Economia |
|---|---|---|---|
| domain table (31M) | 7.3 GB | 5.1 GB | -2.2 GB (-30%) |
| domain table (200M projeção) | 44 GB | 33 GB | -11 GB (-25%) |
| MinIO artifacts | 3.1 GB | 0.97 GB | -2.1 GB (já aplicado) |
| Ingestão: passos/batch | 5 | 1 | -80% I/O |
| Ingestão: soft-delete pass | UPDATE em milhões | Eliminado | -100% |

**Nota:** O schema proposto é levemente maior que a versão sem label (~2.4 GB), mas inclui capacidade de similaridade que antes não existia. A troca é: +2.7 GB de label+GIN em troca de queries de similaridade em < 100ms.

---

## Decisões Técnicas Consolidadas

### D1. PK natural em `name` (sem UUID)

- **Escolha:** `name` VARCHAR(253) como PK + `tld` na PK composta (requisito do partitioning)
- **Motivo:** Nenhuma FK referencia `domain.id`. A tabela `domain_observation` tem 0 rows e será dropada. Elimina coluna UUID (16 bytes) + índice PK (1.2 GB).
- **Trade-off:** Se no futuro uma FK apontar para domain, precisará referenciar `name` (string) em vez de UUID. Aceitável porque FKs para tabelas de 200M+ rows são raras e geralmente anti-pattern.

### D2. Sem status — derivado de `last_seen_at`

- **Escolha:** Remover colunas `status`, `deleted_at`, `created_at`, `updated_at`
- **Motivo:** "Ativo" = `last_seen_at >= checkpoint do último sync`. Elimina o UPDATE massivo de soft-delete por run (que hoje processa milhões de rows por ingestão).
- **Trade-off:** Queries de "ativos" precisam saber a data do último sync (disponível em `ingestion_checkpoint`).

### D3. Coluna `label` para similaridade

- **Escolha:** Adicionar coluna `label` VARCHAR(228) = name sem TLD suffix
- **Motivo:** GIN trigram index no label é o coração da busca de similaridade. Sem ele, cada busca seria seq scan de minutos. Com ele, < 100ms.
- **Custo:** ~2.7 GB para 200M rows (coluna) + ~10.5 GB (GIN index) = ~13 GB
- **Alternativa descartada:** Functional GIN index em `left(name, ...)` — complexo, frágil, e performance inferior.

### D4. Partitioning por TLD (LIST)

- **Escolha:** `PARTITION BY LIST (tld)`, uma partição por TLD ingerido
- **Motivo:** Partition pruning (queries filtram por TLD), VACUUM/REINDEX isolado, escalabilidade modular.
- **Criação dinâmica:** Partições criadas automaticamente quando um TLD é habilitado em `czds_tld_policy`.

### D5. pg_trgm como motor principal de similaridade (não pgvector)

- **Escolha:** `pg_trgm` GIN + `fuzzystrmatch` Levenshtein + geração de candidatos
- **Motivo:** pgvector na tabela inteira = 715 GB para 200M rows. pg_trgm = 13 GB. Trigram cobre typosquatting, homograph, brand containment e keyword risk (~90% dos ataques reais).
- **pgvector quando:** V2+, on-the-fly no candidate set (~10k domínios), zero storage extra.

### D6. Drop da tabela `domain_observation`

- **Escolha:** Remover tabela (0 rows, nunca populada)
- **Motivo:** Se populada com 1 row por domínio por run, seria 160M rows/dia com .com = 540 GB/mês. Insustentável.
- **Alternativa futura:** Tabela de **deltas** (apenas domínios que entraram/saíram), não observações completas.

### D7. Análise de similaridade desacoplada da ingestão

- **Escolha:** Tabelas separadas (`monitored_brand`, `similarity_scan_cursor`, `similarity_match`) + worker dedicado
- **Motivo:** Ingestão é write-heavy e precisa ser rápida. Análise é read-heavy e pode rodar assincronamente. Misturar as duas degrada ambas.

---

## Plano de Implementação — Fases

### Fase 1: Redesign da tabela domain

**Escopo:** Migration + código + validação da tabela domain com novo schema.

**Entregáveis:**
- Migration 005: schema particionado com label
- Extensions: `pg_trgm`, `fuzzystrmatch`
- Model `domain.py` atualizado
- Repository `domain_repository.py` simplificado (sem staging, sem soft-delete)
- Use case `apply_zone_delta.py` simplificado
- Drop `domain_observation`
- Validação: ingestão de 1 TLD, verificação de dados e performance

**Especificação completa:** `docs/domain-table-redesign-proposal.md`

**Estimativa:** 1-2 dias

### Fase 2: Infraestrutura de similaridade

**Escopo:** Models, repositories e services para análise de similaridade.

**Entregáveis:**
- Models: `monitored_brand`, `similarity_scan_cursor`, `similarity_match`
- Migration 006: tabelas de análise
- Repository: `similarity_repository.py` (queries de candidatos com trigram/Levenshtein)
- Service: `compute_similarity.py` (scoring engine)
- Service: `run_similarity_scan.py` (orchestração com watermark)
- Normalização homograph + geração de candidatos typosquatting

**Especificação completa:** `docs/similarity-analysis-architecture.md` (seções 7-10)

**Estimativa:** 3-5 dias

### Fase 3: Worker e API

**Escopo:** Worker de similaridade + endpoints de brands e matches.

**Entregáveis:**
- Worker: `similarity_worker.py` (scheduler, trigger após ingestão)
- API: `POST/GET /v1/brands` (CRUD de marcas monitoradas)
- API: `GET /v1/brands/{id}/matches` (resultados de similaridade)
- API: `PATCH /v1/matches/{id}` (review workflow: dismiss/confirm)
- Stack: serviço `similarity_worker` no `stack.dev.yml`

**Estimativa:** 2-3 dias

### Fase 4: Validação e ajuste

**Escopo:** Testes com dados reais, ajuste de thresholds, performance.

**Entregáveis:**
- Teste com brands reais (google, itau, nubank, mercadolivre)
- Medição precision/recall com dataset de ataques conhecidos
- Ajuste de pesos do scoring
- Performance profiling em escala (31M domains)
- Documentação de resultados

**Estimativa:** 1-2 dias

---

## Dependências e Ordem

```
Fase 1 (domain redesign)
  │
  ├──► Fase 2 (similarity infra) ──► Fase 3 (worker + API) ──► Fase 4 (validação)
  │
  └──► Ingestão CZDS continua funcionando (já simplificada)
```

Fase 1 é pré-requisito para tudo. Após fase 1, a ingestão já funciona com o novo schema. Fases 2-4 são o core de similaridade.

---

## Riscos

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Migration de 31M rows falha ou demora | Baixa | Alto | Backup antes, rollback plan com domain_old, testar em dev primeiro |
| GIN trigram index em 200M rows fica lento | Baixa | Médio | Partitioning garante que cada partição tem GIN próprio, partition pruning filtra |
| Trigram não detecta ataques semânticos | Média | Médio | V2 adiciona embedding on-the-fly (custo marginal). V1 já cobre 90%+ |
| Muitas brands monitoradas (1000+) degradam performance | Baixa | Médio | Paralelizar scans, batch processing, priorização por plano do cliente |
| Regressão na ingestão após redesign | Média | Alto | Manter domain_old por 7 dias, validar com ingestão real antes de dropar |

---

## Referências Cruzadas

| Documento | O que cobre |
|---|---|
| `docs/czds-ingestion-optimization-study.md` | Diagnóstico completo: tamanhos, índices, problemas, R1-R9 |
| `docs/domain-table-redesign-proposal.md` | Schema proposto, migration SQL, código Python, rollback plan |
| `docs/similarity-analysis-architecture.md` | Estratégias de busca, scoring, watermark, worker, pgvector analysis |
| `docs/tipos-analises-dominios.md` | Técnicas de detecção: trigram, Levenshtein, homograph, embedding, scoring |
| `.specs/features/domain-database/prd.md` | PRD da base global de domínios |
| `.specs/todos/003/plan.md` | Plano do Similarity Service |
| `docs/similarity-service-refinement.md` | Refinamento técnico do similarity service |

---

## Ações Realizadas

### Pré-implementação (2026-03-19)

| Ação | Status | Ganho |
|---|---|---|
| R1: Drop índice duplicado `ix_domain_name` | ✅ Aplicado | -1.880 MB |
| R2: Cleanup artifacts órfãos no MinIO | ✅ Aplicado | -2.205 MB |
| R2: Prevenção de órfãos futuros no `sync_czds_tld` | ✅ Código alterado | Evita acúmulo |
| R4: Limpeza cache local após sucesso | ✅ Código alterado | -785 MB recorrente |

### Fase 1: Domain Redesign (2026-03-21) ✅

| Ação | Status |
|---|---|
| Migration 005: partitioned table, natural PK, label, GIN trigram | ✅ Aplicado |
| Domain model reescrito (5 colunas, sem UUID/status) | ✅ |
| DomainRepository simplificado (bulk_upsert único) | ✅ |
| apply_zone_delta simplificado (sem staging, sem soft-delete) | ✅ |
| Auto-criação de partições em sync_czds_tld | ✅ |
| Drop domain_observation (0 rows) | ✅ |
| **Resultado:** 8.8 GB → 5.8 GB (-34%) | |

### Fase 2: Similarity Infrastructure (2026-03-22) ✅

| Ação | Status |
|---|---|
| Migration 006: monitored_brand, similarity_scan_cursor, similarity_match | ✅ Aplicado |
| Models: MonitoredBrand, SimilarityScanCursor, SimilarityMatch | ✅ |
| Repository: MonitoredBrandRepository (CRUD) | ✅ |
| Repository: SimilarityRepository (candidate queries + match ops) | ✅ |
| Scoring engine: compute_similarity.py (trigram, Levenshtein, homograph, keywords) | ✅ |
| Scan orchestration: run_similarity_scan.py (watermark, initial/delta) | ✅ |
| Schemas Pydantic: brands + similarity | ✅ |

### Fase 3: Worker + API (2026-03-22) ✅

| Ação | Status |
|---|---|
| API: POST/GET/PATCH/DELETE /v1/brands (CRUD) | ✅ |
| API: POST /v1/brands/{id}/scan (trigger scan) | ✅ |
| API: GET /v1/brands/{id}/matches (list matches filterable) | ✅ |
| API: GET/PATCH /v1/matches/{id} (review workflow) | ✅ |
| Worker: similarity_worker.py (scheduled scans) | ✅ |
| Stack: similarity_worker service em stack.dev.yml | ✅ |

### Fase 4: Validação (2026-03-22) ✅

| Brand | Matches | Critical | Scan time |
|---|---|---|---|
| Google | 5,478 | 440 | 0.1s (delta) |
| Nubank | 687 | 22 | 3.5s |
| MercadoLivre | 439 | 4 | 6.1s |
| Facebook | 2,579 | 235 | 7.6s |
| Bradesco | 1,236 | 98 | 8.5s |
| Itau | 1,077 | 94 | 3.3s |

**Tuning aplicado:** threshold dinâmico (0.5 para labels <= 5 chars, 0.3 para maiores).
**Performance:** GIN index confirmado em todos os candidate queries (120-260ms).
**FP rate:** matches "low" são noise aceitável; "critical" tem alta precisão.

## Próximo Passo

**Fase 5 (V2):** Embedding on-the-fly para candidatos (MiniLM), ajuste de pesos por feedback.
