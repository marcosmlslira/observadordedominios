# PRD: Screenshot de página

## 1. Product overview

### 1.1 Document title and version

- PRD: Screenshot de página
- Version: 1.0

### 1.2 Product summary

Este PRD define a ferramenta de captura de screenshot da página inicial de domínios no Observador de Domínios. A feature serve como evidência visual para triagem, suporte, segurança e contexto jurídico inicial.

A captura deve ser resiliente, com status explícito de sucesso/falha, timeout controlado e persistência por organização.

## 2. Goals

### 2.1 Business goals

- Fornecer evidência visual prática para investigações.
- Reduzir tempo de comunicação entre times em casos suspeitos.
- Aumentar valor percebido do módulo de ferramentas.

### 2.2 User goals

- Obter imagem atual da página alvo rapidamente.
- Entender se houve bloqueio, timeout ou carregamento normal.
- Recuperar histórico visual para comparação.

### 2.3 Non-goals

- Não faz crawling completo do site.
- Não garante bypass de mecanismos anti-bot.
- Não substitui coleta forense avançada.

## 3. User personas

### 3.1 Key user types

- Analista de marca/risco
- Analista de segurança
- Operações internas e suporte

### 3.2 Basic persona details

- **Analista de marca/risco**: precisa de evidência visual para decisão e reporte.
- **Analista de segurança**: precisa correlacionar imagem com sinais técnicos.
- **Operações internas e suporte**: precisa comprovar estado da página no atendimento.

### 3.3 Role-based access

- **Cliente autenticado**: captura e visualiza evidências da própria organização.
- **Operador interno**: captura em contexto de caso/suporte.
- **Admin interno**: configura retenção e políticas operacionais.

## 4. Functional requirements

- **Captura de página inicial** (Priority: Alta)
  - Renderizar URL alvo e gerar screenshot.
  - Registrar resolução, horário e URL final após redirecionamento.

- **Status de execução** (Priority: Alta)
  - Sucesso, timeout, bloqueado, erro de navegação.
  - Mensagem curta e acionável por status.

- **Persistência e recuperação** (Priority: Média)
  - Salvar evidência com metadados por organização.
  - Permitir visualização posterior no histórico.

- **Controle operacional** (Priority: Média)
  - Timeout máximo configurável.
  - Isolamento de execução para evitar travas.

## 5. User experience

### 5.1 Entry points & first-time user flow

- Acesso na área Ferramentas.
- Inserção de domínio/URL.
- Botão “Capturar Screenshot”.

### 5.2 Core experience

- **Informar domínio**: usuário define alvo.
  - Simplifica início da coleta visual.
- **Executar captura**: sistema processa renderização.
  - Garante evidência rápida para análise.
- **Visualizar resultado**: usuário vê imagem e status.
  - Facilita comunicação e priorização.

### 5.3 Advanced features & edge cases

- Página indisponível retorna erro de navegação.
- Timeout retorna estado claro sem travar fluxo.
- Bloqueio anti-bot retorna status específico.

### 5.4 UI/UX highlights

- Preview da imagem com metadados essenciais.
- Status visual consistente com demais ferramentas.
- Ação rápida para abrir no histórico.

## 6. Narrative

Ao validar um domínio suspeito, o usuário executa screenshot e recebe uma evidência visual do estado atual da página. Mesmo em caso de bloqueio ou timeout, o sistema retorna status claro, mantendo rastreabilidade da tentativa e contexto para investigação.

## 7. Success metrics

### 7.1 User-centric metrics

- Taxa de captura bem-sucedida maior que 85% em domínios acessíveis.
- Tempo médio de captura menor que 12 segundos.

### 7.2 Business metrics

- Aumento de uso da funcionalidade em fluxos de triagem.
- Redução de tempo de resposta em suporte de incidentes.

### 7.3 Technical metrics

- P95 de execução menor que 20 segundos.
- Taxa de falha técnica (exceto anti-bot) menor que 5%.

## 8. Technical considerations

### 8.1 Integration points

- Endpoint backend para solicitar captura.
- Worker/fila para execução de renderização.
- Frontend com exibição de evidência e status.

### 8.2 Data storage & privacy

- Armazenar imagem e metadados mínimos.
- Política de retenção configurável por organização/plano.
- Controle de acesso estrito por organização.

### 8.3 Scalability & performance

- Fila para absorver picos.
- Limite de concorrência por organização.
- Timeouts e cancelamento de job estagnado.

### 8.4 Potential challenges

- Bloqueios anti-automação.
- Alto custo computacional em volume elevado.
- Variações de renderização por conteúdo dinâmico.

## 9. Milestones & sequencing

### 9.1 Project estimate

- M: 1,5 a 2 semanas

### 9.2 Team size & composition

- 3 a 4 pessoas: 2 Backend, 1 Frontend, 1 QA parcial

### 9.3 Suggested phases

- **Fase 1**: Pipeline de captura e status (4 dias)
  - Endpoint, execução e contratos de retorno.
- **Fase 2**: Persistência, histórico e UX (3 a 4 dias)
  - Armazenamento, visualização e filtros básicos.

## 10. User stories

### 10.1 Capturar evidência visual

- **ID**: GH-SHOT-001
- **Description**: Como analista, quero capturar screenshot para registrar evidência visual.
- **Acceptance criteria**:
  - Gera imagem da página inicial quando acessível.
  - Registra data/hora e URL final.
  - Exibe status de sucesso ao concluir.

### 10.2 Tratar falhas de navegação

- **ID**: GH-SHOT-002
- **Description**: Como analista, quero saber por que a captura falhou.
- **Acceptance criteria**:
  - Diferencia timeout, bloqueio e erro de navegação.
  - Exibe mensagem objetiva para cada status.
  - Não interrompe uso de outras ferramentas.

### 10.3 Revisar histórico de screenshots

- **ID**: GH-SHOT-003
- **Description**: Como usuário autenticado, quero revisar capturas anteriores.
- **Acceptance criteria**:
  - Lista domínio, data/hora e status.
  - Permite abrir imagem salva da própria organização.
  - Suporta filtro por período e domínio.

### 10.4 Segurança e governança de acesso

- **ID**: GH-SHOT-004
- **Description**: Como gestor da plataforma, quero proteger acesso às evidências.
- **Acceptance criteria**:
  - Exige autenticação e autorização por papel.
  - Restringe acesso às evidências por organização.
  - Registra auditoria de execução e visualização interna.
