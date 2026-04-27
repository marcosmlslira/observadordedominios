# TODO 011 — Ingestão "Boring": estabilização estrutural do ciclo diário

> **Status:** proposta oficial — pronta para execução
> **Criado em:** 2026-04-27
> **Última revisão:** 2026-04-27 (refletida com validações por item + prova de resiliência + replicação em docker-stack-infra)
> **Autor:** Marcos Lira + Claude
> **Relaciona-se com:** [ADR-002](../../../docs/adr/002-ingestion-daily-tld-update-architecture.md), [TODO 010](../010/plan.md), [TODO 008](../008/plan.md), [TODO 009](../009/plan.md)
> **Repositórios afetados:**
> - `observadordedominios` (este repo) — código do worker, backend, frontend, migrations
> - `docker-stack-infra` — stacks Swarm, workflows de deploy, env/secrets

---

## 1. Objetivo

Tornar o ciclo de ingestão **simples, resiliente e diário**, com visibilidade auditável em `/admin/ingestion`.

A meta única que orienta todas as decisões abaixo:

> **Um SIGKILL no worker, em qualquer instante, não pode corromper o catálogo do PostgreSQL nem deixar o ciclo em estado irrecuperável sem intervenção manual.**

A resiliência não será prometida — será **provada** com cenários adversariais reproduzíveis (§12).

---

## 2. Diagnóstico (resumo do TODO 010)

Os 14 problemas catalogados em [`010/plan.md`](../010/plan.md) se reduzem a **4 falhas estruturais**:

| Falha | Sintomas em TODO 010 | Causa raiz |
|---|---|---|
| **F1. DDL no hot path** | P02, P11, P12, P13, P14 | `delta_loader` faz `DETACH` / `DROP INDEX` / `ATTACH` por run; SIGKILL no meio = catálogo parcialmente escrito |
| **F2. Sem garantia de sobrevivência** | P01, P03, P08 | Sem limite de memória no worker **nem no Postgres**; CI/CD do backend redeploya o worker; `restart_policy: any` |
| **F3. Estado operacional volátil** | P04, P05, P09 | `last_run` em memória; `INGESTION_TRIGGER_URLS` ausente; trigger sem auth |
| **F4. Sem visibilidade auditável** | P06, P07, complemento P05 | UI não consegue distinguir sucesso, `LOAD_ONLY` pendente, `no_snapshot`, `stale_recovered` |

Diagnóstico em uma frase:

> A ingestão é frágil porque mistura **carregar dados** com **manipular catálogo** no mesmo caminho crítico, e o ambiente onde ela roda **não dá garantia de sobrevivência** (nem o worker, nem o Postgres em si).

---

## 3. Princípio central

> **Ciclo diário = só DML. DDL = só em provisioning idempotente, fora do scheduler.**

Esse princípio é não-negociável neste plano. Toda decisão abaixo decorre dele.

---

## 4. Arquitetura alvo

```text
┌────────────────────────────────────────────────────────────────────┐
│                  PROVISIONING (raro, idempotente)                   │
│   ingestion/provisioning/provision_tld.py                           │
│   ─ pg_advisory_lock(hashtext('ingestion_provision'))               │
│   ─ CREATE TABLE IF NOT EXISTS domain_<tld>                        │
│   ─ ATTACH PARTITION (idempotente; SKIP se já anexada)              │
│   ─ CREATE TABLE IF NOT EXISTS staging_<tld>                       │
│   Roda no boot do worker e sob demanda (nunca dentro do ciclo).     │
└──────────────────────────────┬─────────────────────────────────────┘
                               │
                               ▼
┌────────────────────────────────────────────────────────────────────┐
│                       CICLO DIÁRIO (só DML)                         │
│   scheduler → orchestrator → loader                                 │
│   ─ resolve snapshot/delta no Databricks ou local                   │
│   ─ persiste artefato em R2 (marker)                                │
│   ─ TRUNCATE staging_<tld>            (DML, transacional)           │
│   ─ COPY delta → staging_<tld>        (DML, transacional)           │
│   ─ INSERT ... SELECT ... ON CONFLICT DO NOTHING → domain_<tld>     │
│   ─ TRUNCATE staging_<tld>            (cleanup)                     │
│   ─ registra ingestion_run + ingestion_cycle                        │
└────────────────────────────────────────────────────────────────────┘
```

Pontos-chave do desenho:

