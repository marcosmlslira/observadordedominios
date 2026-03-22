# Data Modeling Master Spec — Observador de Domínios

## 1) Objetivo e escopo

Este documento define a modelagem de dados canônica do produto, cobrindo as features já especificadas em:

- Autenticação simples
- SSO (OIDC/SAML)
- Ferramentas pontuais (DNS, WHOIS, SSL, Screenshot, Página suspeita)
- Base global de domínios (ingestão multi-fonte, histórico e snapshots)
- Pagamentos e assinaturas (Stripe)

Objetivos da modelagem:

1. Ser escalável para volume global de domínios e histórico temporal.
2. Manter separação clara de domínios de negócio.
3. Garantir evolução segura de schema sem downtime.
4. Permitir manutenção contínua com versionamento explícito do modelo.

---

## 2) Premissas de modelagem (aplicando a skill)

Com base em `.github/skills/database-modeling/SKILL.md`:

- PostgreSQL é o banco transacional principal.
- Dados temporais de alto volume usam tabelas append-only + particionamento por tempo.
- Status usam enum/check, nunca string livre.
- Dados variáveis externos usam JSONB somente para metadados/raw payload, não como atalho de modelagem.
- Evolução de schema segue ciclo de migração segura (additive-first, backfill, cutover, deprecação).
- IDs recomendados: UUID v7 para entidades de negócio.

---

## 3) Mapa de domínios (bounded contexts)

### 3.1 identity_access

Responsabilidade: autenticação, sessão, identidade federada, autorização e auditoria de acesso.

### 3.2 billing

Responsabilidade: planos, assinatura, vínculo Stripe, limites de uso e eventos de cobrança.

### 3.3 domain_intelligence_global

Responsabilidade: base global centralizada de domínios, observações de fontes, inferência temporal e DNS snapshots.

### 3.4 monitoring_workspace

Responsabilidade: relação organização ↔ domínios monitorados, execuções de ferramentas e histórico consultável por organização.

### 3.5 platform_ops_audit

Responsabilidade: auditoria operacional, execução de pipelines, rastreabilidade e governança técnica.

---

## 4) Estratégia multi-tenant

### 4.1 Tabelas globais do sistema

Sem `organization_id`:

- Base global de domínios e observações (`domain_intelligence_global`)
- Catálogos de plano/produto
- Metadados técnicos de conectores e execução de ingestão

### 4.2 Tabelas tenant-aware

Com `organization_id` obrigatório:

- Usuários, memberships e sessão de produto
- Histórico de ferramentas executadas por cliente
- Assinaturas e limites efetivos por organização
- Evidências e resultados visualizados pelo cliente

### 4.3 Segurança de dados

- Aplicar RLS nas tabelas tenant-aware.
- Nunca aplicar RLS em tabelas globais de inteligência (acesso controlado por serviço).

---

## 5) Modelo lógico por domínio

## 5.1 Identity & Access

### Entidades principais

- `organization` (Entity, tenant owner)
- `user_account` (Entity)
- `organization_membership` (Relationship)
- `role` (Configuration/catalog)
- `user_session` (Entity)
- `refresh_token_chain` (Event/Entity de segurança)
- `mfa_factor` (Entity)
- `auth_event` (Event)

### SSO

- `sso_connection` (Entity)
- `sso_connection_domain` (Relationship)
- `sso_claim_mapping` (Configuration)
- `federated_identity` (Relationship user ↔ external identity)
- `sso_login_event` (Event)

### Regras críticas

- `organization_membership` UNIQUE (`organization_id`, `user_id`).
- `sso_connection_domain.domain` UNIQUE global para evitar colisão entre organizações.
- `federated_identity` UNIQUE (`provider`, `external_subject`).

## 5.2 Billing

### Entidades principais

- `billing_plan` (Catalog)
- `billing_price` (Catalog)
- `organization_subscription` (Entity)
- `organization_usage_limit` (Snapshot/config)
- `billing_invoice` (Entity)
- `billing_webhook_event` (Event append-only)
- `billing_entitlement_event` (Event)

### Regras críticas

- `organization_subscription` UNIQUE ativo por organização.
- Webhooks Stripe idempotentes por `stripe_event_id` UNIQUE.
- Atualização de limites sempre derivada de evento validado de assinatura.

