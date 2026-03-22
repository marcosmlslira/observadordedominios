# Refinamento Técnico: Ingestão CZDS Zone Files

**Data:** 2026-02-28
**Refinador:** Tech Refiner Agent
**Status:** 🟢 Decisões de arquitetura aprovadas

---

## 1. Entendimento

Implementar uma fonte de ingestão de dados globais de domínios via CZDS (ICANN) que:

1. baixa zone files completas por TLD autorizado,
2. armazena o artefato raw `.zone.gz` em storage S3,
3. extrai e normaliza os domínios,
4. aplica delta real no PostgreSQL (novos, mantidos, removidos),
5. mantém rastreabilidade por execução.

No contexto deste repositório, isso pertence ao domínio `domain_intelligence_global` e deve ser implementado no backend FastAPI existente (arquitetura em camadas), com execução agendada e gatilho manual por endpoint.

---

## 2. Decisões aprovadas

- **[P1] Escopo inicial de TLDs:** iniciar pelos mais leves (`.net`, `.org`, `.info`), sem `.com` na fase 1.
- **[P2] Estratégia de remoção:** **soft delete** com `deleted_at`.
- **[P3] Topologia de execução:** **worker dedicado** no Swarm, separado da API.
- **[P4] Storage em desenvolvimento:** **MinIO** em dev; S3 compatível em produção.

### Gestão fácil de TLDs habilitados

Para facilitar operação sem editar código:

1. criar tabela de configuração `czds_tld_policy`;
2. scheduler lê TLDs ativos dessa tabela a cada ciclo;
3. endpoint administrativo permite habilitar/desabilitar TLD;
4. `CZDS_ENABLED_TLDS` fica como fallback de bootstrap (ambiente vazio).

Campos mínimos da política:

- `tld` (PK)
- `is_enabled` (bool)
- `priority` (int)
- `cooldown_hours` (int, default 24)
- `notes` (text, opcional)
- `updated_at`

---

## 3. Mapa Técnico

### Dados envolvidos

| Entidade | Operação | Observação |
|----------|----------|------------|
| `domain` | UPSERT | Registro canônico global (`name`, `tld`, `first_seen_at`, `last_seen_at`, `status`) |
| `domain_observation` | INSERT | Evento append-only por execução/fonte |
| `ingestion_run` | INSERT/UPDATE | Controle de execução, volume, duração, status e erro |
| `ingestion_checkpoint` | UPSERT | Último sync bem-sucedido por fonte/TLD |
| `zone_file_artifact` | INSERT | Metadado do raw salvo no S3 (bucket, key, etag, size, hash) |

### Componentes impactados

- [x] Banco de dados — novas tabelas + índices + migrações Alembic
- [x] API — endpoint manual de trigger e endpoint de status
- [x] Autenticação/Autorização — endpoint de trigger restrito (admin/internal)
- [x] Serviços externos — CZDS API + S3
- [ ] Frontend — não obrigatório para fase de ingestão
- [x] Jobs/Workers — scheduler diário + execução por TLD
- [x] Cache — não necessário no MVP
- [x] Logs/Monitoramento — obrigatório (run_id, tld, counters, erros)

### Fluxo de dados

```text
[Scheduler/API Trigger] → [Use case sync_tld] → [CZDS download] → [S3 raw save]
→ [Parse stream zone file] → [Staging delta no Postgres]
→ [Apply upsert + removidos] → [Persist run metrics/checkpoint] → [Resposta/Logs]
```

---

## 4. Viabilidade e Riscos

### Viabilidade

| Dimensão | Avaliação | Observação |
|----------|-----------|------------|
| Complexidade técnica | Média/Alta | Pipeline de alto volume + delta consistente |
| Incerteza de implementação | Média | depende de TLDs e estratégia de execução |
| Impacto em sistema existente | Médio | adiciona domínio global, storage e worker |
| Estimativa aproximada | 8–15 dias úteis | faseada por milestones |

### Riscos identificados