1. **`staging_<tld>` é permanente.** Criada uma vez, nunca dropada. `TRUNCATE` é DML — sobrevive a SIGKILL graciosamente.
2. **`domain_<tld>` mantém índices ativos durante o load.** Throughput cai um pouco, mas o load vira append puro (`INSERT ... ON CONFLICT DO NOTHING`).
3. **Provisioning roda separado do ciclo.** Script Python idempotente sob `pg_advisory_lock`. Pode ser interrompido e re-executado sem efeito colateral. **Não é migration Alembic** — Alembic deve ser determinístico, e a lista de TLDs muda em runtime.
4. **R2 continua sendo contrato operacional** (ADR-002 D4): permite `LOAD_ONLY` em retry sem rerodar Databricks.
5. **Memory limits explícitos** no `ingestion_worker` **e no `postgres`**. O segundo é o que falta hoje e é o que produz P12.

---

## 5. Plano de execução

Cinco sprints. Sprints 1–3 são sequenciais. Sprints 4–5 podem rodar em paralelo a partir do fim do Sprint 2.

> **Cada item tem um bloco `Validação:` — comandos concretos para confirmar que aquele trecho está funcional antes de avançar.**

---

### Sprint 1 — Estancar o sangramento (1–2 dias)

Objetivo: fazer o sistema parar de piorar. Janela de manutenção com worker desligado.

#### 1.1 — Backup `pg_basebackup` antes de manipulação

- **Onde:** servidor `158.69.211.109`
- **Como:** `ssh ubuntu@158.69.211.109 'docker exec observador_postgres.1.* pg_basebackup -D /tmp/backup-pre-011 -Ft -z -P'` + scp para off-site
- **Validação:**
  ```bash
  ssh ubuntu@158.69.211.109 'ls -lh /tmp/backup-pre-011/'
  # esperado: arquivos base.tar.gz e pg_wal.tar.gz com tamanho >0
  ```

#### 1.2 — Reparar `domain_xn__yfro4i67o` (P14 de TODO 010)

- **Onde:** psql remoto via SSH
- **Plano SQL:** ver [references.md §"Reparos pontuais Sprint 1.2"](references.md)
- **Validação:**
  ```sql
  SELECT count(*) FROM pg_attribute WHERE attrelid = 'domain'::regclass AND attnum > 0;
  -- esperado: número de colunas do domínio (não-zero)
  REFRESH MATERIALIZED VIEW tld_domain_count_mv;
  -- esperado: sucesso, sem erro de pg_attribute
  ```

#### 1.3 — `REINDEX SYSTEM obs` se necessário

- **Onde:** psql como superuser
- **Validação:**
  ```sql
  -- Antes:
  CHECKPOINT;  -- não deve mais loopar nos logs do postgres
  -- Depois:
  SELECT count(*) FROM pg_attribute WHERE attrelid::regclass::text LIKE 'domain_%';
  -- esperado: > 0 para todas as partições
  ```

#### 1.4 — Memory limits no `postgres` E no `ingestion_worker`

- **Onde:** [docker-stack-infra/stacks/observador.yml](C:\PROJETOS\docker-stack-infra\stacks\observador.yml)
- **Mudanças:**
  - `postgres`: `deploy.resources.limits.memory: 8G`, `reservations.memory: 4G`
  - `ingestion_worker`: `deploy.resources.limits.memory: 4G`, `reservations.memory: 2G`
- **Validação após deploy:**
  ```bash
  ssh ubuntu@158.69.211.109 'docker service inspect observador_postgres --format "{{.Spec.TaskTemplate.Resources.Limits.MemoryBytes}}"'
  # esperado: 8589934592 (8 GiB)
  ssh ubuntu@158.69.211.109 'docker service inspect observador_ingestion_worker --format "{{.Spec.TaskTemplate.Resources.Limits.MemoryBytes}}"'
  # esperado: 4294967296 (4 GiB)
  ssh ubuntu@158.69.211.109 'docker stats --no-stream | grep -E "postgres|ingestion"'
  # confirmar que LIMIT mostra os novos valores
  ```

#### 1.5 — `restart_policy: condition: on-failure` no `ingestion_worker`

- **Onde:** [docker-stack-infra/stacks/observador.yml](C:\PROJETOS\docker-stack-infra\stacks\observador.yml)
- **Validação:**
  ```bash
  ssh ubuntu@158.69.211.109 'docker service inspect observador_ingestion_worker --format "{{.Spec.TaskTemplate.RestartPolicy.Condition}}"'
  # esperado: on-failure
  ```

#### 1.6 — `INGESTION_TRIGGER_URLS` no env do backend

