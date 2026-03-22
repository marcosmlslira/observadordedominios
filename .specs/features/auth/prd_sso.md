# PRD: Single Sign-On (SSO)

## 1. Product overview

### 1.1 Document title and version

- PRD: Single Sign-On (SSO)
- Version: 1.0

### 1.2 Product summary

Este PRD define o recurso de autenticação federada para organizações que desejam centralizar identidade em provedores corporativos. O escopo contempla suporte a OIDC e SAML 2.0, com controles de segurança para login corporativo e governança de acesso por tenant.

O recurso é complementar à autenticação simples e direcionado a planos corporativos. A proposta permite login via IdP, provisionamento controlado de usuários e aplicação consistente de autorização por organização e papel.

## 2. Goals

### 2.1 Business goals

- Habilitar aquisição e retenção de clientes corporativos com exigência de SSO.
- Reduzir riscos operacionais por credenciais locais em contas empresariais.
- Diminuir esforço de onboarding/offboarding por provisionamento centralizado.

### 2.2 User goals

- Entrar na plataforma com credenciais corporativas já conhecidas.
- Evitar múltiplas senhas para o mesmo contexto de trabalho.
- Ter acesso automaticamente alinhado ao vínculo organizacional.

### 2.3 Non-goals

- Não inclui SCIM nesta fase inicial.
- Não inclui federação entre múltiplos IdPs por usuário na mesma sessão.
- Não substitui regras internas de autorização por papel da aplicação.

## 3. User personas

### 3.1 Key user types

- Administrador de TI do cliente corporativo
- Usuário corporativo final
- Administrador interno da plataforma

### 3.2 Basic persona details

- **Administrador de TI do cliente corporativo**: precisa configurar e manter integração SSO segura e auditável.
- **Usuário corporativo final**: precisa acessar sem criar senha local adicional.
- **Administrador interno da plataforma**: precisa observar saúde de integrações e apoiar suporte técnico.

### 3.3 Role-based access

- **Admin da organização**: configura IdP, certificados/metadados e regras de mapeamento.
- **Usuário da organização**: autentica via SSO e acessa recursos conforme papel.
- **Admin interno**: visualiza status da integração e logs de autenticação federada.

## 4. Functional requirements

- **Suporte a protocolos SSO** (Priority: Alta)
  - Implementar OIDC (Authorization Code + PKCE) para provedores modernos.
  - Implementar SAML 2.0 para provedores corporativos legados.
  - Permitir habilitação por organização e plano.

- **Configuração por organização (tenant-aware)** (Priority: Alta)
  - Permitir cadastro de uma ou mais conexões SSO por organização.
  - Definir conexão padrão por domínio de e-mail quando aplicável.
  - Impedir colisão de domínios entre organizações distintas.

- **Fluxo de login federado** (Priority: Alta)
  - Iniciar login por discovery (domínio/e-mail) ou botão “Entrar com SSO”.
  - Validar assinatura, audiência, emissor e janelas de tempo do assertion/token.
  - Criar sessão da aplicação com tokens internos após autenticação federada.

- **Provisionamento e vínculo de conta** (Priority: Alta)
  - Suportar just-in-time provisioning com regras configuráveis.
  - Vincular usuário federado a conta existente por e-mail verificado e critérios de segurança.
  - Bloquear auto-provisionamento quando política da organização exigir aprovação.

- **Mapeamento de atributos e papéis** (Priority: Média)
  - Mapear atributos padrão (email, nome, identificador externo).
  - Permitir mapeamento de grupos/claims para papéis internos.
  - Definir fallback seguro quando atributo obrigatório não estiver presente.

- **Operação, segurança e auditoria** (Priority: Alta)
  - Registrar eventos de sucesso/falha por etapa de autenticação federada.
  - Aplicar rate limit e proteção de replay nos endpoints de callback.
  - Permitir rotação de certificados/chaves e atualização de metadados.

