# TODO 010 — Catálogo de Problemas: Ciclo de Ingestão em Produção

> Gerado durante execução manual em produção em 27/04/2026.
> Objetivo: executar ciclo completo (OpenINTEL + CZDS), importar incrementais no PostgreSQL e ter visibilidade em `/admin/ingestion`.
> Esta TODO é um **catálogo vivo** — adicionar observações conforme identificadas.

---

## Contexto da Execução

- **Servidor**: `158.69.211.109` (Ubuntu, Docker Swarm)
- **Worker**: `observador_ingestion_worker` (porta 8080, imagem `observadordedominios-ingestion:latest`)
- **Banco**: `observador_postgres` (PostgreSQL, db `obs`, user `obs`)
- **Data da run**: 27/04/2026 ~13:20 UTC (manual) e ~13:56 UTC (segunda tentativa)
- **Run diária anterior**: 04:00 UTC → container morreu (exit 137, SIGKILL, OOM)

---

## Problemas Identificados

---

### 🔴 P01 — Container morto com SIGKILL (exit 137) durante TLD grande

| Campo | Valor |
|-------|-------|
| **Severidade** | CRÍTICA |
| **Categoria** | Infraestrutura / Memória |
| **Status atual** | Identificado, não resolvido |

**Descrição:**  
A run das 04:00 UTC (imagem `9896fe`) morreu com exit 137 (SIGKILL) durante o processamento do TLD `.ch` (zona grande, ~2M domínios em FULL_RUN). O Docker Swarm não tem limite de memória configurado para o container, mas o OOM killer do sistema operacional provavelmente matou o processo quando o consumo de memória ficou alto durante leitura do zone file + cálculo de diff + escrita parquet.

**Evidências:**
```
Container "trytsg0" exited with exit code 137
"ch" → "Automatically marked failed: no progress for 62m (threshold: 60m)"
Outros TLDs grandes afetados: de, com, net, br
```

**Impacto:**
- DDL incompleto no PostgreSQL → corrupção de catalog (ver P02)
- 60+ TLDs ficaram com R2 marker mas sem registro de sucesso no banco
- Ciclo de ingestão abortado antes de completar

**Ações necessárias:**
- [ ] Configurar limite de memória explícito no Docker Swarm (ex: `limits.memory: 4g`) com swap habilitado
- [ ] Processar TLDs grandes (>500k domínios) separadamente ou com streaming em chunks
- [ ] Monitorar consumo de memória por TLD — adicionar log de `psutil.Process().memory_info()`
- [ ] Considerar aumentar o threshold de "no progress" para TLDs grandes (`ch`, `de`, `com`, `net`)

---

### 🔴 P02 — Corrupção de catálogo PostgreSQL em partições IDN (xn--*)

| Campo | Valor |
|-------|-------|
| **Severidade** | CRÍTICA |
| **Categoria** | PostgreSQL / Integridade de dados |
| **Status atual** | Parcialmente resolvido manualmente |

**Descrição:**  
Quando o container morre com SIGKILL durante uma operação DDL (ATTACH/DETACH PARTITION, DROP INDEX), o PostgreSQL pode ficar com o catálogo de sistema em estado inconsistente. Foram encontrados 4 partições IDN nessa situação. Cada uma em estado diferente de corrupção:

**Tabelas afetadas:**
| Tabela | Estado inicial | Problema |
|--------|---------------|---------|
| `domain_xn__qxa6a` | `relispartition=false`, `conparentid=0` | Simples orphan table |
| `domain_xn__wgbh1c` | `relispartition=true`*, `conparentid=107424` | `relispartition` inconsistente + constraint linkada ao pai sem `pg_inherits` |
| `domain_xn__wgbl6a` | `relispartition=true`*, `conparentid=107424` | Idem |
| `domain_xn__xkc2al3hye2a` | `relispartition=true`*, `conparentid=107424` | Idem |
| `domain_xn__yfro4i67o` | `relispartition=true`, `pg_inherits` OK | `pg_attribute` missing 4 attributes |

*`relispartition` foi corrigido para `false` via `SET allow_system_table_mods = on` na sessão anterior.

**Tipos de erro no log do worker:**
```
"domain_xn__wgbh1c" is already a partition (WrongObjectType)
tuple concurrently deleted/updated (durante DETACH ou DROP INDEX)
pg_attribute catalog is missing N attribute(s) for relation OID XXXXX
```

