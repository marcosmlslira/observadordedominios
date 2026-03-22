# Data Modeling Changelog

## [1.0.0] - 2026-02-27

### Contexto

Primeira consolidação do modelo de dados unificado do Observador de Domínios, cobrindo as features especificadas em autenticação simples, SSO, freetools, base global de domínios e billing.

### Entidades afetadas

- `organization`, `user_account`, `organization_membership`, `role`
- `user_session`, `refresh_token_chain`, `mfa_factor`, `auth_event`
- `sso_connection`, `sso_connection_domain`, `sso_claim_mapping`, `federated_identity`, `sso_login_event`
- `billing_plan`, `billing_price`, `organization_subscription`, `organization_usage_limit`, `billing_invoice`, `billing_webhook_event`, `billing_entitlement_event`
- `domain`, `domain_source`, `domain_observation`, `domain_registration_evidence`, `ingestion_run`, `ingestion_run_source`, `ingestion_checkpoint`, `dns_snapshot`, `dns_snapshot_current`
- `organization_monitored_domain`, `tool_execution`, `tool_dns_result`, `tool_whois_result`, `tool_ssl_result`, `tool_screenshot_result`, `tool_suspicious_result`, `tool_quick_analysis_result`
- `audit_event`, `job_queue`, `job_attempt`, `system_incident`

### Migrações

- Planejadas em fases (foundation → auth → sso → domain intelligence → dns snapshots → freetools → billing → ops hardening).
- Estratégia additive-first com backfill e cutover gradual.

### Rollback

- Reversão por migration inversa de cada fase.
- Para mudanças destrutivas futuras, manter ciclo de deprecação em múltiplos deploys.