- **Onde:** [docker-stack-infra/stacks/observador.yml](C:\PROJETOS\docker-stack-infra\stacks\observador.yml) (env do `backend`)
- **Valor:** `INGESTION_TRIGGER_URLS=http://ingestion_worker:8080`
- **Validação:**
  ```bash
  ssh ubuntu@158.69.211.109 'docker exec $(docker ps -q -f name=observador_backend) env | grep INGESTION_TRIGGER_URLS'
  # esperado: INGESTION_TRIGGER_URLS=http://ingestion_worker:8080
  curl -X POST -H "Authorization: Bearer $TOKEN" https://api.observadordedominios.com.br/v1/ingestion/trigger/openintel
  # esperado: HTTP 200/202, log do worker mostra recebimento
  ```

#### 1.7 — Stack isolado para ingestão (`observador-ingestion.yml`)

- **Onde:** [docker-stack-infra/stacks/observador-ingestion.yml.draft](C:\PROJETOS\docker-stack-infra\stacks\observador-ingestion.yml.draft) — criado já, ainda inativo
- **Quando ativar:** após Sprint 1.4–1.6 estarem em produção e estáveis por 24h
- **Como ativar:**
  1. Renomear `.draft` → `.yml` em PR no docker-stack-infra
  2. Editar `observador.yml` para remover bloco `ingestion_worker`
  3. Editar `.github/workflows/deploy.yml` para tratar `observador-ingestion` como stack manual (ver 1.8)
  4. PR + merge faz deploy de **dois stacks**, com `--prune` movendo o serviço sem downtime
- **Validação:**
  ```bash
  ssh ubuntu@158.69.211.109 'docker stack ls | grep observador'
  # esperado: 2 linhas — observador, observador-ingestion
  ssh ubuntu@158.69.211.109 'docker stack services observador-ingestion'
  # esperado: ingestion_worker rodando, replicas 1/1
  ssh ubuntu@158.69.211.109 'docker stack services observador | grep ingestion'
  # esperado: vazio
  ```

#### 1.8 — CI/CD do backend deixa de tocar stack de ingestão

- **Onde:** [docker-stack-infra/.github/workflows/deploy.yml](C:\PROJETOS\docker-stack-infra\.github\workflows\deploy.yml)
- **Mudança:** filtro no loop `for stack_file in stacks/*.yml` — pular `observador-ingestion.yml` em `push` automático; só permitir via `workflow_dispatch` ou `repository_dispatch` com `client_payload.stack=observador-ingestion`
- **Workflow novo:** [docker-stack-infra/.github/workflows/deploy-ingestion.yml](C:\PROJETOS\docker-stack-infra\.github\workflows\deploy-ingestion.yml) — manual, com checagem de "ciclo idle" antes de deployar
- **Validação:**
  ```bash
  # Cenário: push de mudança trivial no backend
  git -C C:\PROJETOS\observadordedominios commit --allow-empty -m "test: deploy isolation" && git push
  # CI roda; no servidor:
  ssh ubuntu@158.69.211.109 'docker service ps observador-ingestion_ingestion_worker --format "{{.CreatedAt}}" | head -1'
  # esperado: timestamp ANTERIOR ao push (não foi tocado)
  ```

**Critério de saída do Sprint 1:**
- [ ] `pg_basebackup` armazenado off-site
- [ ] `domain_xn__yfro4i67o` reparada; `REFRESH MATERIALIZED VIEW tld_domain_count_mv` funciona
- [ ] Memory limits ativos e visíveis em `docker stats`
- [ ] `restart_policy: on-failure` ativo no worker
- [ ] `/admin/ingestion` consegue disparar trigger pela UI (botão)
- [ ] Stack `observador-ingestion` rodando isolado (1.7)
- [ ] `git push` no backend **não** reinicia o `ingestion_worker` (1.8)

---

### Sprint 2 — Eliminar DDL do hot path (3–4 dias)

Objetivo: tornar o loader incapaz de corromper o catálogo, mesmo sob SIGKILL.

#### 2.1 — Provisioning script idempotente

- **Arquivo novo:** `ingestion/provisioning/provision_tld.py`
- **Comportamento:**
  - `pg_advisory_lock(hashtext('ingestion_provision'))` no início
  - Lê `ingestion_tld_policy` para descobrir TLDs ativos
  - Para cada TLD: `CREATE TABLE IF NOT EXISTS domain_<tld>`, `ATTACH PARTITION` se não anexada, `CREATE TABLE IF NOT EXISTS staging_<tld> (LIKE domain_<tld> INCLUDING DEFAULTS)`
  - Mesma coisa para `domain_removed_<tld>` e `staging_removed_<tld>`
  - Cada operação envolvida em `SAVEPOINT` para que falha em um TLD não cancele os outros
  - `pg_advisory_unlock` no final
