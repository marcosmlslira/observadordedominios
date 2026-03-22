# PRD: Detector de página suspeita

## 1. Product overview

### 1.1 Document title and version

- PRD: Detector de página suspeita
- Version: 1.0

### 1.2 Product summary

Este PRD define a ferramenta de detecção de página suspeita para classificar risco básico a partir de sinais observáveis no conteúdo da página. A feature deve gerar uma classificação simples e justificável para acelerar triagem.

O detector é voltado para uso por clientes e operação interna, sem pretensão de substituir motores avançados de threat intelligence no MVP.

## 2. Goals

### 2.1 Business goals

- Oferecer camada prática de priorização de risco no módulo de ferramentas.
- Reduzir tempo de decisão inicial em investigações.
- Criar base para evolução futura de regras e modelos.

### 2.2 User goals

- Receber classificação clara de risco (baixo/médio/alto).
- Entender os sinais que levaram à classificação.
- Agir rapidamente com recomendações iniciais.

### 2.3 Non-goals

- Não garante detecção perfeita de phishing.
- Não substitui análise humana especializada.
- Não usa, no MVP, modelos complexos de ML em produção.

## 3. User personas

### 3.1 Key user types

- Analista de marca/risco
- Analista de segurança
- Operações internas

### 3.2 Basic persona details

- **Analista de marca/risco**: precisa de score simples com justificativas compreensíveis.
- **Analista de segurança**: precisa rastreabilidade de sinais detectados.
- **Operações internas**: precisa priorizar filas de atendimento e investigação.

### 3.3 Role-based access

- **Cliente autenticado**: executa classificação e vê justificativas.
- **Operador interno**: usa classificação em triagem de casos.
- **Admin interno**: ajusta parâmetros de regras e monitora performance.

## 4. Functional requirements

- **Classificação de risco básica** (Priority: Alta)
  - Classificar página em baixo, médio ou alto.
  - Retornar estado “não conclusivo” quando houver dados insuficientes.

- **Regras iniciais de detecção** (Priority: Alta)
  - Termos sensíveis de credenciais (senha, login, token, etc.).
  - Sinais de imitação de marca (nome e identidade textual básica).
  - Padrões de formulário de login suspeito.
  - Redirecionamentos anômalos observados na navegação.

- **Explicabilidade mínima** (Priority: Alta)
  - Listar quais sinais foram acionados.
  - Exibir peso relativo por sinal (baixo/médio/alto impacto).

- **Persistência de resultado** (Priority: Média)
  - Salvar classificação e sinais por organização.
  - Permitir revisão histórica para auditoria.

## 5. User experience

### 5.1 Entry points & first-time user flow

- Acesso no menu Ferramentas.
- Informar domínio/URL.
- Botão “Analisar página suspeita”.

### 5.2 Core experience

- **Executar análise**: sistema coleta sinais relevantes.
  - Reduz esforço manual de interpretação inicial.
- **Receber classificação**: usuário vê nível de risco.
  - Acelera priorização de ações.
- **Ler justificativas**: usuário entende por que o risco foi atribuído.
  - Aumenta confiança e transparência do resultado.

### 5.3 Advanced features & edge cases

- Página indisponível retorna “não conclusivo”.
- Conteúdo insuficiente ou bloqueado mantém rastreio de tentativa.
- Sinais conflitantes retornam classificação intermediária com justificativa.

### 5.4 UI/UX highlights

- Badge de risco com cor semântica.
- Lista curta de sinais detectados.
- Bloco “o que fazer agora” com próxima ação sugerida.

## 6. Narrative

Após consultar um domínio suspeito, o analista executa o detector e recebe rapidamente um nível de risco acompanhado dos sinais encontrados. Com transparência sobre os critérios, ele decide se escala para investigação aprofundada ou acompanha o caso no histórico.

## 7. Success metrics

### 7.1 User-centric metrics

- Tempo médio de análise menor que 10 segundos.
- Taxa de entendimento das justificativas acima de 85%.

### 7.2 Business metrics

- Redução de tempo médio de triagem inicial.
- Aumento de uso recorrente em fluxos de validação.

### 7.3 Technical metrics

- P95 de execução menor que 15 segundos.
- Taxa de “não conclusivo” abaixo de 20% em domínios acessíveis.

## 8. Technical considerations

### 8.1 Integration points

- Endpoint backend de classificação.
- Serviço de regras de detecção com pesos configuráveis.
- Frontend com visualização de risco e justificativas.

### 8.2 Data storage & privacy

- Armazenar somente sinais e metadados necessários.
- Evitar retenção indevida de conteúdo sensível.
- Segregação estrita por organização.

### 8.3 Scalability & performance

- Execução assíncrona com timeout.
- Cache curto por URL quando apropriado.
- Limites por organização para controle de custo.

### 8.4 Potential challenges

- Falsos positivos em páginas legítimas com formulários.
- Falsos negativos em páginas obfuscadas.
- Mudanças frequentes de layout em páginas maliciosas.

## 9. Milestones & sequencing

### 9.1 Project estimate

- M: 1,5 a 2 semanas

### 9.2 Team size & composition

- 3 a 4 pessoas: 2 Backend, 1 Frontend, 1 QA parcial

### 9.3 Suggested phases

- **Fase 1**: Motor de regras e classificação (4 dias)
  - Implementação de regras iniciais e escore.
- **Fase 2**: UX explicável e histórico (3 a 4 dias)
  - Exibição de justificativas e persistência.

## 10. User stories

### 10.1 Classificar risco da página

- **ID**: GH-SUSP-001
- **Description**: Como analista, quero classificar risco para priorizar investigação.
- **Acceptance criteria**:
  - Retorna baixo/médio/alto para páginas analisáveis.
  - Retorna “não conclusivo” com justificativa em dados insuficientes.
  - Registra timestamp e URL analisada.

### 10.2 Entender sinais detectados

- **ID**: GH-SUSP-002
- **Description**: Como analista, quero ver sinais que explicam o risco atribuído.
- **Acceptance criteria**:
  - Lista sinais acionados de forma objetiva.
  - Exibe impacto relativo por sinal.
  - Mantém consistência de explicação entre execuções equivalentes.

### 10.3 Revisar histórico de classificações

- **ID**: GH-SUSP-003
- **Description**: Como usuário autenticado, quero revisar classificações anteriores.
- **Acceptance criteria**:
  - Lista domínio, data/hora, risco e status.
  - Permite filtro por período e domínio.
  - Restringe acesso à organização do usuário.

### 10.4 Segurança e autorização

- **ID**: GH-SUSP-004
- **Description**: Como gestor da plataforma, quero acesso controlado ao detector.
- **Acceptance criteria**:
  - Exige autenticação.
  - Aplica autorização por perfil.
  - Registra auditoria e rate limit por organização.