**Correções manuais aplicadas:**
```sql
-- Sessão anterior:
SET allow_system_table_mods = on;
UPDATE pg_class SET relispartition = false WHERE relname IN ('domain_xn__wgbh1c', 'domain_xn__wgbl6a', 'domain_xn__xkc2al3hye2a');
UPDATE pg_constraint SET coninhcount = 0, conislocal = true WHERE conname IN (..._pkey);
UPDATE pg_constraint SET conparentid = 0 WHERE conname IN (..._pkey);
SET allow_system_table_mods = off;

-- Sessão atual:
ALTER TABLE domain ATTACH PARTITION domain_xn__qxa6a FOR VALUES IN ('xn--qxa6a'); -- ✅ OK
ALTER TABLE domain ATTACH PARTITION domain_xn__wgbh1c ... -- ❌ still "multiple primary keys"
ALTER TABLE domain ATTACH PARTITION domain_xn__wgbl6a ... -- ❌ timeout/lock
ALTER TABLE domain ATTACH PARTITION domain_xn__xkc2al3hye2a ... -- ❌ blocked
```

**Análise pendente `domain_xn__wgbh1c`:**
- Após resetar `coninhcount=0`, `conislocal=true`, `conparentid=0` → ainda "multiple primary keys"
- Suspeita: há uma entrada em `pg_index` ou `pg_depend` que ainda aponta para o PK do pai
- Próximo passo: checar `pg_depend` e `pg_index.indrelid` para o index que suporta o PK

**Ações necessárias:**
- [ ] Investigar `pg_depend` para `domain_xn__wgbh1c_pkey` 
- [ ] Possivelmente DROP + recreate do PK constraint manualmente
- [ ] Corrigir `domain_xn__yfro4i67o` (pg_attribute corruption) — tentar VACUUM FULL ou recriação
- [ ] Implementar verificação de saúde das partições no worker (antes de iniciar DETACH)
- [ ] Implementar tratamento gracioso de SIGTERM no worker para não deixar DDL a meio

---

### 🔴 P03 — CI/CD interrompe runs em andamento

| Campo | Valor |
|-------|-------|
| **Severidade** | ALTA |
| **Categoria** | CI/CD / Operação |
| **Status atual** | Identificado, não resolvido |

**Descrição:**  
Qualquer `push to main` dispara o GitHub Actions que faz `docker stack deploy` no servidor de produção. Isso reinicia TODOS os serviços simultaneamente (backend + ingestion_worker + postgres + redis). Nosso segundo run manual (container `trytsg0`) foi interrompido ~16 minutos após o start por um redeploy de CI/CD.

**Evidências:**
```
Backend container: Shutdown 16min ago
Ingestion worker: Shutdown 16min ago  
← aconteceram ao mesmo tempo → CI/CD deploy
```

**Impacto:**
- Run de ingestão abortada no meio
- Partições ficam em estado inconsistente (DDL incompleto)
- `last_run` (in-memory) perdido

**Ações necessárias:**
- [ ] Adicionar `StopGracePeriod` mais longo para ingestion_worker no stack (já tem 6h mas CI/CD pode ignorar?)
- [ ] Antes de fazer `docker stack deploy`, verificar se há run em progresso via `/health`
- [ ] Adicionar handler SIGTERM no scheduler para aguardar TLD atual terminar antes de sair
- [ ] Separar deploy do ingestion_worker do deploy do backend (só fazer stack deploy quando worker está idle)

---

### 🟡 P04 — `INGESTION_TRIGGER_URLS` não configurado no backend

| Campo | Valor |
|-------|-------|
| **Severidade** | MÉDIA |
| **Categoria** | Configuração / Admin UI |
| **Status atual** | Identificado, não resolvido |

**Descrição:**  
A variável de ambiente `INGESTION_TRIGGER_URLS` não está setada no container do backend. O endpoint `/v1/ingestion/trigger/...` não consegue fazer proxy para o worker. A UI em `/admin/ingestion` não consegue disparar runs manualmente.

**Evidências:**
```bash
docker exec observador_backend.1.xxx env | grep INGESTION
# → nenhum resultado
```

