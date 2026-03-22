# PRD: Autenticação Simples

## 1. Product overview

### 1.1 Document title and version

- PRD: Autenticação Simples
- Version: 1.0

### 1.2 Product summary

Este PRD define a autenticação simples da plataforma com foco em segurança, previsibilidade operacional e baixo atrito para usuários de pequenas e médias equipes. O escopo cobre cadastro, login, sessão, recuperação de acesso e controles de proteção contra abuso.

A solução adota e-mail e senha com tokens JWT de acesso e refresh token rotativo, controles de sessão por dispositivo e trilha de auditoria. O objetivo é estabelecer uma base sólida para acesso seguro a todas as features da plataforma e habilitar evolução posterior para fluxos corporativos.

## 2. Goals

### 2.1 Business goals

- Reduzir risco de acesso indevido com controles de autenticação robustos.
- Padronizar o mecanismo de acesso para todas as áreas autenticadas.
- Diminuir tickets de suporte por problemas de login e recuperação de conta.
- Criar base compatível com evolução para SSO corporativo.

### 2.2 User goals

- Entrar na plataforma com fluxo simples e confiável.
- Recuperar acesso com rapidez e segurança quando esquecer a senha.
- Visualizar e encerrar sessões ativas quando necessário.
- Ter proteção adicional com MFA opcional.

### 2.3 Non-goals

- Não cobre login social direto (Google, Microsoft) nesta fase.
- Não cobre autenticação federada via IdP corporativo (escopo do PRD de SSO).
- Não inclui políticas adaptativas avançadas por risco geográfico/dispositivo.

## 3. User personas

### 3.1 Key user types

- Usuário cliente
- Administrador da organização
- Operações internas

### 3.2 Basic persona details

- **Usuário cliente**: precisa acessar rapidamente recursos de monitoramento com segurança.
- **Administrador da organização**: precisa controlar acesso da equipe e reduzir risco operacional.
- **Operações internas**: precisa diagnosticar falhas de login com evidências auditáveis.

### 3.3 Role-based access

- **Usuário autenticado**: acessa recursos permitidos pelo papel da conta.
- **Administrador da organização**: gerencia sessões e políticas básicas da organização.
- **Administrador interno**: consulta auditoria e eventos de autenticação para suporte e conformidade.

## 4. Functional requirements

- **Cadastro e ativação de conta** (Priority: Alta)
  - Permitir criação de conta por e-mail e senha.
  - Validar e-mail com token de confirmação e validade temporal.
  - Exigir aceite de termos e política de privacidade.

- **Login seguro com sessão baseada em tokens** (Priority: Alta)
  - Autenticar por e-mail e senha.
  - Emitir access token de curta duração e refresh token rotativo.
  - Invalidar refresh token anterior a cada renovação.

- **Política de senha e recuperação de conta** (Priority: Alta)
  - Aplicar política mínima de senha forte.
  - Permitir redefinição de senha com token de uso único e expiração curta.
  - Revogar sessões ativas após troca de senha sensível.

- **Proteções contra abuso** (Priority: Alta)
  - Rate limit por IP e por conta em endpoints de autenticação.
  - Bloqueio temporário progressivo após tentativas inválidas.
  - Mensagens de erro neutras para evitar enumeração de usuários.

- **MFA opcional e gestão de sessões** (Priority: Média)
  - Habilitar MFA opcional via TOTP.
  - Exibir sessões ativas por dispositivo/data aproximada.
  - Permitir encerramento de sessão específica ou de todas as sessões.

- **Auditoria de autenticação** (Priority: Média)
  - Registrar eventos de login, logout, falha, reset e mudança de MFA.
  - Associar evento a usuário, organização e contexto técnico mínimo.

## 5. User experience

### 5.1 Entry points & first-time user flow

- Acesso por tela de login.
- Opção de criar conta na mesma jornada.
- Confirmação de e-mail antes do primeiro acesso completo.
- Guia curto para ativar MFA opcional no primeiro login.

### 5.2 Core experience

- **Cadastrar conta**: usuário informa e-mail, senha e aceite de termos.
  - Reduz fricção inicial sem comprometer validações essenciais.
- **Confirmar e-mail**: usuário valida conta por link temporário.
  - Garante posse do e-mail e reduz fraude de cadastro.
- **Autenticar e acessar painel**: usuário efetua login e recebe sessão segura.
  - Mantém experiência rápida com proteção por refresh rotativo.
- **Gerenciar segurança da conta**: usuário revisa sessões e MFA.
  - Aumenta controle e confiança no uso diário.

### 5.3 Advanced features & edge cases

- Tentativas repetidas geram bloqueio temporário com mensagem orientativa.
- Token de redefinição expirado oferece reemissão segura.
- Sessão inválida por rotação de token força novo login sem perda de integridade.
- Usuário sem e-mail confirmado tem acesso limitado a fluxo de verificação.

### 5.4 UI/UX highlights

- Mensagens objetivas e acionáveis para falha de autenticação.
- Indicadores claros de sessão expirada e próximo passo.
- Tela de segurança com lista de sessões e ação de revogação.
- Fluxos mobile-first com estados de loading, erro, vazio e desabilitado.

## 6. Narrative

O usuário cria a conta em poucos passos, confirma o e-mail e passa a acessar a plataforma com sessão segura e renovação transparente. Quando ocorre qualquer risco de acesso indevido, os mecanismos de proteção limitam abuso, enquanto MFA opcional e gestão de sessões oferecem autonomia para recuperação e controle.

## 7. Success metrics

### 7.1 User-centric metrics

