# PRD: WHOIS

## 1. Product overview

### 1.1 Document title and version

- PRD: WHOIS
- Version: 1.0

### 1.2 Product summary

Este PRD define a ferramenta WHOIS para consulta pontual de dados de registro de domínios no Observador de Domínios. A ferramenta deve oferecer leitura simplificada de informações essenciais e deixar explícitas limitações de disponibilidade por TLD.

O uso é voltado para clientes e operação interna, com foco em rapidez de triagem e geração de evidência inicial sobre contexto de registro.

## 2. Goals

### 2.1 Business goals

- Entregar visibilidade de contexto de registro sem depender de fontes externas manuais.
- Aumentar percepção de valor do módulo de ferramentas.
- Reduzir esforço operacional em investigações iniciais.

### 2.2 User goals

- Ver idade e status do domínio de forma rápida.
- Entender disponibilidade/limitação dos dados de registro.
- Guardar histórico consultável por organização.

### 2.3 Non-goals

- Não garante completude dos dados para todas as TLDs.
- Não realiza enriquecimento avançado de inteligência externa.
- Não substitui análise jurídica especializada.

## 3. User personas

### 3.1 Key user types

- Analista de marca/risco
- Analista de segurança
- Operações internas

### 3.2 Basic persona details

- **Analista de marca/risco**: precisa de sinais claros sobre registro recente e status.
- **Analista de segurança**: precisa de campos técnicos normalizados.
- **Operações internas**: precisa de evidência rápida para atendimento.

### 3.3 Role-based access

- **Cliente autenticado**: executa consulta WHOIS e histórico próprio.
- **Operador interno**: consulta em contexto de incidente/atendimento.
- **Admin interno**: configura limites e monitora uso.

## 4. Functional requirements

- **Consulta WHOIS essencial** (Priority: Alta)
  - Retornar registrador, datas relevantes, status e nameservers quando disponíveis.
  - Exibir timestamp da coleta.

- **Normalização de campos** (Priority: Alta)
  - Padronizar chaves de saída para frontend e serviços internos.
  - Tratar ausência de dados com status explícito.

- **Transparência de indisponibilidade** (Priority: Alta)
  - Informar quando TLD/política de privacidade reduzir dados.
  - Diferenciar falha técnica de indisponibilidade regulatória.

- **Persistência por organização** (Priority: Média)
  - Salvar consultas e status para auditoria e comparação.

## 5. User experience

### 5.1 Entry points & first-time user flow

- Acesso via menu Ferramentas.
- Campo de domínio com validação.
- Botão “Executar WHOIS”.

### 5.2 Core experience

- **Informar domínio**: usuário define alvo da consulta.
  - Mantém fluxo simples e rápido.
- **Executar WHOIS**: backend consulta fonte de registro.
  - Fornece contexto inicial de registro.
- **Interpretar resultado**: usuário vê dados e limitações.
  - Evita conclusões erradas por dados ausentes.

### 5.3 Advanced features & edge cases

- TLD sem dados públicos retorna “indisponível”.
- Timeout/falha externa retorna erro controlado.
- Domínio inválido retorna orientação de correção.

### 5.4 UI/UX highlights

- Blocos de dados por categoria (registro, datas, status).
- Destaque para data de criação e expiração.
- Mensagem explícita em casos de limitação.

## 6. Narrative

Ao investigar um domínio suspeito, o analista executa WHOIS para entender quando foi registrado, por quem e em que estado está. Mesmo quando parte dos dados não estiver disponível, o sistema explica o motivo e mantém o fluxo de decisão claro.

## 7. Success metrics

### 7.1 User-centric metrics

- Tempo médio de resposta menor que 8 segundos.
- Taxa de compreensão de resultado (pesquisa rápida) acima de 85%.

### 7.2 Business metrics

- Aumento de uso recorrente da ferramenta em contas ativas.
- Redução de abertura de chamados por dúvida de contexto de domínio.

### 7.3 Technical metrics

- P95 de latência menor que 12 segundos.
- Taxa de falha técnica menor que 5%.

## 8. Technical considerations

### 8.1 Integration points

- Endpoint de WHOIS no backend.
- Serviço de normalização de resposta.
- Consumo frontend em tela de ferramenta individual.

### 8.2 Data storage & privacy

- Persistir apenas campos necessários à investigação.
- Escopo de acesso por organização.
- Auditoria de uso interno e externo.

### 8.3 Scalability & performance

- Cache curto para repetição de consulta.
- Limites por organização.
- Timeouts por provedor externo.

### 8.4 Potential challenges

- Inconsistência entre provedores e TLDs.
- Campos redigidos por privacidade.
- Variação de formato de resposta.

## 9. Milestones & sequencing

### 9.1 Project estimate

- S: 1 a 1,5 semana

### 9.2 Team size & composition

- 2 a 3 pessoas: 1 Backend, 1 Frontend, 1 QA parcial

### 9.3 Suggested phases

- **Fase 1**: Integração e normalização (3 dias)
  - Endpoint + parser de resposta padronizado.
- **Fase 2**: UI, histórico e observabilidade (2 a 3 dias)
  - Tela de resultados e persistência por organização.

## 10. User stories

### 10.1 Executar consulta WHOIS

- **ID**: GH-WHOIS-001
- **Description**: Como analista, quero consultar WHOIS para entender contexto de registro.
- **Acceptance criteria**:
  - Exibe registrador, datas, status e nameservers quando disponíveis.
  - Mostra timestamp da coleta.
  - Exibe status claro em falha técnica.

### 10.2 Entender limitações por TLD

- **ID**: GH-WHOIS-002
- **Description**: Como analista, quero saber quando a ausência de dados é limitação da fonte.
- **Acceptance criteria**:
  - Diferencia indisponibilidade regulatória de erro técnico.
  - Mostra mensagem objetiva de limitação.
  - Mantém estrutura de resposta consistente.

### 10.3 Revisar histórico WHOIS

- **ID**: GH-WHOIS-003
- **Description**: Como usuário autenticado, quero revisar consultas WHOIS anteriores.
- **Acceptance criteria**:
  - Lista domínio, data/hora, status e resumo.
  - Permite filtro por domínio e período.
  - Restringe visualização à própria organização.

### 10.4 Segurança e controle de acesso

- **ID**: GH-WHOIS-004
- **Description**: Como gestor da plataforma, quero acesso controlado ao WHOIS.
- **Acceptance criteria**:
  - Exige autenticação para execução.
  - Aplica permissão por papel (cliente/interno/admin).
  - Aplica rate limit por organização.