**Impacto:**
- Usuário admin não consegue disparar runs pela UI
- Trigger manual requer `docker exec` direto no servidor

**Ações necessárias:**
- [ ] Adicionar `INGESTION_TRIGGER_URLS=http://obs_ingestion_worker:8080` no arquivo de environment do stack (infra/env/)
- [ ] Fazer deploy via CI/CD para aplicar
- [ ] Testar trigger via admin UI

---

### 🟡 P05 — Estado `last_run` in-memory se perde no restart

| Campo | Valor |
|-------|-------|
| **Severidade** | MÉDIA |
| **Categoria** | Observabilidade |
| **Status atual** | Identificado, não resolvido |

**Descrição:**  
O endpoint `/health` do worker retorna `last_run` que é mantido apenas em memória (`_last_run_info` em `scheduler.py`). Após qualquer restart do container (CI/CD, OOM kill, crash), o `/health` mostra `last_run: {}` permanentemente até a próxima run completar. Não há persistência de estado de execução anterior.

**Impacto:**
- `/admin/ingestion` mostra estado vazio após restarts
- Não é possível saber o que aconteceu na última run via UI após restart

**Ações necessárias:**
- [ ] Persistir `last_run` no banco de dados (tabela `ingestion_run` já existe com as informações)
- [ ] Endpoint `/health` deve ler do banco o estado da última run completada se `_last_run_info` estiver vazio

---

### 🟡 P06 — 61 TLDs com R2 marker mas PG load com falha (04:00 UTC)

| Campo | Valor |
|-------|-------|
| **Severidade** | ALTA |
| **Categoria** | Dados / Reprocessamento |
| **Status atual** | Pendente retry |

**Descrição:**  
Na run das 04:00 UTC, 60 TLDs falharam com `duplicate key violates unique constraint "domain_{tld}_pkey"` porque a imagem antiga (`9896fe`) não tinha `ON CONFLICT DO NOTHING` no `_load_shard_worker`. Os R2 markers foram escritos (download + diff OK) mas a carga no PostgreSQL falhou. Na próxima run, esses TLDs entrarão no modo `LOAD_ONLY` (R2 existe, sem sucesso no banco) e devem ser reprocessados com a imagem atual (`d3e44f`) que tem o `ON CONFLICT DO NOTHING`.

**TLDs afetados:** ~60 TLDs (maioria ASCII). Os IDN TLDs com corrupção de catalog são bloqueantes separados.

**Ações necessárias:**
- [ ] Disparar nova run completa → os 60 TLDs devem processar em LOAD_ONLY automaticamente
- [ ] Verificar se todos os 60 tiveram sucesso após a próxima run
- [ ] Confirmar que TLDs IDN problemáticos (P02) precisam da correção de catalog ANTES do retry

---

### 🟡 P07 — Fase CZDS nunca confirmada

| Campo | Valor |
|-------|-------|
| **Severidade** | MÉDIA |
| **Categoria** | Funcionalidade / CZDS |
| **Status atual** | Desconhecido |

**Descrição:**  
Em nenhuma das runs observadas hoje chegamos até a fase CZDS (ambas foram interrompidas antes de concluir OpenINTEL). Não sabemos se:
- CZDS funciona corretamente com a imagem atual
- As credenciais CZDS estão válidas em produção
- Quantos TLDs CZDS estão configurados

**Ações necessárias:**
- [ ] Executar run que complete a fase OpenINTEL para observar início do CZDS
- [ ] Verificar credenciais CZDS no `.env` de produção
- [ ] Monitorar logs da fase CZDS quando iniciar

---

### 🟡 P08 — `restart_policy: condition: any` causa restart em saída limpa

| Campo | Valor |
|-------|-------|
| **Severidade** | BAIXA |
| **Categoria** | Infraestrutura |
| **Status atual** | Identificado |

**Descrição:**  
O Docker Swarm tem `restart_policy: condition: any` para todos os serviços (incluindo ingestion_worker). Isso faz o container reiniciar mesmo em saída limpa (exit 0), criando ruído nos logs e potencialmente mascarando problemas reais.

**Ações necessárias:**
- [ ] Mudar `restart_policy: condition: on-failure` para ingestion_worker
- [ ] Aplicar via CI/CD

---

### 🔵 P09 — Sem autenticação no endpoint `/run-now`

