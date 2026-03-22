# PRD: SSL Check

## 1. Product overview

### 1.1 Document title and version

- PRD: SSL Check
- Version: 1.0

### 1.2 Product summary

Este PRD define a ferramenta de SSL Check para validação pontual de certificado TLS em domínios. A ferramenta deve identificar disponibilidade de certificado, validade e sinais críticos de confiança.

O resultado deve apoiar clientes e time interno na priorização de riscos técnicos de forma simples e rápida.

## 2. Goals

### 2.1 Business goals

- Entregar diagnóstico técnico de confiança HTTPS no módulo de ferramentas.
- Reduzir tempo de validação em triagem de domínios suspeitos.
- Criar base para alertas futuros de expiração e anomalias.

### 2.2 User goals

- Ver rapidamente se o host possui certificado válido.
- Identificar expiração, mismatch de hostname e risco crítico.
- Registrar evidência técnica no histórico da organização.

### 2.3 Non-goals

- Não realiza hardening de segurança do servidor.
- Não substitui auditoria completa de configuração TLS.
- Não corrige problemas automaticamente.

## 3. User personas

### 3.1 Key user types

- Analista de segurança
- Analista de marca/risco
- Operações internas

### 3.2 Basic persona details

- **Analista de segurança**: precisa de detalhes de validade e cadeia de confiança.
- **Analista de marca/risco**: precisa de severidade clara para decisão.
- **Operações internas**: precisa de status objetivo para suporte e triagem.

### 3.3 Role-based access

- **Cliente autenticado**: executa SSL Check e consulta histórico próprio.
- **Operador interno**: executa validação em casos operacionais.
- **Admin interno**: acompanha métricas e limites.

## 4. Functional requirements

- **Validação TLS** (Priority: Alta)
  - Verificar presença de certificado no host HTTPS.
  - Ler emissor, CN/SAN e período de validade.
  - Calcular dias restantes para expiração.

- **Classificação de severidade** (Priority: Alta)
  - Alto: expirado, ausente ou mismatch crítico.
  - Médio: próximo de expirar (janela configurável).
  - Baixo: válido sem sinais críticos.

- **Resultado padronizado** (Priority: Média)
  - Estrutura comum para uso na UI e serviços internos.
  - Registro temporal da execução.

- **Persistência de histórico** (Priority: Média)
  - Salvar resultado por organização e papel executor.

## 5. User experience

### 5.1 Entry points & first-time user flow

- Acesso via Ferramentas.
- Campo de domínio/host.
- Botão “Executar SSL Check”.

### 5.2 Core experience

- **Inserir host**: usuário informa alvo HTTPS.
  - Mantém entrada simples e direta.
- **Executar validação**: sistema consulta certificado.
  - Entrega resultado técnico em poucos segundos.
- **Ler severidade**: usuário vê classificação e justificativa.
  - Facilita priorização de risco.

### 5.3 Advanced features & edge cases

- Host sem HTTPS retorna “sem TLS”.
- Timeout de conexão retorna erro controlado.
- Certificado válido porém sem SAN adequado retorna alerta.

### 5.4 UI/UX highlights

- Badge de severidade (baixo/médio/alto).
- Bloco de validade com dias restantes.
- Mensagens de ação recomendada.

## 6. Narrative

Durante a triagem de um domínio, o analista executa SSL Check e descobre rapidamente se o certificado é confiável e atual. Quando encontra severidade alta, prioriza investigação imediata e encaminha evidências para resposta interna.

## 7. Success metrics

### 7.1 User-centric metrics

- Tempo médio de resposta menor que 6 segundos.
- Clareza da severidade percebida acima de 90% em teste de usabilidade.

### 7.2 Business metrics

- Aumento de uso da ferramenta em fluxos de triagem.
- Redução de tempo para decisão de prioridade técnica.

### 7.3 Technical metrics

- P95 de latência menor que 10 segundos.
- Taxa de erro técnico menor que 4%.

## 8. Technical considerations

### 8.1 Integration points

- Endpoint backend para SSL Check.
- Serviço de leitura e validação de certificado.
- Frontend com visualização de severidade.

### 8.2 Data storage & privacy

- Armazenar apenas metadados do certificado.
- Evitar dados sensíveis desnecessários.
- Acesso por organização.

### 8.3 Scalability & performance

- Timeouts curtos e retentativa controlada.
- Rate limit por organização.
- Cache breve para consultas repetidas.

### 8.4 Potential challenges

- Hosts com configurações TLS não padronizadas.
- Intermitência de handshake por rede.
- Diferença entre domínio raiz e subdomínios.

## 9. Milestones & sequencing

### 9.1 Project estimate

- S: 1 semana

### 9.2 Team size & composition

- 2 a 3 pessoas: 1 Backend, 1 Frontend, 1 QA parcial

### 9.3 Suggested phases

- **Fase 1**: Serviço TLS e endpoint (3 dias)
  - Retorno de campos essenciais e severidade.
- **Fase 2**: UX e histórico (2 dias)
  - Exibição e persistência por organização.

## 10. User stories

### 10.1 Validar certificado do host

- **ID**: GH-SSL-001
- **Description**: Como analista, quero validar certificado TLS para medir confiança técnica.
- **Acceptance criteria**:
  - Exibe emissor, CN/SAN, validade e dias restantes.
  - Identifica ausência de TLS de forma explícita.
  - Registra timestamp da execução.

### 10.2 Receber severidade objetiva

- **ID**: GH-SSL-002
- **Description**: Como analista, quero severidade clara para priorizar resposta.
- **Acceptance criteria**:
  - Classifica em baixo/médio/alto com justificativa.
  - Sinaliza expirado e mismatch como alto.
  - Mostra proximidade de expiração como médio.

### 10.3 Revisar histórico SSL

- **ID**: GH-SSL-003
- **Description**: Como usuário autenticado, quero revisar checks anteriores de SSL.
- **Acceptance criteria**:
  - Lista host, data/hora, severidade e status.
  - Permite filtro por período e domínio.
  - Restringe acesso à organização do usuário.

### 10.4 Segurança e limites de uso

- **ID**: GH-SSL-004
- **Description**: Como gestor da plataforma, quero acesso e uso controlados.
- **Acceptance criteria**:
  - Exige autenticação.
  - Aplica autorização por papel.
  - Aplica rate limit e auditoria de execução.
