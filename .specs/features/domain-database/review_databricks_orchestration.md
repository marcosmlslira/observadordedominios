# Revisão Técnica: Orquestração Databricks + Modelo Particionado de Domínios

**Revisor:** Claude (Opus 4.6)
**Data:** 2026-04-22
**Documentos revisados:**
- `prd.md` — PRD da base global de domínios
- `spec_databricks_orchestration_and_partitioned_domains.md` — Spec técnica
- `spec_impact_analysis_databricks_orchestration.md` — Análise de impacto
**Base de comparação:** Estado atual do codebase (models, repositories, use cases, scripts)

---

## 1. Avaliação geral

A proposta é **sólida na direção estratégica**: migrar de ingestão monolítica (full reload por TLD) para processamento em Databricks com deltas incrementais é a decisão correta para escalar `.com` e outros TLDs de alto volume. O modelo particionado por `source+tld+date` resolve limitações reais do modelo atual.

No entanto, identifico **lacunas significativas entre o PRD e a spec**, **decisões de modelagem questionáveis**, e **acoplamentos que podem dificultar a evolução futura**. Abaixo detalho cada ponto.

**Nota:** 7/10 — boa fundação, precisa de ajustes antes de implementar.

---

## 2. Pontos fortes

### 2.1 Deltas incrementais em vez de full reload
A abordagem `new_domains` / `removed_domains` é muito superior ao modelo atual onde cada sync por TLD faz scan completo da zone file. O ganho é especialmente crítico para `.com` (~160M domínios), onde full reload é inviável em PostgreSQL.

### 2.2 Partição de negócio (`source+tld+date`)
Chave natural bem escolhida. Permite:
- Reprocessamento cirúrgico (um TLD, um dia),
- Falha parcial sem contaminar o lote inteiro,
- Similaridade incremental só no que é novo.

### 2.3 Idempotência como requisito de primeira classe
As regras de idempotência (seção 18.6 da spec) são claras e corretas: `ON CONFLICT` por chave natural, markers como gate de prontidão, replay apenas com flag explícita.

### 2.4 Análise de impacto bem estruturada
O documento de impacto cobre recursos, riscos e mitigações com granularidade útil. A matriz por time (backend, DBA, DevOps, QA) é pragmática.

### 2.5 Contrato de paths R2 detalhado
A seção 18.4 é excelente — paths versionados com `source`, `tld`, `snapshot_date`, `run_id` e `shard` dão rastreabilidade completa.

---

## 3. Lacunas entre PRD e Spec

O PRD define um produto ambicioso. A spec implementa uma fatia dele, mas **não delimita explicitamente o que ficou de fora**. Isso cria ambiguidade sobre o que é "fase futura" vs "esquecido".

| Requisito do PRD | Status na Spec | Risco |
|---|---|---|
| DNS snapshots (A, AAAA, NS, MX, TXT) | **Ausente** | Médio — deve ser declarado fora de escopo |
| `registered_at_best` com score de confiança | **Ausente** | Alto — é requisito de prioridade Alta no PRD |
| CT Logs como fonte | **Ausente** | Baixo — pode ser fase futura |
| pDNS como fonte | **Ausente** | Baixo — pode ser fase futura |
| Paid feeds como fonte | **Ausente** | Baixo — pode ser fase futura |
| Modelo event+snapshot temporal | **Parcialmente** — deltas são append-only, mas não há snapshot temporal versionado | Médio |
| Ciclo de vida independente por fonte | **Implementado** via `domain_ingestion_run` | ✓ OK |
| Normalização canônica | **Implícita** (Databricks faz) mas não especificada no backend | Médio |

**Recomendação:** Adicionar seção "Deliberadamente fora de escopo nesta fase" listando cada item do PRD que não será coberto e em qual fase futura é esperado.

---

## 4. Problemas de modelagem

### 4.1 `domain_raw_b64` — campo desnecessário

A spec inclui `domain_raw_b64` (base64 do domínio bruto) em **todas** as tabelas de delta e current. Isso:
- Triplica o armazenamento para domínios IDN (que já estão representados em `domain_raw` + `domain_norm`/punycode),
- Não tem caso de uso claro na spec (nenhuma query ou API consome esse campo),
- Adiciona complexidade de encoding sem benefício.

**O que eu faria:** Remover `domain_raw_b64`. Manter apenas `domain_norm` (punycode/canonical) e `domain_raw` (UTF-8 original). Se houver necessidade de serialização binária segura, isso é responsabilidade da camada de transporte, não do modelo.