| Campo | Valor |
|-------|-------|
| **Severidade** | BAIXA |
| **Categoria** | Segurança |
| **Status atual** | Identificado |

**Descrição:**  
O endpoint `POST http://localhost:8080/run-now` não tem autenticação. Qualquer processo dentro do Docker network pode disparar uma run. A porta 8080 não está exposta externamente (apenas interna ao Swarm), mas internamente qualquer serviço pode chamar.

**Ações necessárias:**
- [ ] Adicionar token de autenticação simples (Bearer token via env var)

---

### 🔵 P10 — Problema de quoting PowerShell/SSH para SQL com aspas simples

| Campo | Valor |
|-------|-------|
| **Severidade** | BAIXA (operacional) |
| **Categoria** | DevOps / Tooling |
| **Status atual** | Contornado com workaround |

**Descrição:**  
Ao executar comandos PostgreSQL via SSH a partir do PowerShell, o quoting de aspas simples (`'`) em valores SQL causa falhas de parsing. Isso ocorre porque o PowerShell interpreta as aspas antes de passar para o SSH.

**Workaround:**  
Escrever o SQL em um arquivo temporário `/tmp/query.sql` via heredoc e executar com `psql ... < /tmp/query.sql`.

---

### 🟢 P11 — Corrupção Layer 4: PK INDEX com `relispartition=true`

| Campo | Valor |
|-------|-------|
| **Severidade** | ALTA |
| **Categoria** | PostgreSQL / Catálogo |
| **Status atual** | ✅ RESOLVIDO — 27/04/2026 |

**Descrição:**  
Além de corrigir `pg_class` (tabela), `pg_constraint` (coninhcount/conislocal/conparentid), era necessário corrigir também o **índice PK** (`relkind='i'`) que tinha `relispartition=true`. O ATTACH tentava criar novo PK herdado sobre um índice já marcado como partição, resultando em "multiple primary keys".

**Fix aplicado:**
```sql
SET allow_system_table_mods = on;
UPDATE pg_class SET relispartition = false 
WHERE relname IN ('domain_xn__wgbh1c_pkey', 'domain_xn__wgbl6a_pkey', 'domain_xn__xkc2al3hye2a_pkey')
  AND relkind = 'i';
```

**Resultado:** `domain_xn__qxa6a` ✅ ATTACHED, `domain_xn__wgbh1c` ✅ ATTACHED.

**Layer discovery completo (ATTACH PARTITION após SIGKILL):**
| Layer | Objeto | Coluna | Corrompido → Fix |
|-------|--------|--------|-----------------|
| 1 | pg_class (tabela) | relispartition | true → false |
| 2 | pg_constraint | coninhcount | 1 → 0 |
| 2 | pg_constraint | conislocal | false → true |
| 2 | pg_constraint | conparentid | OID pai → 0 |
| 3 | pg_class (índice PK) | relispartition | true → false |
| 4 | pg_depends (indexes) | - | phantom OIDs → DELETE |

---

### 🔴 P12 — WAL LSN corruption em pg_attribute: checkpoint em loop infinito

| Campo | Valor |
|-------|-------|
| **Severidade** | CRÍTICA |
| **Categoria** | PostgreSQL / WAL / Integridade |
| **Status atual** | Identificado — requer restart PostgreSQL |

**Descrição:**  
Block 755 de `pg_attribute` (relfilenode 1249) tem um LSN em memória (`2F1/7F2314D8`) que está **à frente** da posição WAL atual (`2F1/7E6FAFC0`). Isso causa:
1. `CHECKPOINT` falha a cada segundo com "xlog flush request not satisfied"
2. DROP TABLE de qualquer tabela com atributos nesse bloco resulta em timeout
3. Todo DDL que precisa escrever pg_attribute (incluindo DROP/CREATE partições) falha

**Root cause:** SIGKILL durante escrita de WAL criou buffer dirty em memória com LSN inválido.

**Evidência nos logs:**
```
LOG:  request to flush past end of generated WAL; request 2F1/7F2314D8, current position 2F1/7E6FAFC0
CONTEXT: writing block 755 of relation base/16384/1249
ERROR: xlog flush request 2F1/7F2314D8 is not satisfied
WARNING: could not write block 755 --- write error might be permanent.
```
Este loop aparece **a cada segundo** nos logs do container PostgreSQL.