## 5. User experience

### 5.1 Entry points & first-time user flow

- Usuário acessa login e informa e-mail corporativo.
- Sistema identifica organização e redireciona para IdP apropriado.
- Após autenticação no IdP, usuário retorna autenticado à plataforma.
- Primeiro acesso pode pedir confirmação de vínculo, conforme política.

### 5.2 Core experience

- **Configurar conexão SSO**: admin organiza dados de OIDC ou SAML no painel.
  - Permite ativação segura e validada antes de produção.
- **Executar login federado**: usuário autentica no IdP e retorna ao sistema.
  - Remove necessidade de senha local e reduz atrito operacional.
- **Aplicar autorização interna**: sistema mapeia claims para permissões.
  - Garante que autenticação e autorização permaneçam separadas e previsíveis.

### 5.3 Advanced features & edge cases

- Falha de assinatura/issuer/audience bloqueia login com erro orientativo.
- Usuário sem claim de e-mail obrigatório cai em fluxo de suporte.
- Conta desativada no IdP perde acesso na próxima autenticação.
- Conexão SSO indisponível ativa fallback controlado definido pela organização.

### 5.4 UI/UX highlights

- Assistente de configuração com validação de metadados/campos obrigatórios.
- Tela de diagnóstico da conexão (último sucesso, últimas falhas, motivo).
- Mensagens de erro acionáveis para usuário final e para administrador.
- Fluxo mobile-first sem dependência de hover para ações críticas.

## 6. Narrative

O administrador corporativo configura o IdP uma única vez e valida a conexão antes da ativação. A partir daí, colaboradores entram pela identidade corporativa, com vínculo correto à organização e permissões consistentes, reduzindo riscos de credenciais locais e simplificando a operação diária.

## 7. Success metrics

### 7.1 User-centric metrics

- Taxa de sucesso de login SSO acima de 97% (excluindo indisponibilidade do IdP).
- Tempo médio de login federado abaixo de 8 segundos.
- Redução de chamados de senha em contas corporativas acima de 40%.

### 7.2 Business metrics

- Aumento da conversão de contas enterprise com requisito de SSO.
- Redução de churn em clientes com exigência de compliance de identidade.
- Aumento de adoção de SSO em organizações elegíveis.

### 7.3 Technical metrics

- Taxa de erro em callbacks SSO menor que 1.5%.
- Cobertura de auditoria em 100% dos eventos críticos de SSO.
- Tempo de diagnóstico de incidente SSO reduzido com trilha estruturada.

## 8. Technical considerations

### 8.1 Integration points

- Backend FastAPI com endpoints dedicados para OIDC e SAML callbacks.
- Frontend Next.js para setup administrativo, login discovery e mensagens de estado.
- Banco PostgreSQL para conexões SSO, mapeamentos, vínculos e auditoria.

### 8.2 Data storage & privacy

- Armazenar apenas atributos necessários para identidade e autorização.
- Criptografar segredos de integração em repouso.
- Segregar conexões e logs por organização.

### 8.3 Scalability & performance

- Processar callbacks de forma idempotente com proteção de replay.
- Cache curto de metadados públicos do IdP com invalidação controlada.
- Isolar falhas de um IdP para não degradar organizações não afetadas.

### 8.4 Potential challenges

- Diferenças de implementação entre provedores SAML.
- Mapeamento inconsistente de claims/grupos entre tenants.
- Estratégia segura de fallback quando IdP estiver indisponível.

## 9. Milestones & sequencing

### 9.1 Project estimate

- L: 4 a 6 semanas

### 9.2 Team size & composition

- 4 a 5 pessoas: 2 Backend, 1 Frontend, 1 QA, 1 apoio DevOps/SRE parcial

### 9.3 Suggested phases

- **Fase 1**: Base de identidade federada e modelo tenant-aware (1 semana)
  - Modelagem de conexões SSO por organização e auditoria inicial.