## 5.3 Domain Intelligence Global

### Entidades principais

- `domain` (Entity canônica global)
  - `name`, `etld1`, `tld`, `first_seen_at`, `last_seen_at`, `registered_at_best`, `registered_at_confidence`, `status`
- `domain_source` (Catalog)
- `domain_observation` (Event append-only)
  - fonte, tempo observado, referência raw, payload técnico
- `domain_registration_evidence` (Event)
  - evidência específica para cálculo de `registered_at_best`
- `ingestion_run` (Entity operacional)
- `ingestion_run_source` (Relationship run ↔ source)
- `ingestion_checkpoint` (Snapshot de cursor por fonte)
- `dns_snapshot` (Snapshot temporal)
- `dns_snapshot_current` (Read model/materialização do último snapshot)

### Regras críticas

- `domain.name` UNIQUE (canônico: lowercase + punycode + sem trailing dot).
- `domain_observation` idempotente por hash natural (`domain_id`, `source_id`, `observed_at`, `record_fingerprint`).
- `ingestion_run` e `ingestion_checkpoint` por fonte com ciclo de vida independente.
- `registered_at_best` sempre derivado por ranking de confiança em `domain_registration_evidence`.

## 5.4 Monitoring Workspace (por organização)

### Entidades principais

- `organization_monitored_domain` (Relationship org ↔ domain)
  - estado de monitoramento, prioridade, tags
- `tool_execution` (Entity de execução)
  - tipo (`dns_lookup`, `whois`, `ssl_check`, `screenshot`, `suspicious_page`, `quick_analysis`)
  - alvo, executor, status, latência, erro
- `tool_dns_result` (Snapshot)
- `tool_whois_result` (Snapshot)
- `tool_ssl_result` (Snapshot)
- `tool_screenshot_result` (Snapshot)
  - `object_key` para storage externo
- `tool_suspicious_result` (Snapshot)
- `tool_quick_analysis_result` (Snapshot agregada)

### Regras críticas

- Toda execução pertence a uma organização.
- Falha parcial por ferramenta não invalida a execução consolidada.
- Screenshot armazena somente chave de objeto (S3/R2/compatível), nunca binário no PostgreSQL.

## 5.5 Platform Ops & Audit

### Entidades principais

- `audit_event` (Event)
- `job_queue` (Entity operacional)
- `job_attempt` (Event)
- `system_incident` (Entity opcional para operação)

### Regras críticas

- `audit_event` append-only e imutável.
- `job_attempt` registra retry, erro e duration para observabilidade.

---

## 6) Relações principais (visão textual)

- `organization` 1:N `organization_membership` N:1 `user_account`
- `organization` 1:N `sso_connection`
- `sso_connection` 1:N `sso_connection_domain`
- `user_account` 1:N `user_session`
- `organization` 1:N `organization_subscription`
- `billing_plan` 1:N `billing_price`
- `domain` 1:N `domain_observation`
- `domain_source` 1:N `domain_observation`
- `domain` 1:N `dns_snapshot`
- `organization` N:M `domain` via `organization_monitored_domain`
- `tool_execution` 1:1/1:N resultados por tipo (dependendo da ferramenta)

---

## 7) Estratégia física de armazenamento e escala

## 7.1 Particionamento

Particionar por mês (`RANGE observed_at/collected_at`) em:

- `domain_observation`
- `domain_registration_evidence`
- `dns_snapshot`
- `auth_event`
- `audit_event`
- `billing_webhook_event`

## 7.2 Índices mínimos obrigatórios

### Global domains

- `domain(name)` UNIQUE
- `domain(etld1, first_seen_at DESC)`
- `domain_observation(domain_id, observed_at DESC)`
- `domain_observation(source_id, observed_at DESC)`
- `domain_observation(record_fingerprint)`

### Tenant tables

- `organization_monitored_domain(organization_id, domain_id)` UNIQUE
- `tool_execution(organization_id, created_at DESC)`
- `tool_execution(organization_id, target_domain, created_at DESC)`
- `organization_subscription(organization_id, status)`

### Auth & SSO

- `organization_membership(organization_id, user_id)` UNIQUE
- `federated_identity(provider, external_subject)` UNIQUE
- `sso_connection_domain(domain)` UNIQUE