- 🔴 **Volume extremo em `.com`** → pode degradar I/O e banco.  
  **Mitigação:** fase 1 sem `.com`; particionamento, índices e batch tuning antes.

- 🔴 **Scheduler duplicado em múltiplas réplicas** → duas ingestões simultâneas do mesmo TLD.  
  **Mitigação:** worker único dedicado + lock distribuído por TLD (`pg_try_advisory_lock`).

- 🟡 **Delta incorreto por falha parcial** → marcação de deletados indevida.  
  **Mitigação:** deletar somente após run `SUCCESS`, com `seen_in_run_id` consistente.

- 🟡 **Limite operacional CZDS (1 download/24h por zona)** → risco de bloqueio por retries agressivos.  
  **Mitigação:** política de retry com backoff + guardrail por TLD/24h.

- 🟢 **Custos de storage S3** com retenção total.  
  **Mitigação:** lifecycle policy por ambiente (ex.: 90/180 dias no dev/staging).

---

## 5. Caminhos Possíveis

### Caminho A — Ingestão no próprio `obs_backend`
**Descrição:** APScheduler e jobs dentro do mesmo processo FastAPI.
**Prós:** menos serviços, setup inicial rápido.
**Contras:** risco de acoplamento API/job, concorrência com tráfego HTTP, duplicidade em escala horizontal.
**Quando escolher:** ambiente único, baixo volume, etapa exploratória.

### Caminho B — Worker dedicado de ingestão (recomendado)
**Descrição:** manter API no `obs_backend`; criar processo/serviço `obs_czds_ingestor` com scheduler e use cases de ingestão.
**Prós:** isolamento operacional, controle de concorrência, escalabilidade mais previsível.
**Contras:** aumenta complexidade de stack/deploy e observabilidade.
**Quando escolher:** produção e qualquer cenário com múltiplos TLDs ou volume alto.

### ✅ Recomendação

Adotar **Caminho B**. Mantém conformidade com arquitetura em camadas, reduz risco de dupla execução no Swarm e prepara evolução para filas/processamento paralelo.

---

## 6. Especificação Técnica

### 6.1 Backend (arquitetura alinhada ao projeto)

Estrutura recomendada (incremental) em `backend/app`:

```text
app/
  api/v1/routers/czds_ingestion.py
  services/use_cases/
    sync_czds_tld.py
    apply_zone_delta.py
  repositories/sqlalchemy/
    domain_repository.py
    ingestion_run_repository.py
    zone_artifact_repository.py
  infra/external/
    czds_client.py
    s3_storage.py
  infra/db/
    session.py
  models/
    domain.py
    domain_observation.py
    ingestion_run.py
    ingestion_checkpoint.py
    zone_file_artifact.py
  schemas/
    czds_ingestion.py
```

> Regra: rota HTTP apenas dispara/consulta status; regras e transações ficam em serviços; repositórios sem `commit`.

### 6.2 Endpoints

```http
POST /v1/czds/trigger-sync
Body: {
  "tld": "net",
  "force": false
}
Response 202: {
  "run_id": "uuid",
  "status": "queued|running"
}
Response 409: {
  "error": "sync already running for tld"
}

GET /v1/czds/runs/{run_id}
Response 200: {
  "run_id": "uuid",
  "tld": "net",
  "status": "success|failed|running",
  "started_at": "...",
  "finished_at": "...",
  "domains_seen": 0,
  "domains_inserted": 0,
  "domains_deleted": 0,
  "artifact_key": "zones/net/2026-02-28/net.zone.gz"
}
```

### 6.3 Regras de negócio

- Regra 1: só processar TLD autorizado para a credencial CZDS.
- Regra 2: respeitar janela de 24h por TLD, exceto `force=true` para incidente controlado.
- Regra 3: salvar raw no S3 antes de aplicar delta no banco.
- Regra 4: delta só é finalizado se parsing/extracão terminar sem erro.
- Regra 5: marcar removidos apenas quando `run.status = SUCCESS`.
- Regra 6: operações idempotentes por `run_id` + hash do artefato.

