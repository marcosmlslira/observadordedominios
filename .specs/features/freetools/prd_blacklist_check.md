# PRD: Blacklist Check

## 1. Product overview

### 1.1 Document title and version

- PRD: Blacklist Check
- Version: 1.0

### 1.2 Product summary

Este PRD define a ferramenta de verificação de blacklists do Observador de Domínios. O objetivo é consultar listas negras públicas e conhecidas (DNSBL, SURBL, Spamhaus, etc.) para determinar se um domínio ou IP já foi reportado como malicioso, spam ou abusivo.

A presença em blacklists é um dos sinais mais fortes de risco. Um domínio recém-registrado similar à marca do cliente que já aparece em blacklists é evidência quase conclusiva de atividade maliciosa.

## 2. Goals

### 2.1 Business goals

- Fornecer sinal de alta confiança para o score de risco.
- Reduzir falsos positivos na triagem — blacklists são evidência concreta.
- Diferenciar o produto de ferramentas genéricas de lookup.

### 2.2 User goals

- Verificar rapidamente se um domínio suspeito já é conhecido como malicioso.
- Obter evidência objetiva para justificar ações de proteção de marca.
- Consolidar múltiplas fontes de blacklist em uma única consulta.

### 2.3 Non-goals

- Não solicita remoção de blacklists.
- Não monitora inclusão/remoção de blacklists em tempo real.
- Não substitui threat intelligence feeds premium.

## 3. User personas

### 3.1 Key user types

- Analista de marca/risco
- Analista de segurança
- Operações internas

### 3.2 Basic persona details

- **Analista de marca/risco**: precisa de confirmação rápida se domínio suspeito já foi flagged.
- **Analista de segurança**: precisa saber em quais listas específicas o domínio aparece.
- **Operações internas**: precisa de evidência documentada para escalar casos.

### 3.3 Role-based access

- **Cliente autenticado**: executa verificação e consulta histórico próprio.
- **Operador interno**: executa verificação em casos de suporte/triagem.
- **Admin interno**: gerencia fontes de blacklist e observabilidade.

## 4. Functional requirements

- **Consulta a múltiplas blacklists** (Priority: Alta)
  - Consultar pelo menos 5 fontes DNSBL reconhecidas (ex.: Spamhaus ZEN, SURBL, Barracuda, SpamCop, URIBL).
  - Resolver domínio para IP e consultar tanto domínio quanto IP.
  - Retornar status por lista: listado / não listado / indisponível.

- **Consolidação de resultado** (Priority: Alta)
  - Classificar resultado geral: limpo / parcialmente listado / amplamente listado.
  - Indicar quantidade de listas onde aparece vs. total consultado.
  - Exibir nome da lista e categoria quando disponível (spam, malware, phishing).

- **Detalhes por lista** (Priority: Média)
  - Mostrar código de retorno DNSBL quando aplicável.
  - Indicar categoria da listagem (spam, botnet, phishing, malware).
  - Link para página de lookup da lista original quando disponível.

- **Persistência de histórico** (Priority: Média)
  - Salvar resultado por organização.
  - Permitir comparação temporal (estava limpo ontem, listado hoje).

## 5. User experience

### 5.1 Entry points & first-time user flow

- Entrada na área de Ferramentas.
- Campo de domínio ou IP com validação imediata.
- Botão "Verificar Blacklists".

### 5.2 Core experience

- **Inserir domínio/IP**: usuário informa o alvo.
  - Aceita domínio, subdomínio ou endereço IP.
- **Executar verificação**: sistema consulta múltiplas fontes em paralelo.
  - Loading progressivo por lista consultada.
- **Ver resultado consolidado**: status geral + detalhamento por lista.
  - Decisão rápida sobre nível de risco.

### 5.3 Advanced features & edge cases

- Listas indisponíveis não invalidam resultado geral — indicar parcialidade.
- Domínios muito novos podem não estar em nenhuma lista — isso não significa "seguro".
- Timeout por lista individual (3 segundos) para não travar resultado.

### 5.4 UI/UX highlights

- Indicador visual consolidado: verde (limpo), amarelo (parcial), vermelho (amplamente listado).
- Lista expandível com detalhes por fonte.
- Badge com contagem: "Listado em X de Y fontes".

## 6. Narrative

Um analista detecta um domínio similar à marca do cliente registrado há 3 dias. Executa o Blacklist Check e descobre que o domínio já aparece em 3 de 8 listas consultadas, categorizado como phishing. Essa evidência concreta justifica ação imediata e eleva o score de risco automaticamente.

## 7. Success metrics

### 7.1 User-centric metrics

- Tempo médio de resposta menor que 8 segundos (consulta paralela).
- Taxa de verificações concluídas maior que 90%.

### 7.2 Business metrics

- Adoção por pelo menos 50% dos usuários ativos do módulo.
- Contribuição para score de risco em pelo menos 70% das análises consolidadas.

### 7.3 Technical metrics

- P95 de latência menor que 12 segundos.
- Taxa de erro técnico menor que 5% (excluindo indisponibilidade de listas externas).

## 8. Technical considerations

### 8.1 Integration points

- Endpoint backend dedicado para Blacklist Check.
- Consultas via DNS (DNSBL) — leve e rápido.
- Composição com Quick Analysis e motor de score de risco.

### 8.2 Data storage & privacy

- Armazenar resultado por lista e classificação geral.
- Escopo de acesso por organização.
- Auditoria de execução interna.

### 8.3 Scalability & performance

- Consultas DNSBL em paralelo (async).
- Cache curto por domínio/IP (5-10 minutos).
- Rate limit por organização.
- Timeout individual por lista (3 segundos).

### 8.4 Potential challenges

- Listas DNSBL podem ter intermitência ou rate limiting próprio.
- Falsos positivos em listas menos rigorosas.
- Alguns provedores de blacklist limitam consultas por IP de origem.

## 9. Milestones & sequencing

### 9.1 Project estimate

- S: 1 semana

### 9.2 Team size & composition

- 2 pessoas: 1 Backend, 1 Frontend

### 9.3 Suggested phases

- **Fase 1**: API e consulta DNSBL (2 a 3 dias)
  - Integração com 5+ listas, consulta paralela, consolidação.
- **Fase 2**: Interface e histórico (2 dias)
  - Tela de resultados, indicadores visuais, persistência.

## 10. User stories

### 10.1 Verificar domínio em blacklists

- **ID**: GH-BLC-001
- **Description**: Como analista, quero verificar se um domínio está em blacklists para confirmar atividade maliciosa conhecida.
- **Acceptance criteria**:
  - Consulta pelo menos 5 fontes DNSBL.
  - Mostra status por lista: listado / não listado / indisponível.
  - Classifica resultado geral: limpo / parcial / amplamente listado.

### 10.2 Ver detalhes de listagem

- **ID**: GH-BLC-002
- **Description**: Como analista, quero ver em quais listas específicas o domínio aparece para entender o tipo de ameaça.
- **Acceptance criteria**:
  - Mostra nome da lista e categoria (spam, phishing, malware).
  - Indica código de retorno quando disponível.
  - Fornece link para lookup original quando possível.

### 10.3 Comparar status temporal

- **ID**: GH-BLC-003
- **Description**: Como usuário autenticado, quero comparar resultados ao longo do tempo para detectar mudanças.
- **Acceptance criteria**:
  - Lista verificações anteriores com data/hora e status geral.
  - Permite filtro por domínio e período.
  - Restringe visualização à própria organização.
