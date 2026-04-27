# ADR-002: Arquitetura de ingestao diaria e atualizacao por TLD

- **Status:** Proposta
- **Data:** 2026-04-27
- **Autores:** Marcos Lira, Codex
- **Deciders:** Marcos Lira
- **Relacionada a:** [ADR-001: Redesign da tabela `domain` para pipeline de ingestao otimizado](./001-domain-table-redesign.md)
- **Contexto tecnico:** PostgreSQL 16, particoes LIST por TLD, Databricks, R2, FastAPI, worker de ingestao

---

## Contexto

A necessidade de negocio e manter a base de dominios atualizada por TLD, com custo operacional viavel e sem degradar as consultas de similaridade.

A [ADR-001](./001-domain-table-redesign.md) definiu a base do modelo:

1. `domain` passa a ser append-only, com `added_day`
2. `domain_removed` registra remocoes com `removed_day`
3. particionamento por TLD continua sendo a unidade fisica principal
4. a trilha de auditoria operacional nao fica em `domain`; fica em metadados de execucao

Com isso, a ingestao deixa de ser "reprocessar e regravar tudo" e passa a ser "descobrir delta por TLD e aplicar apenas o necessario".

As fontes atuais possuem caracteristicas diferentes:

- **CZDS**: gTLDs com zone files grandes, incluindo TLDs massivos como `.com`
- **OpenINTEL**: snapshots de ccTLDs e TLDs com atraso natural de disponibilidade
- **CertStream**: fluxo incremental quase em tempo real, complementar ao estoque diario

O sistema tambem precisa atender requisitos operacionais:

- idempotencia por `source + tld + snapshot_date`
- possibilidade de reprocessar carga no PostgreSQL sem rerodar o compute remoto
- rastreabilidade de falhas por TLD
- capacidade de diferenciar "nao executou hoje", "executou e falhou", "executou e carregou", "snapshot indisponivel"

---

## Problema

Precisamos de uma arquitetura de ingestao que resolva, ao mesmo tempo:

1. **Atualizacao diaria dos TLDs** sem UPDATE massivo em tabelas gigantes
2. **Escalabilidade** para TLDs grandes, especialmente os que estouram memoria ou tempo no caminho local
3. **Idempotencia e recuperacao** quando o processamento remoto conclui, mas a carga local falha
4. **Auditoria operacional** clara no `/admin/ingestion`
5. **Compatibilidade com o modelo do ADR-001**, sem reintroduzir colunas ou semanticas que ele removeu

---

## Decisao

Adotaremos uma arquitetura de ingestao diaria orientada a **delta por TLD**, com **Databricks-first progressivo**, **artefatos intermediarios em R2** e **PostgreSQL como destino canonico**.

### Principios

1. **A unidade operacional e o TLD**
- ordenacao, politicas de habilitacao, retries e status sao controlados por TLD
- particoes fisicas `domain_<tld>` e `domain_removed_<tld>` sao o alvo natural da carga

2. **A unidade de idempotencia e `(source, tld, snapshot_date)`**
- uma execucao bem sucedida para esse triplo nao deve ser refeita sem necessidade
- se o artefato ja existe no R2, o sistema pode fazer apenas `LOAD_ONLY`

3. **A ingestao persiste delta, nao snapshot bruto, no banco**
- `delta_added` alimenta `domain`
- `delta_removed` alimenta `domain_removed`
- `domain` nao recebe `UPDATE` recorrente de "last seen"

4. **O compute pesado fica fora do PostgreSQL**
- download, diff e montagem dos artefatos devem ocorrer preferencialmente no Databricks para TLDs grandes
- o banco fica focado em `COPY`, `INSERT` e manutencao de indices/particoes

5. **Auditoria operacional fica separada do dado de produto**
- `ingestion_run`, incidentes e status por TLD respondem "o que aconteceu"
- `domain` e `domain_removed` respondem "qual e o estado conhecido do dominio"

---

## Arquitetura alvo

```text
Fonte (CZDS/OpenINTEL)
  -> resolver snapshot do TLD
  -> gerar delta_added + delta_removed
  -> persistir artefatos parquet + marker no R2
  -> carregar PostgreSQL por particao do TLD
  -> registrar run/auditoria/metricas
```

### Fases canonicas por TLD