- **Fase 2**: OIDC end-to-end com setup administrativo (1 a 2 semanas)
  - Login federado completo com validações e mapeamento básico.
- **Fase 3**: SAML 2.0 e robustez operacional (2 semanas)
  - Suporte a metadata/certificados e tratamento de cenários corporativos.
- **Fase 4**: Hardening, fallback e observabilidade (1 semana)
  - Rate limit, replay protection, dashboards e runbooks operacionais.

## 10. User stories

### 10.1 Configurar provedor OIDC da organização

- **ID**: GH-SSO-001
- **Description**: Como admin da organização, quero configurar OIDC para habilitar login corporativo sem senha local.
- **Acceptance criteria**:
  - Permite inserir client id, issuer, redirect URI e escopos obrigatórios.
  - Valida conectividade e parâmetros antes de ativar.
  - Bloqueia ativação quando validação obrigatória falhar.

### 10.2 Configurar provedor SAML da organização

- **ID**: GH-SSO-002
- **Description**: Como admin da organização, quero configurar SAML 2.0 para integrar IdPs corporativos legados.
- **Acceptance criteria**:
  - Permite upload/import de metadados SAML.
  - Valida certificado de assinatura e campos essenciais.
  - Exibe erros específicos para metadados inválidos.

### 10.3 Realizar login via SSO por discovery

- **ID**: GH-SSO-003
- **Description**: Como usuário corporativo, quero informar meu e-mail e ser direcionado ao IdP correto automaticamente.
- **Acceptance criteria**:
  - Identifica organização pelo domínio ou regra configurada.
  - Redireciona ao IdP correto sem exibir opções irrelevantes.
  - Retorna ao sistema com sessão válida após autenticação bem-sucedida.

### 10.4 Provisionar usuário no primeiro acesso

- **ID**: GH-SSO-004
- **Description**: Como organização, quero provisionar usuário federado no primeiro login com políticas controladas.
- **Acceptance criteria**:
  - Cria conta JIT quando política permitir auto-provisionamento.
  - Vincula conta existente de forma segura quando critérios forem atendidos.
  - Bloqueia criação automática quando política exigir aprovação manual.

### 10.5 Mapear grupos/claims para papéis internos

- **ID**: GH-SSO-005
- **Description**: Como admin da organização, quero mapear atributos do IdP para papéis internos para manter permissões coerentes.
- **Acceptance criteria**:
  - Permite definir regras de mapeamento por claim/grupo.
  - Atualiza papel no login conforme regra ativa.
  - Aplica fallback seguro quando claim obrigatório estiver ausente.

### 10.6 Proteger callbacks e sessão federada

- **ID**: GH-SSO-006
- **Description**: Como plataforma, quero proteger callbacks SSO contra replay e abuso para manter integridade do login.
- **Acceptance criteria**:
  - Valida nonce/state e janelas temporais em todos os callbacks.
  - Aplica rate limit por origem e organização.
  - Rejeita assertion/token inválido sem vazar detalhes sensíveis.

### 10.7 Garantir autenticação e autorização por organização

- **ID**: GH-SSO-007
- **Description**: Como administrador da plataforma, quero garantir isolamento de tenant e autorização correta após login SSO.
- **Acceptance criteria**:
  - Usuário autenticado por SSO recebe escopo da organização correta.
  - Recursos de outra organização são bloqueados por padrão.
  - Permissões de papel são avaliadas antes de ações sensíveis.

### 10.8 Auditar eventos de SSO para suporte e compliance

- **ID**: GH-SSO-008
- **Description**: Como operações internas, quero trilha de auditoria de SSO para investigar falhas e atender requisitos de compliance.
- **Acceptance criteria**:
  - Registra tentativas, sucessos, falhas e mudanças de configuração SSO.
  - Permite consulta por organização, período e tipo de evento.
  - Exibe causa técnica resumida sem expor segredos.