- **Validação:**
  ```bash
  # 1. Roda duas vezes seguidas — segunda deve ser no-op
  docker exec observador_ingestion_worker python -m ingestion.provisioning.provision_tld
  docker exec observador_ingestion_worker python -m ingestion.provisioning.provision_tld
  # esperado: segunda execução loga "0 changes"

  # 2. Em paralelo (advisory lock previne concorrência)
  docker exec observador_ingestion_worker python -m ingestion.provisioning.provision_tld &
  docker exec observador_ingestion_worker python -m ingestion.provisioning.provision_tld &
  wait
  # esperado: uma sucede, outra espera ou aborta limpamente; nenhuma corrupção

  # 3. Tabelas existem
  psql -c "\dt staging_*"
  # esperado: uma staging_<tld> por TLD ativo
  ```

#### 2.2 — Boot hook no scheduler chama provisioning

- **Arquivo:** `ingestion/scheduler.py`
- **Mudança:** chamar `provision_tld` no startup, ANTES de aceitar requests em `/run-now`
- **Validação:**
  ```bash
  docker service update --force observador-ingestion_ingestion_worker
  docker logs $(docker ps -q -f name=ingestion_worker) | grep provision
  # esperado: "Provisioning N tlds... done."
  ```

#### 2.3 — Refactor `delta_loader.py`: remover DDL

- **Arquivo:** `ingestion/ingestion/loader/delta_loader.py`
- **Remover:** todas as chamadas a `ALTER TABLE ... DETACH PARTITION`, `ALTER TABLE ... ATTACH PARTITION`, `DROP INDEX`, `CREATE INDEX`
- **Adicionar:** novo caminho com staging
- **Validação estática:**
  ```bash
  grep -nE "DETACH PARTITION|ATTACH PARTITION|DROP INDEX|CREATE INDEX" ingestion/ingestion/loader/delta_loader.py
  # esperado: 0 matches
  ```
- **Validação funcional:** ver 2.5

#### 2.4 — Novo caminho de load via staging

- **Sequência por TLD:**
  ```sql
  BEGIN;
  TRUNCATE staging_<tld>;
  COPY staging_<tld> FROM stdin WITH (FORMAT BINARY);
  -- (parquet → arrow → COPY binary stream)
  INSERT INTO domain_<tld> (...) SELECT ... FROM staging_<tld>
    ON CONFLICT (domain_name) DO NOTHING;
  TRUNCATE staging_<tld>;
  COMMIT;
  ```
- **Mesma estratégia para `domain_removed_<tld>`** com `staging_removed_<tld>`
- **Validação:**
  ```bash
  # Disparar run em TLD pequeno (ex: ee)
  curl -X POST -H "X-Ingestion-Token: $T" http://ingestion_worker:8080/run-now -d '{"tld":"ee"}'
  # Verificar contagem
  psql -c "SELECT count(*) FROM domain_ee;"
  # esperado: aumenta após o run; staging_ee retorna 0 após COMMIT
  psql -c "SELECT count(*) FROM staging_ee;"
  # esperado: 0
  ```

#### 2.5 — Streaming de TLDs grandes em chunks

- **Onde:** `delta_loader.py`, função `load_delta`
- **Como:** `pyarrow.RecordBatchReader` com `batch_size=100_000`; cada batch faz `COPY` para staging; insert final em uma transação só
- **Validação:**
  ```bash
  # Run em .com (TLD massivo)
  curl -X POST -H "X-Ingestion-Token: $T" http://ingestion_worker:8080/run-now -d '{"tld":"com"}'
  docker stats --no-stream | grep ingestion
  # esperado: MEM USAGE estável < 3 GiB durante o load (não cresce linearmente com número de domínios)
  ```

#### 2.6 — Handler `SIGTERM` no scheduler (graceful shutdown)

- **Arquivo:** `ingestion/scheduler.py`
- **Comportamento:**
  - Recebe SIGTERM → marca flag `shutting_down=True`
  - TLD em curso termina a transação atual
  - Não inicia novo TLD
  - Persiste estado parcial em `ingestion_cycle` com `status=interrupted`
  - Sai com exit 0 antes de `stop_grace_period: 6h` (já configurado)