**Fix necessário:** Restart do container PostgreSQL.
- Ao reiniciar, o dirty buffer corrompido é descartado
- PostgreSQL faz crash recovery via WAL replay
- Block 755 é relido do disco (estado válido do último checkpoint bem-sucedido)
- Risco: se o bloco em disco também estiver corrompido, PostgreSQL não sobe

**TLDs afetados:** `domain_xn__xkc2al3hye2a` (não consegue ser dropada/attachada).

---

### 🟡 P13 — Phantom OIDs em pg_depend para partições IDN corrompidas

| Campo | Valor |
|-------|-------|
| **Severidade** | ALTA |
| **Categoria** | PostgreSQL / Catálogo |
| **Status atual** | Parcialmente resolvido — wgbl6a OK, xkc2al3hye2a pendente |

**Descrição:**  
Após SIGKILL durante ATTACH PARTITION (que inclui criação de índices herdados), alguns OIDs de índices são criados em `pg_depend` mas **não chegam a ter entradas em `pg_class`** (phantom dependencies). Isso bloqueia o DROP TABLE com "cache lookup failed for relation {oid}".

**Exemplo (domain_xn__wgbl6a):**
```sql
-- OIDs 138595, 138596 em pg_depend sem entrada em pg_class
SELECT * FROM pg_class WHERE oid IN (138595, 138596); -- retorna 0 rows
DELETE FROM pg_depend WHERE classid = 'pg_class'::regclass AND objid IN (138595, 138596);
```
Após cleanup: `DROP TABLE domain_xn__wgbl6a` ✅ sucesso.

**Situação `domain_xn__xkc2al3hye2a`:** pg_depend limpo (138598, 138599 existem em pg_class), mas DROP ainda falha por P12 (WAL flush timeout no pg_attribute block 755).

---

### 🔴 P14 — `domain_xn__yfro4i67o`: tabela ATTACHED mas pg_attribute com 0 colunas

| Campo | Valor |
|-------|-------|
| **Severidade** | CRÍTICA |
| **Categoria** | PostgreSQL / Catálogo |
| **Status atual** | Identificado |

**Descrição:**  
A tabela `domain_xn__yfro4i67o` (OID 111607) está no `pg_inherits` (ATTACHED ao parent `domain`), mas seu `pg_attribute` retorna **0 linhas** para atributos com `attnum > 0`. Isso significa que a tabela foi criada sem colunas no catálogo — provavelmente um CREATE TABLE intermediário corrompido por SIGKILL, onde `pg_class` foi escrito mas `pg_attribute` não.

**Evidências:**
```sql
SELECT count(*) FROM pg_attribute WHERE attrelid = 111607 AND attnum > 0;
-- retorna: 0

REFRESH MATERIALIZED VIEW tld_domain_count_mv;
-- ERROR: pg_attribute catalog is missing 4 attribute(s) for relation OID 111607
```

**Impacto:**
- `REFRESH MATERIALIZED VIEW tld_domain_count_mv` FALHA → `/admin/ingestion` sem dados de contagem
- Qualquer query que toque `domain_xn__yfro4i67o` (como SELECT * FROM domain) falha
- A próxima run de ingestão vai tentar usar essa tabela e falhar

**Fix necessário:**
1. DETACH partition (catalog direto via `pg_inherits`)
2. DROP TABLE
3. Próxima run recria automaticamente com FULL_RUN ou LOAD_ONLY

---

## Causa Raiz Unificada