### 4.2 `SMALLINT` para `source_code` — otimização prematura

O codebase atual usa `TEXT` para source (ex.: `"czds"`, `"openintel"`). A spec propõe uma dimensão `domain_source_dim` com `SMALLINT` codes.

Problemas:
- Adiciona JOINs em toda query que precisa do nome da fonte,
- Fontes são ~5 no horizonte visível — economia de bytes é irrelevante,
- Quebra compatibilidade com o modelo existente sem ganho mensurável,
- Torna debugging menos legível (`source_code=1` vs `source='czds'`).

**O que eu faria:** Usar `TEXT` com CHECK constraint (`CHECK (source IN ('czds', 'openintel', ...))`). Se performance for preocupação futura, um `ENUM` type no PostgreSQL é mais ergonômico que uma dimension table.

### 4.3 `similarity_status` acoplado em `domain_ingestion_partition`

Colocar `similarity_status`, `similarity_started_at`, `similarity_finished_at` diretamente na tabela de partição de ingestão **acopla dois domínios distintos**:

- E se similaridade precisar re-rodar por motivo externo à ingestão (ex.: novo brand cadastrado)?
- E se uma partição precisar rodar similaridade para múltiplos brands em momentos diferentes?
- E se o pipeline de similaridade ganhar mais estados (ex.: `enriching`, `reviewing`)?

O modelo atual já tem `similarity_scan_job` e `similarity_scan_cursor` que rastreiam progresso por brand×TLD. A spec não menciona como esses se relacionam com o novo `similarity_status` por partição.

**O que eu faria:** Manter `similarity_status` em tabela separada (`domain_similarity_queue` ou similar) com FK para a partição. Isso permite:
- Múltiplas execuções por partição,
- Estados independentes da ingestão,
- Histórico de runs de similaridade por partição.

### 4.4 `domain_current` sem estratégia de particionamento

A spec define particionamento por `snapshot_date` para tabelas de delta, mas `domain_current` não tem particionamento definido. Com centenas de milhões de domínios ativos:
- VACUUM e REINDEX se tornam operações pesadas,
- Índice GIN de trigrama (necessário para similaridade) em tabela não-particionada degrada com volume.

**O que eu faria:** Particionar `domain_current` por `tld` (list partition). Isso:
- Alinha com a forma como similaridade já consulta (por TLD),
- Permite manutenção por partição,
- Mantém índices de trigrama em tamanhos gerenciáveis.

### 4.5 Falta de índice GIN trigrama em `domain_current`

O pipeline de similaridade atual depende de `pg_trgm` com índice GIN no campo `label` da tabela `domain`. A spec não menciona índice de trigrama em `domain_current.domain_norm`.

Sem esse índice, as queries de similaridade (ring B — fuzzy trigram) não funcionam. Isso é um **blocker** para o cutover.

**O que eu faria:** Declarar explicitamente:
```sql
CREATE INDEX idx_domain_current_trgm ON domain_current
USING gin (domain_norm gin_trgm_ops);
```
E testar performance com volume realista antes do cutover.

---

## 5. Problemas arquiteturais

### 5.1 Normalização como caixa-preta do Databricks

A spec assume que Databricks entrega domínios já normalizados (`domain_norm`), mas não especifica:
- Quais regras de normalização são aplicadas,
- Se o backend valida a normalização recebida,
- O que acontece se Databricks entregar domínio malformado.

O codebase atual tem normalização explícita no backend (lowercase, punycode, trailing dot). Se Databricks divergir dessas regras, o merge com dados existentes quebra silenciosamente.

**O que eu faria:** 
1. Documentar as regras canônicas de normalização em um único lugar (shared contract),
2. Backend deve validar (ao menos sample check) que `domain_norm` recebido segue o contrato,
3. Rejeitar partição inteira se taxa de violação exceder threshold.

### 5.2 Polling de Databricks sem webhook/callback

A spec define polling com timeout/backoff para acompanhar runs Databricks. Isso funciona, mas:
- Consome recursos do backend em loops de espera,
- Runs de `.com` podem levar horas — polling durante esse tempo é wasteful,
- Atraso entre conclusão real e detecção pelo polling.

