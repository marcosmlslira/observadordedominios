# Refinamento Técnico: Ingestão DNS via NSEC Zone Walking

**Data:** 2026-02-28  
**Refinador:** Tech Refiner Agent  
**Status:** 🟢 Especificação complementar aprovada para implementação

---

## 1. Entendimento

Implementar uma **fonte complementar** de ingestão de domínios via **DNS NSEC Zone Walking**, sem substituir o fluxo CZDS existente.

Objetivo operacional:

1. executar walk NSEC para TLDs configurados (inicialmente `.br`),
2. salvar artefato raw da execução em storage S3 compatível,
3. aplicar delta real no PostgreSQL (novos, mantidos, removidos),
4. manter rastreabilidade por execução (`ingestion_run`),
5. coexistir com a ingestão CZDS em arquitetura híbrida por fonte/TLD.

Este refinamento pertence ao domínio `domain_intelligence_global`, subdomínio `nsec_ingestion`, e segue arquitetura em camadas do backend FastAPI.

---

## 2. Decisões aprovadas

- **[N1] Serviço separado:** manter **worker dedicado** para NSEC, isolado do worker CZDS e da API HTTP.
- **[N2] Estratégia de execução:** tarefa longa em container dedicado (Swarm/Fargate/ECS task), sem Lambda.
- **[N3] Política de TLD:** processar apenas TLDs que publiquem **NSEC** (não NSEC3).
- **[N4] Fonte inicial:** `.br` como primeiro alvo de produção.
- **[N5] Remoção:** **soft delete** com `deleted_at`, preservando histórico.
- **[N6] Persistência raw:** armazenar snapshot raw por run em S3/MinIO antes do delta.
- **[N7] Rate limit obrigatório:** limite de consultas por segundo configurável para evitar bloqueio em nameservers autoritativos.

### Estratégia híbrida recomendada (complementar)

- CZDS continua como fonte primária para TLDs com zone file autorizado.
- NSEC cobre TLDs walkable sem CZDS ou com política de acesso restrita.
- Unificação por `source` (`czds` / `nsec`) e `tld` no controle de execução.

---

## 3. Mapa Técnico

### Dados envolvidos

| Entidade | Operação | Observação |
|----------|----------|------------|
| `domain` | UPSERT | Registro canônico por domínio (`last_seen_at`, `deleted_at`) |
| `domain_observation` | INSERT | Evento append-only por execução/fonte |
| `ingestion_run` | INSERT/UPDATE | Estado, duração, volume e erro por run |
| `ingestion_checkpoint` | UPSERT | Último sucesso por fonte/TLD |
| `zone_file_artifact` | INSERT | Metadados do raw (`bucket`, `key`, `etag/hash`, `size`) |
| `nsec_tld_policy` | UPSERT/SELECT | Lista de TLDs, QPS e prioridades de execução |

### Componentes impactados

- [x] Banco de dados — política NSEC + rastreabilidade por run
- [x] Worker/Jobs — scheduler e execução de walk por TLD
- [x] Serviços externos — DNS autoritativo + S3/MinIO
- [x] API — endpoint manual de trigger/status (reuso de padrão existente)
- [ ] Frontend — não obrigatório para fase de ingestão
- [x] Observabilidade — logs estruturados, métricas de progresso e falhas

### Fluxo de dados

```text
[Scheduler/API Trigger] → [Use case sync_nsec_tld] → [NSEC walk com rate limit]
→ [Persist raw snapshot no S3] → [Aplicar delta no Postgres]
→ [Atualizar run/checkpoint + métricas] → [Logs + status]
```

---

## 4. Viabilidade e Riscos

### Viabilidade

| Dimensão | Avaliação | Observação |
|----------|-----------|------------|
| Complexidade técnica | Alta | Alto volume DNS + janela longa de execução |
| Incerteza de implementação | Média | Dependente de comportamento dos NS por TLD |
| Impacto no sistema atual | Médio | Complementa modelo CZDS existente |
| Estimativa aproximada | 7–14 dias úteis | MVP de `.br` com observabilidade |