- **Validação:**
  ```bash
  # Disparar ciclo
  curl -X POST -H "X-Ingestion-Token: $T" http://ingestion_worker:8080/run-now
  sleep 30
  # Mandar SIGTERM
  docker exec observador_ingestion_worker.1.* kill -TERM 1
  # Verificar exit limpo
  docker logs $(docker ps -aq -f name=ingestion_worker) | tail -50 | grep -i "graceful\|shutdown\|interrupted"
  # esperado: log "graceful shutdown completed", exit code 0
  psql -c "SELECT cycle_id, status FROM ingestion_cycle ORDER BY started_at DESC LIMIT 1;"
  # esperado: status = 'interrupted' (não 'running' nem 'failed')
  ```

#### 2.7 — Remover dependências de DDL residuais

- **Como:** `grep -rE "DETACH|ATTACH|DROP INDEX" ingestion/` — só pode aparecer dentro de `ingestion/provisioning/`
- **Validação:**
  ```bash
  grep -rE "DETACH PARTITION|ATTACH PARTITION|DROP INDEX|CREATE INDEX" ingestion/ \
    | grep -v "ingestion/provisioning/"
  # esperado: 0 matches
  ```

**Critério de saída do Sprint 2 — TESTE DE FOGO:**

> Reproduza este cenário 3 vezes seguidas. Tem que passar nas 3.

1. Disparar run em `.com` (TLD massivo)
2. Aguardar 60s (load em curso)
3. `docker exec observador_ingestion_worker.1.* kill -9 1`
4. Aguardar restart automático do swarm
5. Disparar nova run em `.com`
6. **Esperado:** run completa com sucesso (modo `LOAD_ONLY` reaproveita R2); `psql -c "SELECT count(*) FROM domain_com"` cresce; **zero corrupção** (nenhum erro `pg_attribute`/`pg_inherits`/`is already a partition`/`tuple concurrently deleted`).

Se passar 3/3, Sprint 2 está done.

---

### Sprint 3 — Estado e visibilidade (2–3 dias)

Objetivo: `/admin/ingestion` informa a verdade mesmo após restarts.

#### 3.1 — Migration `ingestion_cycle`

- **Arquivo:** `backend/alembic/versions/xxxx_ingestion_cycle.py`
- **Schema:**
  ```sql
  CREATE TABLE ingestion_cycle (
    cycle_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running','succeeded','failed','interrupted')),
    triggered_by TEXT NOT NULL CHECK (triggered_by IN ('cron','manual','api')),
    tld_total INT,
    tld_success INT DEFAULT 0,
    tld_failed INT DEFAULT 0,
    tld_skipped INT DEFAULT 0,
    tld_load_only INT DEFAULT 0,
    last_heartbeat_at TIMESTAMPTZ
  );
  CREATE INDEX idx_ingestion_cycle_started_at ON ingestion_cycle(started_at DESC);
  CREATE INDEX idx_ingestion_cycle_status ON ingestion_cycle(status) WHERE status='running';
  ```
- **Validação:**
  ```bash
  alembic upgrade head
  psql -c "\d ingestion_cycle"
  # esperado: tabela existe com colunas corretas
  ```

#### 3.2 — `run_recorder` registra ciclo agregado

- **Arquivo:** `ingestion/ingestion/observability/run_recorder.py`
- **API:** `open_cycle(triggered_by) -> cycle_id`, `update_cycle(cycle_id, **counts)`, `close_cycle(cycle_id, status)`, `heartbeat(cycle_id)`
- **Validação:**
  ```sql
  -- Após uma run completa:
  SELECT cycle_id, status, tld_total, tld_success, tld_failed, finished_at - started_at AS duration
  FROM ingestion_cycle ORDER BY started_at DESC LIMIT 1;
  -- esperado: linha com status=succeeded, contadores não-nulos, duration coerente
  ```

#### 3.3 — `/health` lê do banco (sem `_last_run_info`)

- **Arquivo:** `ingestion/scheduler.py`
- **Comportamento:** endpoint `/health` faz `SELECT ... FROM ingestion_cycle ORDER BY started_at DESC LIMIT 1` + checagem de heartbeat
- **Validação:**
  ```bash
  # Restart do worker
  docker service update --force observador-ingestion_ingestion_worker
  sleep 30
  curl http://ingestion_worker:8080/health | jq .last_cycle
  # esperado: estado do último ciclo (não vazio mesmo após restart)
  ```

#### 3.4 — View `tld_health_v`