Cada TLD entra em exatamente uma das fases abaixo no ciclo:

1. **SKIP**
- marker do R2 existe
- e ja existe sucesso para `source + tld + snapshot_date`
- nenhuma acao adicional

2. **LOAD_ONLY**
- marker do R2 existe
- mas o PostgreSQL ainda nao confirmou sucesso para aquele snapshot
- reaproveita artefatos do R2 sem rerodar Databricks

3. **FULL_RUN**
- nao existe marker valido
- precisa executar download, diff, persistencia no R2 e depois carga no PostgreSQL

Essa semantica e obrigatoria para suportar recuperacao barata e para evitar rerun remoto desnecessario.

---

## Como a arquitetura atende a necessidade de atualizacao dos TLDs

### 1. Novos dominios

Quando um dominio aparece no snapshot atual e nao existia no snapshot anterior do mesmo TLD:

- ele entra no `delta_added`
- o loader grava em `domain_<tld>` com `added_day`
- a gravacao usa `ON CONFLICT DO NOTHING` ou estrategia equivalente de deduplicacao

Efeito:
- o banco conhece o dominio como presente
- a query de similaridade passa a encontralo
- nao existe custo de atualizar rows antigas

### 2. Dominios removidos

Quando um dominio existia no snapshot anterior e deixou de existir no snapshot atual:

- ele entra no `delta_removed`
- o loader grava em `domain_removed_<tld>` com `removed_day`

Efeito:
- a plataforma consegue auditar desaparecimentos
- fluxos de limpeza e reclassificacao de similaridade podem invalidar matches obsoletos
- nao precisamos usar `last_seen_at` para inferir remocao

### 3. TLD sem snapshot novo

Quando a fonte nao disponibiliza snapshot para aquele TLD no dia:

- a execucao nao deve simular sucesso
- deve registrar `reason_code` explicito, como `no_snapshot`
- o status funcional continua derivado do ultimo estado valido conhecido

Isso evita que a ausencia de material novo pareca uma atualizacao bem sucedida.

### 4. Reexecucao segura

Se o Databricks ja produziu o delta, mas a carga no PostgreSQL falhou:

- o caminho correto e `LOAD_ONLY`
- o sistema nao deve recalcular diff remoto nem redownload do TLD
- em falhas parciais, como `domain_removed` apenas, a recuperacao deve evoluir para fallback automatico especializado

Isso reduz custo, tempo e superficie de falha.

---

## Decisoes derivadas do ADR-001

### D1. `domain` nao registra origem nem estado operacional

Nao teremos `source`, `last_seen_at` ou flags de execucao em `domain`.

Razao:
- isso conflita com o principio append-only do ADR-001
- mistura dado de produto com controle operacional
- reintroduz custo recorrente de escrita

### D2. `domain_removed` e obrigatoria para a estrategia diaria

Ela nao e opcional ou "nice to have".

Razao:
- sem `domain_removed`, a remocao de um dominio some do sistema
- o produto continuaria tratando como vivo um dominio que ja saiu da zona

### D3. O TLD continua sendo a fronteira de particionamento e de rollout

Razao:
- e a unidade que melhor alinha armazenamento, monitoramento, performance e retries
- evita duplicacao do dado por source

### D4. R2 e parte do contrato operacional, nao apenas cache

Razao:
- sem artefato intermediario persistido, nao existe `LOAD_ONLY`
- sem `LOAD_ONLY`, toda falha local empurra rerun remoto

---

## Estrategia de execucao

### Politica por fonte

- **OpenINTEL:** preferencia por `databricks_only`, com particionamento em batches menores quando necessario
- **CZDS:** preferencia por `databricks_only` para TLDs grandes; admissivel `hybrid` durante rollout controlado
- **CertStream:** permanece como fluxo incremental separado, complementando descoberta, nao substituindo o ciclo diario de snapshot

### Ordenacao

- a ordem de execucao deve vir de `ingestion_tld_policy`
- TLDs pequenos podem ser processados individualmente
- TLDs grandes podem ser agrupados em batches quando isso nao violar memoria, rate limit ou previsibilidade
- `.com`, quando necessario, pode permanecer isolado

### Heartbeat e stale recovery

Toda execucao precisa atualizar heartbeat durante etapas longas e recuperar `running` stale automaticamente.