## 7.3 JSONB com uso controlado

Permitido para:

- payload bruto de fonte externa
- metadado técnico de execução
- detalhes não canônicos de WHOIS/CT log

Proibido:

- atributos nucleares de entidade (ex.: status, owner, tempo de criação, relacionamento principal)

---

## 8) Catálogo de enums recomendado

- `account_status`: `pending_email_verification`, `active`, `locked`, `disabled`
- `membership_role`: `owner`, `admin`, `analyst`, `viewer`
- `sso_protocol`: `oidc`, `saml`
- `subscription_status`: `trialing`, `active`, `past_due`, `canceled`, `incomplete`
- `domain_status`: `active`, `inactive`, `unknown`
- `source_status`: `ready`, `running`, `failed`, `paused`
- `job_status`: `queued`, `running`, `succeeded`, `failed`, `dead_letter`
- `tool_status`: `queued`, `running`, `partial_success`, `success`, `failed`, `timeout`
- `risk_level`: `low`, `medium`, `high`, `inconclusive`

---

## 9) Convenções de naming e integridade

- Tabelas em singular e `snake_case`.
- Colunas sem abreviações ambíguas.
- Toda FK com `ondelete` explícito.
- Todos os campos de tempo em `TIMESTAMPTZ`.
- Tabelas append-only não sofrem update em payload funcional.
- Soft delete somente onde houver requisito explícito de negócio.

---

## 10) Protocolo de evolução contínua do modelo (living model)

## 10.1 Fonte de verdade

Este arquivo é a fonte de verdade funcional/lógica. O schema físico é a soma de migrações Alembic.

## 10.2 Workflow obrigatório por mudança

1. Atualizar este documento (seção impactada e versão).
2. Registrar decisão arquitetural em ADR curta (`docs/adr/`).
3. Criar migration Alembic additive-first.
4. Backfill em lote, quando necessário.
5. Ativar leitura/cutover em deploy posterior.
6. Remover legado apenas após janela de deprecação.

## 10.3 Política de versionamento

- `model_version` semântico: `MAJOR.MINOR.PATCH`
- MAJOR: quebra incompatível
- MINOR: adição compatível de entidade/coluna/índice
- PATCH: ajuste não funcional (índice, comentário, documentação)

Versão atual do modelo: **1.0.0**

## 10.4 Template de changelog de modelo

Adicionar entradas em `docs/data-modeling-changelog.md` com:

- data
- versão
- contexto de negócio
- entidades afetadas
- migrações aplicadas
- estratégia de rollback

---

## 11) Sequência recomendada de implementação de schema

1. **Foundation**: `organization`, `user_account`, `organization_membership`, `role`, `auth_event`
2. **Auth core**: sessão, refresh chain, MFA
3. **SSO**: conexão, domínios, mappings, identidade federada, eventos
4. **Global domain intelligence**: domínio canônico, fonte, observação, ingestão, checkpoint
5. **DNS snapshots**: histórico + current read model
6. **Freetools**: execução e resultados por ferramenta
7. **Billing**: planos, assinatura, webhooks, limites
8. **Ops/Audit hardening**: job attempt, auditoria ampliada, índices e particionamento

---

## 12) Riscos e mitigação

- **Risco**: crescimento explosivo de `domain_observation`.
  - **Mitigação**: particionamento mensal + retenção por camada (raw vs canônico).

- **Risco**: drift entre estado Stripe e banco local.
  - **Mitigação**: idempotência por evento + rotinas de reconciliação.

- **Risco**: consulta lenta em histórico por organização.
  - **Mitigação**: índices compostos orientados a filtros reais e paginação obrigatória.

- **Risco**: inconsistência de canonicalização de domínio.
  - **Mitigação**: biblioteca única de normalização no backend + testes de regressão de parser.

---

## 13) Checklist de revisão antes de merge

- [ ] Domínio de negócio identificado e não misturado.
- [ ] Classificação da tabela (Entity/Relationship/Event/Snapshot/Configuration) definida.
- [ ] Ownership validado (global vs organization).
- [ ] FKs e `ondelete` explícitos.
- [ ] Índices mapeados para queries reais.
- [ ] Impacto temporal/retention definido.
- [ ] Migração segura + rollback planejado.
- [ ] Documento mestre e changelog atualizados.