- **Arquivo:** `backend/alembic/versions/xxxx_tld_health_view.py`
- **Schema:**
  ```sql
  CREATE VIEW tld_health_v AS
  SELECT DISTINCT ON (source, tld)
    source, tld, status AS last_status, reason_code AS last_reason_code,
    started_at AS last_attempt_at,
    -- janela: último sucesso/falha (subquery)
    ...
  FROM ingestion_run
  ORDER BY source, tld, started_at DESC;
  ```
- **Validação:**
  ```sql
  SELECT count(*), count(*) FILTER (WHERE last_status='succeeded') FROM tld_health_v;
  -- esperado: total = TLDs ativos; sucesso > 0
  ```

#### 3.5 — Endpoints `/cycles` e `/tlds/health`

- **Arquivo:** `backend/app/api/v1/routers/ingestion.py`
- **Endpoints:**
  - `GET /v1/ingestion/cycles?limit=30` — últimos ciclos
  - `GET /v1/ingestion/tlds/health` — view `tld_health_v`
- **Validação:**
  ```bash
  curl -H "Authorization: Bearer $JWT" https://api.observadordedominios.com.br/v1/ingestion/cycles?limit=5 | jq '. | length'
  # esperado: 5 (ou menos se ainda não há tantos)
  curl -H "Authorization: Bearer $JWT" https://api.observadordedominios.com.br/v1/ingestion/tlds/health | jq '. | length'
  # esperado: número de TLDs ativos
  ```

#### 3.6 — Cards de UI em `/admin/ingestion`

- **Arquivo:** `frontend/app/admin/ingestion/`
- **Cards:** "Ciclo atual", "Hoje por TLD", "Saúde por TLD", "Incidentes recentes"
- **Polling:** SWR com `refreshInterval: 10000`
- **Validação manual:**
  - Abrir `/admin/ingestion` e ver os 4 cards populados
  - Disparar run via botão e ver o card "Ciclo atual" virar `running`
  - Após fim, ver `succeeded` e contadores corretos

#### 3.7 — Auth `X-Ingestion-Token` no `/run-now`

- **Onde:** `ingestion/scheduler.py` + secret do GitHub `INGESTION_TRIGGER_TOKEN`
- **Validação:**
  ```bash
  curl -X POST http://ingestion_worker:8080/run-now
  # esperado: HTTP 401
  curl -X POST -H "X-Ingestion-Token: $T" http://ingestion_worker:8080/run-now
  # esperado: HTTP 202
  ```

---

### Sprint 4 — Validação CZDS + Databricks-first (paralelo, após Sprint 2)

| # | Ação | Validação |
|---|---|---|
| 4.1 | Rodar ciclo completo, observar fase CZDS | `SELECT count(*) FROM ingestion_run WHERE source='czds' AND snapshot_date=CURRENT_DATE` > 0 |
| 4.2 | Validar credenciais CZDS em produção | `docker exec ingestion_worker python -c "from ingestion.fontes.czds import auth; print(auth.token())"` retorna token |
| 4.3 | Migrar TLDs gigantes para `databricks_only` | `SELECT mode FROM ingestion_tld_policy WHERE tld IN ('com','de','net','ch')` retorna `databricks_only` |
| 4.4 | Documentar threshold em `ingestion_tld_policy` | `docs/runbooks/ingestion-tld-policy.md` existe |

---

### Sprint 5 — Hardening contínuo (paralelo, após Sprint 2)

| # | Ação | Validação |
|---|---|---|
| 5.1 | Log de memória por TLD/chunk | `grep "rss_mb" docker logs ingestion_worker` retorna entradas |
| 5.2 | Stale heartbeat watchdog (10 min) | Simular: `UPDATE ingestion_run SET status='running', last_heartbeat_at=now()-interval '15 min' WHERE id=...`; observar reaper marcar como `failed` com `reason_code='stale_heartbeat'` em ≤ 60s |
| 5.3 | Métrica `ingestion_cycle_duration_seconds` | Endpoint `/metrics` expõe a métrica em formato Prometheus |
| 5.4 | Runbook em `docs/runbooks/ingestion.md` | Arquivo existe; cobre 5 incidentes mais comuns |

---

## 6. As 4 perguntas canônicas que `/admin/ingestion` precisa responder

Todas com 1 query indexada, sem WebSocket — polling 10s.