Razao:
- o painel operacional nao pode confundir run orfao com atividade real

---

## Observabilidade e auditoria

O sistema deve responder separadamente:

1. **Estado do ciclo atual**
- esta executando?
- qual TLD/fase atual?
- quantos ativos vs stale?

2. **Estado do TLD no dia**
- executou hoje?
- sucesso, falha, skip, no snapshot?

3. **Saude funcional**
- qual o ultimo sucesso conhecido?
- qual a ultima falha?
- ha degradacao recente?

4. **Incidentes auditaveis**
- `run_id`
- `source`
- `tld`
- `reason_code`
- mensagem curta

Isso e necessario porque a tabela `domain` nao deve ser usada para inferir o andamento operacional do pipeline.

---

## Consequencias

### Positivas

- alinha completamente a ingestao com o modelo append-only do ADR-001
- reduz drasticamente UPDATEs caros em TLDs massivos
- permite recuperar carga no PostgreSQL sem rerodar compute remoto
- melhora auditabilidade por TLD e por snapshot
- cria base robusta para o `/admin/ingestion`

### Negativas

- aumenta a dependencia do contrato de artefatos no R2
- exige disciplina de `reason_code`, heartbeat e fechamento correto dos runs
- batches ruins no Databricks podem falhar por memoria ou rate limit e exigem particionamento cuidadoso
- o loader fica mais sofisticado, porque precisa lidar com particoes, reattach e recuperacao parcial

### Tradeoff assumido

Aceitamos maior complexidade operacional na camada de ingestao para manter:

- o modelo de dados de produto simples
- o banco eficiente para leitura
- a recuperacao de falhas barata e previsivel

---

## Alternativas consideradas e rejeitadas

### A1: Reprocessar snapshot inteiro diretamente no PostgreSQL a cada dia

**Rejeitada porque:**

- contradiz o ADR-001
- reintroduz custo massivo de escrita
- torna TLDs grandes inviaveis operacionalmente

### A2: Tratar R2 apenas como cache descartavel

**Rejeitada porque:**

- elimina `LOAD_ONLY`
- obriga rerun remoto apos qualquer falha local
- piora custo e tempo de recuperacao

### A3: Usar `domain` como fonte de monitoramento operacional

**Rejeitada porque:**

- `domain` representa estado de produto, nao trilha de execucao
- nao permite distinguir `no_snapshot`, `submit_error`, `pg_load_error`, `stale_recovered`

### A4: Manter caminho local como padrao para tudo

**Rejeitada porque:**

- nao escala para batches grandes
- aumenta risco de OOM no ambiente do worker
- conflita com a estrategia de mover compute pesado para Databricks

---

## Criterios de aceite arquiteturais

Uma implementacao aderente a esta ADR deve garantir:

1. nenhum TLD precisa de `UPDATE` recorrente em `domain` para ser considerado atualizado
2. toda atualizacao diaria gera, ou reaproveita, artefato identificavel por `source + tld + snapshot_date`
3. uma falha de carga local pode ser recuperada sem recalcular o snapshot remoto
4. remocoes de dominio ficam registradas em `domain_removed`
5. a camada de observabilidade consegue explicar por TLD se houve sucesso, falha, skip, ausencia de snapshot ou recuperacao

---

## Implicacoes de implementacao

1. `ingestion_run` continua sendo o registro canonico de execucao por TLD
2. `reason_code` precisa ser padronizado e exibido na API/UI
3. o contrato de layout do R2 precisa permanecer estavel e versionavel
4. o loader deve tolerar recuperacao parcial e evoluir para fallback automatico quando o remoto concluiu com sucesso
5. a semantica de "status do dia" e "ultima tentativa" precisa ficar explicita no `/admin/ingestion`

---

## Referencias

- [ADR-001: Redesign da tabela `domain` para pipeline de ingestao otimizado](./001-domain-table-redesign.md)
- [czds-ingestion-optimization-study.md](../czds-ingestion-optimization-study.md)
- [domain-infrastructure-master-plan.md](../domain-infrastructure-master-plan.md)
- [similarity-analysis-architecture.md](../similarity-analysis-architecture.md)
- [ingestion-cleanup-and-certstream-reference.md](../ingestion-cleanup-and-certstream-reference.md)