> **Todos os P02, P11, P12, P13, P14 são manifestações da mesma causa raiz:**
> 
> `SIGKILL` (kill -9) no container PostgreSQL ou no container de ingestão durante uma **operação DDL**
> (`CREATE TABLE`, `ATTACH PARTITION`, `DROP INDEX`) deixa o catálogo `pg_catalog` em estado
> **parcialmente escrito** — sem chance de rollback porque DDL no PostgreSQL **não usa WAL transacional**
> da mesma forma que DML.
>
> Cada SIGKILL produz uma "camada" de corrupção diferente dependendo de **qual instrução SQL interna**
> do DDL foi interrompida:
>
> | Corrupção | Instrução interrompida |
> |-----------|----------------------|
> | `relispartition=true` sem `pg_inherits` | `UPDATE pg_class` executado, `INSERT pg_inherits` não |
> | `coninhcount>0, conparentid≠0` | constraints herdadas escritas, `pg_inherits` não |
> | `relispartition=true` no INDEX | index herdado marcado, parent link não criado |
> | Phantom OIDs em `pg_depend` | `INSERT pg_depend` executado, objeto nunca criado |
> | `pg_attribute` com 0 colunas | `INSERT pg_class` ok, `INSERT pg_attribute` nunca ocorreu |
> | WAL LSN corruption | buffer dirty em memória com LSN futuro por flush parcial do OS |
>
> A solução definitiva é **prevenir SIGKILLs durante DDL** (P01+P03). Enquanto isso não é resolvido,
> cada SIGKILL gera novos casos do mesmo tipo de corrupção, exigindo reparo manual.

---

## Resumo de Situação Atual (27/04/2026 ~16:00 UTC)

| # | Problema | Severidade | Status |
|---|----------|------------|--------|
| P01 | SIGKILL em TLD grande (OOM) | 🔴 CRÍTICA | ❌ Não resolvido |
| P02 | Corrupção catálogo PostgreSQL IDN TLDs | 🔴 CRÍTICA | 🟡 Em andamento (manual) |
| P03 | CI/CD interrompe runs | 🔴 ALTA | ❌ Não resolvido |
| P04 | INGESTION_TRIGGER_URLS não configurado | 🟡 MÉDIA | ❌ Não resolvido |
| P05 | last_run in-memory | 🟡 MÉDIA | ❌ Não resolvido |
| P06 | 74 TLDs com falha aguardando retry | 🟡 ALTA | ⏳ Pendente próxima run |
| P07 | CZDS nunca confirmado | 🟡 MÉDIA | ❓ Desconhecido |
| P08 | restart_policy condition:any | 🔵 BAIXA | ❌ Não resolvido |
| P09 | /run-now sem autenticação | 🔵 BAIXA | ❌ Não resolvido |
| P10 | Quoting PowerShell/SSH | 🔵 BAIXA (op.) | ✅ Contornado |
| P11 | Layer 4: PK INDEX relispartition | 🔴 ALTA | ✅ RESOLVIDO |
| P12 | WAL LSN corruption — checkpoint loop | 🔴 CRÍTICA | ✅ RESOLVIDO (VACUUM FULL) |
| P13 | Phantom OIDs em pg_depend | 🟡 ALTA | ✅ RESOLVIDO (wgbl6a, xkc2al3hye2a) |
| P14 | domain_xn__yfro4i67o: 0 colunas em pg_attribute | 🔴 CRÍTICA | 🔧 Fix em andamento |

**Estado das partições (27/04 ~16:00 UTC):**

| Partição | Status |
|----------|--------|
| `domain_com` | ✅ ATTACHED (concluído ~15:30) |
| `domain_removed_com` | ✅ ATTACHED |
| `domain_xn__qxa6a` | ✅ ATTACHED |
| `domain_removed_xn__qxa6a` | ✅ ATTACHED |
| `domain_xn__wgbh1c` | ✅ ATTACHED |
| `domain_removed_xn__wgbh1c` | ✅ ATTACHED (fix 4-layer ~16:00) |
| `domain_xn__wgbl6a` | ✅ DROPPED (será recriado na run) |
| `domain_removed_xn__wgbl6a` | ✅ ATTACHED (fix 4-layer ~16:00) |
| `domain_xn__xkc2dl3a5ee0h` | ✅ ATTACHED (fix 4-layer ~16:00) |
| `domain_removed_xn__xkc2dl3a5ee0h` | ✅ ATTACHED (fix 4-layer ~16:00) |
| `domain_xn__y9a3aq` | ✅ ATTACHED (fix 4-layer ~16:00) |
| `domain_removed_xn__y9a3aq` | ✅ ATTACHED (fix 4-layer ~16:00) |
| `domain_xn__xkc2al3hye2a` | ✅ DROPPED (recriado na run) |
| `domain_removed_xn__xkc2al3hye2a` | ✅ DROPPED |
| `domain_old` | ✅ DROPPED |
| `domain_xn__yfro4i67o` | 🔴 ATTACHED mas 0 colunas → precisa DROP+recreate |