| Pergunta | Fonte | Esboço de query |
|---|---|---|
| **"Está rodando agora?"** | `ingestion_cycle` | `WHERE status='running' ORDER BY started_at DESC LIMIT 1` + checagem de heartbeat |
| **"O que aconteceu hoje por TLD?"** | `ingestion_run` | `WHERE snapshot_date = CURRENT_DATE` agrupado por `(source, tld, status)` |
| **"Saúde funcional por TLD"** | view `tld_health_v` | `SELECT *` direto |
| **"Incidentes auditáveis"** | `ingestion_run` | `WHERE status='failed' ORDER BY started_at DESC LIMIT 100` com `reason_code, message` |

---

## 7. O que este plano explicitamente NÃO faz

Para manter o escopo controlado:

- **Não reescreve o orquestrador.** O `pipeline.py` continua como está, só perde a parte de DDL.
- **Não migra schema de `domain`/`domain_removed`.** O ADR-001 já definiu, e está em produção.
- **Não muda fontes (CZDS/OpenINTEL/CertStream).** Só muda como o worker carrega os deltas no Postgres.
- **Não introduz novos serviços externos.** Mantém Postgres, R2, Databricks como já são.
- **Não muda o frontend** além dos cards de `/admin/ingestion` em Sprint 3.

---

## 8. Critérios de aceite arquiteturais

Reaproveita os 5 do ADR-002 e adiciona 3 operacionais:

**Do ADR-002 (mantidos):**

1. nenhum TLD precisa de `UPDATE` recorrente em `domain` para ser considerado atualizado
2. toda atualização diária gera, ou reaproveita, artefato identificável por `source + tld + snapshot_date`
3. uma falha de carga local pode ser recuperada sem recalcular o snapshot remoto
4. remoções de domínio ficam registradas em `domain_removed`
5. observabilidade explica por TLD se houve sucesso, falha, skip, ausência de snapshot ou recuperação

**Novos (deste plano):**

6. **um SIGKILL no worker em qualquer instante NUNCA corrompe catálogo do Postgres** — ciclo seguinte completa sem intervenção manual (provado em §12)
7. **deploy do backend NUNCA mata o worker em meio a um ciclo** — stacks isolados, deploy de ingestão exige ação explícita (provado em §12)
8. **após restart do worker, `/admin/ingestion` mostra estado correto imediatamente** — sem precisar esperar a próxima run (provado em §12)

---

## 9. Riscos e mitigações

| Risco | Probabilidade | Mitigação |
|---|---|---|
| Throughput de load cai com índices ativos | Média | Staging table + `INSERT ... SELECT` mantém custo baixo; medir e ajustar para top-10 TLDs |
| Migration Alembic para `ingestion_cycle` falha em produção | Baixa | Migration testada em dev primeiro; rollback simples (DROP TABLE) |
| Refactor do `delta_loader` introduz regressão | Alta | Deploy em janela de baixo tráfego; rollback = imagem anterior; teste de fogo (Sprint 2 critério) |
| Stack isolado da ingestão complica deploy | Baixa | Documentar comando único; CI/CD tem job manual com aprovação |
| `staging_<tld>` ocupa espaço em disco | Baixa | Sempre vazia entre runs (`TRUNCATE`); custo desprezível |
| Postgres com `limits.memory: 8G` fica limitado em queries pesadas | Média | Monitorar `shared_buffers`, ajustar valor após observação; 8G é ponto de partida — pode subir se necessário |
| Provisioning idempotente roda concorrente em scaling | Baixa | Advisory lock previne (testado em 2.1 validação) |

---

## 10. Encerramento de TODO 010

Quando este plano fechar (todos os critérios §8 verdes + §12 verde), TODO 010 vai a `done` com nota:
> "Sintomas catalogados em 010 foram resolvidos estruturalmente em 011. Mantido como referência forense."

---

## 11. Decisões pendentes do owner

- [ ] Aprovar plano e iniciar Sprint 1
- [ ] Confirmar janela de manutenção para reparo final P14 (Sprint 1.2)
- [ ] Confirmar separação de stacks (1.7) — implica criar `stack.ingestion.yml` e ajustar workflow
- [ ] Confirmar valores de `limits.memory` (Postgres 8G, worker 4G) — depende de RAM disponível no servidor
- [ ] Confirmar token `INGESTION_TRIGGER_TOKEN` (gerar e salvar como secret no GitHub)

---

## 12. Prova de resiliência — cenários adversariais

Cada cenário tem **passos** e **critério objetivo de pass/fail**. O plano só está concluído quando todos os 8 cenários passam.

> **Princípio:** se um cenário não pode ser executado porque depende de produção, ele é executado em staging com cópia de dados sintéticos representativa do volume.

### C1 — SIGKILL no worker durante load de TLD massivo