- Taxa de sucesso no login acima de 95% para credenciais válidas.
- Taxa de conclusão do reset de senha acima de 85%.
- Adoção de MFA opcional acima de 25% em 90 dias.

### 7.2 Business metrics

- Redução de tickets relacionados a acesso em pelo menos 30%.
- Redução de incidentes de tomada de conta reportados.
- Aumento de ativação de contas confirmadas no primeiro dia.

### 7.3 Technical metrics

- Latência P95 em login menor que 500 ms (sem provedores externos).
- Taxa de erro 5xx em endpoints de auth menor que 1%.
- Cobertura de auditoria em 100% dos eventos críticos de autenticação.

## 8. Technical considerations

### 8.1 Integration points

- Backend FastAPI com camada de segurança em `core` e rotas de auth em `api`.
- Frontend Next.js com telas de login, cadastro, recuperação e segurança da conta.
- Banco PostgreSQL para usuários, sessões, refresh tokens e auditoria.

### 8.2 Data storage & privacy

- Armazenar senha com hash forte e salt (ex.: Argon2id).
- Persistir somente dados necessários para autenticação e auditoria.
- Garantir segregação por organização nos registros aplicáveis.

### 8.3 Scalability & performance

- Usar TTLs curtos para access token e rotação para refresh token.
- Indexar consultas de sessão e auditoria por usuário/organização/data.
- Aplicar rate limit em camada de API para prevenir abuso em picos.

### 8.4 Potential challenges

- Equilibrar segurança forte com baixa fricção de uso.
- Tratar clocks e expiração de token em ambientes distribuídos.
- Manter observabilidade sem registrar dados sensíveis em logs.

## 9. Milestones & sequencing

### 9.1 Project estimate

- M: 2 a 3 semanas

### 9.2 Team size & composition

- 3 a 4 pessoas: 1 Backend, 1 Frontend, 1 QA, 1 apoio DevOps/SRE parcial

### 9.3 Suggested phases

- **Fase 1**: Base de identidade e sessão segura (1 semana)
  - Cadastro, confirmação de e-mail, login e refresh rotativo.
- **Fase 2**: Recuperação de conta e proteções antiabuso (1 semana)
  - Reset de senha, rate limit e bloqueio por tentativas.
- **Fase 3**: MFA opcional, sessões e auditoria (1 semana)
  - Gestão de sessões e trilha completa de eventos.

## 10. User stories

### 10.1 Criar e ativar conta

- **ID**: GH-AUTH-001
- **Description**: Como novo usuário, quero criar e ativar minha conta para começar a usar a plataforma com segurança.
- **Acceptance criteria**:
  - Permite cadastro com e-mail, senha forte e aceite de termos.
  - Envia e-mail de confirmação com token temporário.
  - Bloqueia acesso completo até confirmação de e-mail.

### 10.2 Autenticar com sessão segura

- **ID**: GH-AUTH-002
- **Description**: Como usuário, quero fazer login com segurança e manter minha sessão ativa sem repetir login a todo momento.
- **Acceptance criteria**:
  - Emite access token curto e refresh token rotativo após login válido.
  - Renova sessão sem reautenticar enquanto refresh token for válido.
  - Revoga cadeia de refresh token ao detectar uso inválido/replay.

### 10.3 Recuperar acesso à conta

- **ID**: GH-AUTH-003
- **Description**: Como usuário, quero redefinir minha senha quando esquecer para recuperar acesso rapidamente.
- **Acceptance criteria**:
  - Solicitação de reset não revela existência da conta.
  - Token de reset é de uso único e expira em curto prazo.
  - Após redefinição, sessões antigas são revogadas.

### 10.4 Proteger contra tentativas maliciosas

- **ID**: GH-AUTH-004
- **Description**: Como plataforma, quero limitar tentativas de login para reduzir risco de brute force e enumeração.
- **Acceptance criteria**:
  - Aplica rate limit por IP e por identificador de conta.
  - Ativa bloqueio temporário progressivo após falhas consecutivas.
  - Retorna mensagens de erro neutras sem indicar se o usuário existe.

### 10.5 Habilitar MFA opcional

- **ID**: GH-AUTH-005
- **Description**: Como usuário, quero habilitar MFA para aumentar a proteção da minha conta.
- **Acceptance criteria**:
  - Permite ativar MFA via TOTP após validação de senha.
  - Exige segundo fator no login quando MFA estiver ativo.
  - Permite desativar MFA com reautenticação forte.

### 10.6 Gerenciar sessões ativas

- **ID**: GH-AUTH-006
- **Description**: Como usuário, quero ver e encerrar sessões para controlar acessos ativos.
- **Acceptance criteria**:
  - Lista sessões com data/hora aproximada e tipo de cliente.
  - Permite encerrar sessão específica.
  - Permite encerrar todas as outras sessões.

### 10.7 Garantir autenticação e autorização em recursos protegidos

- **ID**: GH-AUTH-007
- **Description**: Como administrador da organização, quero que recursos sensíveis exijam autenticação e respeitem permissões de papel.
- **Acceptance criteria**:
  - Endpoints protegidos rejeitam requisições sem token válido.
  - Permissões por papel são verificadas antes de ações sensíveis.
  - Acesso entre organizações é isolado por escopo de tenant.

### 10.8 Auditar eventos de autenticação

- **ID**: GH-AUTH-008
- **Description**: Como operações internas, quero rastrear eventos de autenticação para suporte, investigação e compliance.
- **Acceptance criteria**:
  - Registra login, logout, falha, reset, troca de senha e alteração de MFA.
  - Associa eventos a usuário, organização e timestamp.
  - Permite consulta por período e tipo de evento para usuários autorizados.