### Riscos identificados

- 🔴 **Bloqueio/rate-limit por nameserver** em consultas agressivas.  
  **Mitigação:** `MAX_QUERIES_PER_SECOND`, backoff exponencial, retry com jitter.

- 🔴 **Execução duplicada do mesmo TLD** em escala horizontal.  
  **Mitigação:** lock distribuído por `source+tld` com `pg_try_advisory_lock`.

- 🟡 **Walk incompleto por timeout/intermitência DNS**.  
  **Mitigação:** checkpoint de progresso parcial, retentativa e tolerância a falhas por trecho.

- 🟡 **Custo de execução prolongada** (2h–8h em TLDs grandes).  
  **Mitigação:** janela dedicada, prioridade por TLD e monitoramento de duração.

---

## 5. Caminhos possíveis

### Caminho A — acoplar NSEC no serviço CZDS (não recomendado)
**Prós:** menor esforço inicial.  
**Contras:** concorrência de recursos, maior acoplamento, difícil tunning operacional.

### Caminho B — worker dedicado `nsec_walker` (recomendado)
**Prós:** isolamento, escalabilidade independente, operação previsível por tipo de ingestão.  
**Contras:** mais um serviço no stack.

### ✅ Recomendação

Adotar **Caminho B** no mesmo monorepo, com serviço dedicado em `infra/stack.dev.yml` e `infra/stack.yml`.

> Observação de governança: neste repositório, usar **Docker Stack/Swarm**; `docker-compose` não deve ser adotado.

---

## 6. Especificação Técnica

### 6.1 Estrutura recomendada (incremental em `backend/app`)

```text
app/
  api/v1/routers/nsec_ingestion.py
  services/use_cases/
    sync_nsec_tld.py
    walk_nsec_zone.py
    apply_nsec_delta.py
  repositories/sqlalchemy/
    nsec_tld_policy_repository.py
    ingestion_run_repository.py
    domain_repository.py
    zone_artifact_repository.py
  infra/external/
    dns_client.py
    s3_storage.py
  models/
    nsec_tld_policy.py
    ingestion_run.py
    ingestion_checkpoint.py
    domain.py
    domain_observation.py
    zone_file_artifact.py
  schemas/
    nsec_ingestion.py
```

Regra de responsabilidade:
- rota HTTP apenas dispara/consulta;
- regra de negócio em `services/use_cases`;
- acesso a dados em `repositories` sem `commit`.

### 6.2 Endpoints

```http
POST /v1/nsec/trigger-walk
Body: {
  "tld": "br",
  "force": false,
  "queries_per_second": 8
}
Response 202: {
  "run_id": "uuid",
  "status": "queued|running",
  "source": "nsec",
  "tld": "br"
}

GET /v1/nsec/runs/{run_id}
Response 200: {
  "run_id": "uuid",
  "source": "nsec",
  "tld": "br",
  "status": "running|success|failed",
  "started_at": "...",
  "finished_at": "...",
  "domains_seen": 0,
  "domains_inserted": 0,
  "domains_reactivated": 0,
  "domains_deleted": 0,
  "artifact_key": "zones/nsec/br/2026/02/28/<run_id>/br.txt.gz"
}
```

### 6.3 Regras de negócio

- Regra 1: só executar TLD marcado como `walk_enabled=true` em `nsec_tld_policy`.
- Regra 2: respeitar cooldown por TLD (ex.: 24h), exceto `force=true`.
- Regra 3: salvar snapshot raw da execução no S3 antes de aplicar delta.
- Regra 4: aplicar remoções apenas quando a run terminar com `SUCCESS`.
- Regra 5: garantir idempotência por `run_id` + hash do artefato.
- Regra 6: registrar progresso periódico (`domains_seen`) para observabilidade.