- **Cenário:** ciclo em curso, processando `.com`. `kill -9` no worker.
- **Passos:** disparar run; aguardar 60s; `kill -9`; aguardar restart; disparar nova run.
- **Pass se:**
  - Restart automático ≤ 60s
  - Nova run completa sucesso
  - `psql -c "\d domain"` lista todas as partições corretamente (sem `relispartition` inconsistente)
  - Nenhum erro `is already a partition`, `tuple concurrently deleted`, `pg_attribute is missing` no log do Postgres

### C2 — SIGKILL no Postgres durante load

- **Cenário:** load em curso; `kill -9` no container do Postgres.
- **Passos:** análogo ao C1, mas matando o `postgres`.
- **Pass se:**
  - Postgres faz crash recovery automático em ≤ 2 min
  - Worker detecta erro de conexão e marca run atual como `failed` com `reason_code='db_disconnected'`
  - Próxima run usa `LOAD_ONLY` (R2 marker presente) e completa
  - `CHECKPOINT;` não loopa nos logs

### C3 — Deploy do backend durante ciclo de ingestão

- **Cenário:** ciclo em curso; `git push` no backend.
- **Passos:** disparar run; aguardar 60s; `git push origin main` no backend; observar.
- **Pass se:**
  - `ingestion_worker` **não** reinicia
  - `docker service ps observador-ingestion_ingestion_worker --format "{{.CreatedAt}}"` permanece igual antes e depois
  - Ciclo completa sem ser afetado

### C4 — Deploy do worker durante ciclo

- **Cenário:** ciclo em curso; deploy intencional do worker via `workflow_dispatch`.
- **Passos:** disparar run; aguardar 60s; rodar `gh workflow run deploy-ingestion.yml`.
- **Pass se:**
  - Workflow detecta ciclo em curso e **rejeita o deploy** com mensagem clara
  - OU (com flag `--force`) graceful: SIGTERM → TLD atual termina → ciclo é marcado `interrupted` → nova versão sobe → próxima run completa em `LOAD_ONLY`

### C5 — OOM do worker em TLD massivo

- **Cenário:** worker tenta carregar `.com` em memória.
- **Passos:** disparar run em `.com`.
- **Pass se:**
  - `docker stats` mostra MEM USAGE estável < 3 GiB (não cresce linearmente com volume)
  - Container não é OOM-killed
  - Run completa

### C6 — Restart limpo do worker (`docker service update --force`)

- **Cenário:** restart sem ciclo em curso.
- **Passos:** restart; abrir `/admin/ingestion`.
- **Pass se:**
  - `/admin/ingestion` mostra estado do **último** ciclo (não vazio)
  - Card "Está rodando agora?" mostra "não rodando"
  - Nenhum tempo de espera para a UI ficar utilizável

### C7 — Reexecução após falha em LOAD_ONLY

- **Cenário:** R2 marker existe; PG load falhou na run anterior.
- **Passos:** simular falha (matar worker durante INSERT); disparar nova run.
- **Pass se:**
  - Nova run detecta R2 marker → entra em `LOAD_ONLY`
  - Não rerodada Databricks (verificar logs: nenhuma chamada para Databricks API)
  - Carga completa em ≤ 50% do tempo de FULL_RUN

### C8 — Provisioning concorrente

- **Cenário:** dois workers chamando `provision_tld` simultaneamente.
- **Passos:** abrir 2 shells; rodar `provision_tld` em cada um ao mesmo tempo.
- **Pass se:**
  - Um sucede; outro espera ou sai limpo com mensagem "lock held by other process"
  - Nenhum erro de catálogo
  - Estado final consistente (mesmo número de tabelas após e antes)

---

## 13. O que ainda pode falhar (honestidade)

Mesmo com tudo isso, há cenários que este plano **não cobre**:

1. **Falha do servidor inteiro** (host OVH cai, disco corrompe). Mitigação parcial: backup `pg_basebackup` automático (não está no escopo deste plano — ver TODO separado).
2. **Bug em `pyarrow` ou `psycopg`**. Mitigação: fixação de versão + canary em staging.
3. **Mudança de schema das fontes** (CZDS muda formato do zone file). Mitigação: parser tolerante + alarme.
4. **Crescimento descontrolado de `ingestion_run`** (milhões de linhas em 1 ano). Mitigação futura: particionar por mês ou rotacionar.
5. **Disponibilidade do Databricks** (workspace ou job indisponível). Mitigação: retry com backoff + fallback para caminho local em TLDs onde isso é viável.

Esses ficam fora do escopo de 011, mas devem virar TODOs próprios.