### 6.4 Validações

- `tld`: obrigatório, min 2 max 24, regex `^[a-z0-9-]+$`, lowercase.
- `force`: opcional (`false` default).
- `CZDS_*`, `AWS_*`, `POSTGRES_*`: obrigatórios em runtime do worker.

### 6.5 Banco de dados (modelo mínimo)

Domínio: `domain_intelligence_global`  
Subdomínio: `czds_ingestion`

Tabelas propostas:

1. `domain` (Entity global)
   - `id UUID PK`
   - `name CITEXT UNIQUE NOT NULL`
   - `tld VARCHAR(24) NOT NULL`
   - `status VARCHAR(16) NOT NULL DEFAULT 'active'` (`active|deleted`)
   - `first_seen_at TIMESTAMPTZ NOT NULL`
   - `last_seen_at TIMESTAMPTZ NOT NULL`
   - `deleted_at TIMESTAMPTZ NULL`
   - `created_at`, `updated_at`

2. `domain_observation` (Event append-only)
   - `id UUID PK`
   - `domain_id UUID FK -> domain(id) ON DELETE CASCADE`
   - `source VARCHAR(32) NOT NULL` (`czds`)
   - `tld VARCHAR(24) NOT NULL`
   - `observed_at TIMESTAMPTZ NOT NULL`
   - `ingestion_run_id UUID FK`
   - UNIQUE natural para idempotência (`domain_id`,`source`,`observed_at`,`ingestion_run_id`)

3. `ingestion_run` (Entity operacional)
   - `id UUID PK`
   - `source VARCHAR(32) NOT NULL` (`czds`)
   - `tld VARCHAR(24) NOT NULL`
   - `status VARCHAR(16) NOT NULL` (`running|success|failed`)
   - `started_at`, `finished_at`
   - `artifact_id UUID NULL FK -> zone_file_artifact(id)`
   - `domains_seen BIGINT DEFAULT 0`
   - `domains_inserted BIGINT DEFAULT 0`
   - `domains_reactivated BIGINT DEFAULT 0`
   - `domains_deleted BIGINT DEFAULT 0`
   - `error_message TEXT NULL`

4. `ingestion_checkpoint` (Snapshot por fonte/TLD)
   - `source VARCHAR(32)`
   - `tld VARCHAR(24)`
   - `last_successful_run_id UUID`
   - `last_successful_run_at TIMESTAMPTZ`
   - PK (`source`, `tld`)

5. `zone_file_artifact` (Entity técnica)
   - `id UUID PK`
   - `source VARCHAR(32) NOT NULL`
   - `tld VARCHAR(24) NOT NULL`
   - `bucket VARCHAR(128) NOT NULL`
   - `object_key TEXT NOT NULL`
   - `etag VARCHAR(128) NULL`
   - `sha256 CHAR(64) NOT NULL`
   - `size_bytes BIGINT NOT NULL`
   - `downloaded_at TIMESTAMPTZ NOT NULL`

Índices mínimos:

- `domain(tld, last_seen_at DESC)`
- `domain(status, tld)`
- `domain_observation(tld, observed_at DESC)`
- `ingestion_run(source, tld, started_at DESC)`
- `zone_file_artifact(tld, downloaded_at DESC)`

### 6.6 Estratégia de delta (sem full compare em memória)

Para não carregar milhões de domínios em RAM:

1. criar tabela temporária `stg_zone_domain_<run_id>`;
2. inserir domínios parseados em batch (`COPY`/bulk);
3. `INSERT ... SELECT` para novos;
4. `UPDATE ... FROM stg` para existentes (`last_seen_at`, `deleted_at=NULL`, `status='active'`);
5. `UPDATE domain` para removidos (`status='deleted'`, `deleted_at=now`) onde `tld=:tld` e não existe em staging;
6. registrar métricas no `ingestion_run` e dropar staging.

### 6.7 Storage S3

Padrão de chave:

```text
zones/czds/{tld}/{yyyy}/{mm}/{dd}/{run_id}/{tld}.zone.gz
```

Metadados obrigatórios no objeto:

- `source=czds`
- `tld=<tld>`
- `run_id=<uuid>`
- `sha256=<hash>`

### 6.8 Agendamento e execução

- Scheduler diário no worker dedicado.
- Janela UTC configurável por env (`CZDS_SYNC_CRON`).
- Concorrência padrão: 1 TLD por vez (evita saturação no início).
- Lock distribuído por TLD em PostgreSQL.
- Endpoint manual apenas enfileira/solicita execução; processamento no worker.

### 6.9 Configuração e ambientes

Variáveis adicionais necessárias:

```env
CZDS_USERNAME=
CZDS_PASSWORD=
CZDS_ENABLED_TLDS=net,org,info
CZDS_SYNC_CRON=0 7 * * *
CZDS_FORCE_COOLDOWN_HOURS=24

S3_BUCKET=
S3_REGION=
S3_ENDPOINT_URL=http://minio:9000
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=
S3_FORCE_PATH_STYLE=true

DATABASE_URL=
```

> `S3_ENDPOINT_URL` permite AWS ou compatível (MinIO) sem mudar código.

### 6.10 Gestão de TLDs no runtime

Ordem de prioridade para lista de TLDs habilitados:

1. `czds_tld_policy` (fonte primária em produção);
2. `CZDS_ENABLED_TLDS` (fallback);
3. lista hardcoded apenas para bootstrap local de desenvolvimento.

Regras:

- scheduler processa somente `is_enabled = true`;
- ordenação por `priority ASC`, depois `tld ASC`;
- se falhar em um TLD, continua para o próximo e marca `ingestion_run` como `failed`;
- respeita cooldown por TLD (`cooldown_hours`).

### 6.11 Infraestrutura (ajuste ao projeto)

**Não usar `docker-compose`** neste projeto.

Aplicar no Swarm:

- `infra/stack.dev.yml`: incluir serviço `czds_ingestor` (imagem backend, comando worker)
- `infra/stack.yml`: incluir serviço equivalente de produção
- Secrets/configs para credenciais CZDS e S3
- `deploy.replicas: 1` no worker até existir lock global robusto + fila

---

## 7. Definições necessárias antes de codar

- [x] **Escopo inicial de TLDs** definido: `.net`, `.org`, `.info` (sem `.com` na fase 1)
- [x] **Estratégia de remoção** definida: soft delete com `deleted_at`
- [x] **Topologia de execução** definida: worker dedicado
- [x] **Storage em dev** definido: MinIO
- [ ] **Política de retenção dos raw files no S3** → Quem decide: PO + Plataforma

---

## 8. Critérios de pronto (técnicos)

- [ ] Migrações Alembic criadas e aplicáveis sem quebra
- [ ] Ingestão de 1 TLD médio (`.net` ou `.org`) concluída fim-a-fim
- [ ] Raw `.zone.gz` salvo no S3 com metadados obrigatórios
- [ ] Delta aplica `novos`, `reativados` e `deletados` corretamente
- [ ] Endpoint manual responde `202` e permite rastrear status do `run_id`
- [ ] Logs estruturados com `run_id`, `tld`, contadores e erro
- [ ] Proteção contra dupla execução simultânea por TLD
- [ ] Execução em `infra/stack.dev.yml` validada em container

---

## 9. Plano de implementação sugerido (fases)

### Fase 1 — Fundação

- modelagem + Alembic das tabelas de ingestão,
- cliente CZDS + upload S3,
- parsing stream + staging table,
- endpoint manual de trigger.

### Fase 2 — Operação

- worker dedicado no stack,
- scheduler diário,
- lock distribuído e retries com backoff,
- métricas operacionais por execução.

### Fase 3 — Escala

- tuning de batch/COPY,
- estratégia para `.com`,
- particionamento adicional e otimização de índices,
- políticas de retenção e custo.