### 6.4 Configuração (env)

```env
NSEC_ENABLED=true
NSEC_WALK_TLDS=br
NSEC_MAX_QUERIES_PER_SECOND=8
NSEC_DNS_TIMEOUT_SECONDS=5
NSEC_RETRY_MAX_ATTEMPTS=5
NSEC_RETRY_BASE_DELAY_MS=250
```

Variáveis de infraestrutura já existentes (`AWS_*`, `POSTGRES_*`) são reutilizadas.

### 6.5 Tecnologia recomendada

- FastAPI + Uvicorn (controle e trigger)
- dnspython (query DNS NSEC)
- SQLAlchemy + asyncpg
- boto3 (S3/MinIO compatível)
- APScheduler (agendamento diário)

---

## 7. Modelagem de dados (complementar)

**Domain:** `domain_intelligence_global`  
**Subdomain:** `nsec_ingestion`  
**Ownership level:** `System`

### Tabela nova: `nsec_tld_policy` (Configuration)

Campos mínimos:
- `tld` (PK)
- `walk_enabled` (bool)
- `priority` (int)
- `cooldown_hours` (int, default 24)
- `queries_per_second` (int)
- `max_runtime_minutes` (int)
- `authoritative_nameservers` (jsonb técnico)
- `notes` (text, opcional)
- `updated_at`

### Reuso de tabelas existentes de ingestão

- `domain`
- `domain_observation`
- `ingestion_run`
- `ingestion_checkpoint`
- `zone_file_artifact`

Com distinção por:
- `source = 'nsec'`
- `tld = 'br'` (ou demais TLDs elegíveis)

---

## 8. Operação e agendamento

- Janela padrão diária: `05:00 UTC`.
- Execução por prioridade (`nsec_tld_policy.priority`).
- Concorrência inicial recomendada: `1` TLD por worker.
- Guardrail de runtime por TLD: encerrar run com `FAILED_TIMEOUT` se exceder limite da política.

---

## 9. Observabilidade e SRE

### Logs estruturados mínimos

- `run_id`, `source`, `tld`, `current_owner`, `next_owner`, `queries_sent`, `domains_seen`, `qps`, `duration_seconds`, `status`.

### Métricas mínimas

- `nsec_walk_duration_seconds`
- `nsec_queries_total`
- `nsec_query_errors_total`
- `nsec_domains_seen_total`
- `nsec_delta_inserted_total`
- `nsec_delta_deleted_total`

### Alertas recomendados

- falha de run por 2 dias consecutivos por TLD;
- duração acima do percentil histórico;
- taxa de erro DNS acima do limiar configurado.

---

## 10. Segurança e conformidade

- endpoint de trigger restrito a perfil `admin/internal`;
- secrets em variáveis de ambiente (sem credenciais em código);
- sem dados pessoais no pipeline (apenas nomes de domínio);
- retenção de artefatos com lifecycle por ambiente.

---

## 11. Próxima etapa: similaridade e risco

Após estabilidade da ingestão híbrida (CZDS + NSEC):

1. habilitar `pgvector` no PostgreSQL,
2. adicionar coluna `embedding` na entidade de domínio canônico,
3. criar job de embedding diário para domínios novos/alterados,
4. habilitar busca de vizinhança semântica para score de risco.

Essa etapa é opcional para o MVP de ingestão e deve ser tratada como refinamento separado.

---

## 12. Critérios de aceite (MVP NSEC)

- [ ] Trigger manual inicia run para `.br` e retorna `run_id`.
- [ ] Worker NSEC grava artefato raw em S3/MinIO.
- [ ] Delta aplica inserção/reativação/remoção com consistência transacional.
- [ ] `ingestion_run` e `ingestion_checkpoint` refletem execução real.
- [ ] Lock impede duas runs simultâneas para `source+tld`.
- [ ] Logs e métricas permitem diagnóstico operacional.