**O que eu faria:** Se Databricks suportar webhooks, usar callback para notificar conclusão. Se não, polling é aceitável mas deve ser **event-driven no R2**: em vez de checar status do run, checar existência de `markers/.../success.json` periodicamente. O marker é o sinal definitivo de que a partição está pronta, independente do mecanismo de notificação.

### 5.3 Ausência de backpressure

A spec não define o que acontece quando:
- Múltiplas partições ficam prontas simultaneamente,
- O backend não consegue acompanhar a taxa de carga,
- A fila de similaridade cresce indefinidamente.

**O que eu faria:** Definir limites:
- Máximo de partições em carga simultânea (ex.: 4),
- Máximo de partições em fila de similaridade,
- Alerta quando backlog excede N horas.

---

## 6. Problemas operacionais

### 6.1 Cutover precisa de mais validação

A seção 13 define: criar tabelas → carga inicial → validar contagem → feature flag → truncar antiga. Isso é **insuficiente** para um cutover de tabela que é core do produto.

**O que eu faria adicionar:**
1. **Dual-read por período** — aplicação lê de ambas as tabelas e compara resultados em shadow mode,
2. **Validação de similaridade** — rodar scan de similaridade em ambos os modelos e comparar matches encontrados,
3. **Rollback plan** — manter tabela antiga por ao menos 30 dias após cutover (não truncar imediatamente),
4. **Canary por TLD** — migrar um TLD pequeno (ex.: `.museum`) primeiro, validar end-to-end, depois expandir.

### 6.2 Retenção de deltas não definida

As tabelas `domain_delta_added` e `domain_delta_removed` são append-only por snapshot_date. Em 1 ano de operação com ~300 TLDs:
- Volume pode chegar a centenas de milhões de linhas,
- Sem política de retenção, o banco cresce indefinidamente.

**O que eu faria:** Definir política de retenção (ex.: manter deltas dos últimos 90 dias). Particionamento por `snapshot_date` facilita `DROP PARTITION` para expiração.

---

## 7. O que está faltando na spec

| Item | Impacto | Sugestão |
|---|---|---|
| Como `domain_current` se conecta com `similarity_match` (FK, join, etc.) | **Alto** — similarity precisa de domínio para funcionar | Definir explicitamente a relação |
| Migração de dados existentes (tabela `domain` → `domain_current`) | **Alto** — milhões de registros existentes | Plano de migração com script e estimativa |
| Impacto nas queries do `similarity_repository.py` | **Alto** — queries usam `domain.name`, `domain.label`, `domain.tld` | Mapear cada query afetada |
| Como o CertStream (fonte real-time existente) se integra | **Médio** — CertStream não é batch/Databricks | Definir se continua no modelo atual |
| Testes de carga com volume realista | **Alto** — `.com` é o teste definitivo | Plano de load test obrigatório antes do cutover |
| Estimativa de custo Databricks/R2 por mês | **Médio** — decisão de negócio | Budget antes de implementar |

---

## 8. Resumo das recomendações

### Mudanças obrigatórias (blockers)
1. Adicionar índice GIN trigrama em `domain_current` (sem isso, similaridade não funciona)
2. Definir relação entre `domain_current` e o pipeline de similaridade existente
3. Mapear impacto nas queries de `similarity_repository.py`
4. Declarar explicitamente o que do PRD está fora de escopo

### Mudanças recomendadas (alta prioridade)
5. Remover `domain_raw_b64` — sem caso de uso claro
6. Trocar `SMALLINT source_code` por `TEXT source` com CHECK constraint
7. Extrair `similarity_status` para tabela separada
8. Particionar `domain_current` por TLD
9. Definir política de retenção para tabelas de delta

### Melhorias desejáveis
10. Documentar contrato de normalização como spec compartilhada
11. Substituir polling Databricks por verificação de markers R2
12. Definir backpressure e limites de concorrência
13. Expandir plano de cutover com dual-read e canary
14. Estimar custos antes de implementar

---

## 9. Conclusão

A direção está correta: Databricks para processamento pesado, R2 como data lake intermediário, PostgreSQL para estado operacional e consultas de similaridade. O modelo particionado por `source+tld+date` é a abstração certa.

Os ajustes recomendados não mudam a arquitetura — **refinam a modelagem para compatibilidade com o pipeline existente** (especialmente similaridade) e **reduzem risco operacional no cutover**.

A maior preocupação é a **lacuna silenciosa entre PRD e spec**: sem delimitar explicitamente o que ficou de fora, há risco de expectativas desalinhadas durante a implementação.
