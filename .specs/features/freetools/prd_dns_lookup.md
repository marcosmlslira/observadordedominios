# PRD: DNS Lookup

## 1. Product overview

### 1.1 Document title and version

- PRD: DNS Lookup
- Version: 1.0

### 1.2 Product summary

Este PRD define a ferramenta de DNS Lookup do Observador de Domínios para consulta pontual por clientes e uso interno operacional. O objetivo é transformar inspeção técnica de DNS em uma experiência rápida, legível e acionável.

A ferramenta deve retornar registros principais, status de resolução e sinais básicos de inconsistência. O resultado deve ser útil tanto para triagem imediata quanto para composição futura de análise consolidada.

## 2. Goals

### 2.1 Business goals

- Aumentar utilidade prática do módulo de ferramentas.
- Reduzir tempo de triagem técnica em incidentes.
- Criar base reutilizável para monitoramento contínuo.

### 2.2 User goals

- Validar rapidamente configuração DNS de um domínio.
- Identificar sinais técnicos iniciais de risco.
- Registrar evidência com timestamp para auditoria.

### 2.3 Non-goals

- Não substitui análise profunda de infraestrutura.
- Não executa correção automática de DNS.
- Não cobre monitoramento contínuo no MVP desta feature.

## 3. User personas

### 3.1 Key user types

- Analista de marca/risco
- Analista de segurança
- Operações internas

### 3.2 Basic persona details

- **Analista de marca/risco**: precisa de leitura simples para decisão rápida.
- **Analista de segurança**: precisa de dados técnicos brutos e confiáveis.
- **Operações internas**: precisa validar alertas e apoiar suporte.

### 3.3 Role-based access

- **Cliente autenticado**: executa lookup e consulta histórico próprio.
- **Operador interno**: executa lookup em casos de suporte/triagem.
- **Admin interno**: gerencia limites e observabilidade.

## 4. Functional requirements

- **Consulta de registros DNS** (Priority: Alta)
  - Buscar A, AAAA, CNAME, MX, NS e TXT.
  - Mostrar status da consulta e duração.
  - Exibir “sem registro” por tipo quando aplicável.

- **Normalização de saída** (Priority: Alta)
  - Retornar formato padronizado para UI e serviços internos.
  - Incluir timestamp de coleta e domínio consultado.

- **Sinais básicos de inconsistência** (Priority: Média)
  - Ausência de A/AAAA em domínio raiz.
  - MX ausente para domínio que aparenta uso de e-mail.
  - Nameservers ausentes ou inválidos.

- **Persistência de histórico** (Priority: Média)
  - Salvar resultado por organização.
  - Permitir recuperação para comparações futuras.

## 5. User experience

### 5.1 Entry points & first-time user flow

- Entrada na área de Ferramentas.
- Campo de domínio com validação imediata.
- Botão “Executar DNS Lookup”.

### 5.2 Core experience

- **Inserir domínio**: usuário informa o alvo.
  - Reduz fricção da consulta técnica.
- **Executar busca**: sistema consulta resolvedores.
  - Garante retorno rápido e previsível.
- **Ver resultados por tipo de registro**: usuário interpreta evidências.
  - Facilita tomada de decisão inicial.

### 5.3 Advanced features & edge cases

- Domínio malformado retorna erro orientativo.
- Timeout retorna status controlado sem travar interface.
- Falha de um tipo de consulta não invalida os demais.

### 5.4 UI/UX highlights

- Resultado em cartões por tipo de registro.
- Status visual claro: sucesso, parcial, falha.
- Mensagens objetivas e acionáveis.

## 6. Narrative

Um analista recebe um domínio suspeito e executa DNS Lookup. Em segundos, ele vê registros essenciais, status da resolução e possíveis inconsistências. Com isso, decide se prioriza investigação adicional ou encerra o caso inicial.

## 7. Success metrics

### 7.1 User-centric metrics

- Tempo médio de resposta menor que 5 segundos.
- Taxa de consultas concluídas maior que 95% para domínios válidos.

### 7.2 Business metrics

- Adoção da ferramenta por pelo menos 40% dos usuários ativos do módulo.
- Redução do tempo de triagem interna em 20%.

### 7.3 Technical metrics

- P95 de latência menor que 8 segundos.
- Taxa de erro técnico menor que 3%.

## 8. Technical considerations

### 8.1 Integration points

- Endpoint backend dedicado para DNS Lookup.
- Serviço interno reutilizável por monitoramento e triagem.
- Tela frontend com execução individual.

### 8.2 Data storage & privacy

- Armazenar somente resultado técnico necessário.
- Escopo de acesso por organização.
- Auditoria de execução interna.

### 8.3 Scalability & performance

- Cache curto por domínio/tipo de registro.
- Rate limit por organização.
- Timeout por chamada externa.

### 8.4 Potential challenges

- Diferenças entre resolvedores públicos.
- Respostas inconsistentes por região.
- Intermitência de rede externa.

## 9. Milestones & sequencing

### 9.1 Project estimate

- S: 1 a 1,5 semana

### 9.2 Team size & composition

- 2 a 3 pessoas: 1 Backend, 1 Frontend, 1 QA parcial

### 9.3 Suggested phases

- **Fase 1**: API e normalização (3 dias)
  - Endpoint funcional e contrato de resposta.
- **Fase 2**: Interface e histórico (2 a 3 dias)
  - Tela de consulta e persistência por organização.

## 10. User stories

### 10.1 Executar consulta DNS

- **ID**: GH-DNS-001
- **Description**: Como analista, quero consultar DNS para validar rapidamente infraestrutura do domínio.
- **Acceptance criteria**:
  - Exibe A/AAAA/CNAME/MX/NS/TXT quando disponíveis.
  - Mostra timestamp e duração da consulta.
  - Retorna status claro em falha/timeout.

### 10.2 Visualizar inconsistências básicas

- **ID**: GH-DNS-002
- **Description**: Como analista, quero ver alertas simples de inconsistência para priorizar investigação.
- **Acceptance criteria**:
  - Destaca ausência de registros críticos quando aplicável.
  - Não classifica risco final, apenas sinal técnico.
  - Mantém explicação curta e objetiva.

### 10.3 Revisar histórico de consultas DNS

- **ID**: GH-DNS-003
- **Description**: Como usuário autenticado, quero revisar consultas anteriores para comparação.
- **Acceptance criteria**:
  - Lista domínio, data/hora e status.
  - Permite filtro por domínio e período.
  - Restringe visualização à própria organização.

### 10.4 Garantir acesso seguro e controle de uso

- **ID**: GH-DNS-004
- **Description**: Como gestor da plataforma, quero autenticação e limites para evitar abuso.
- **Acceptance criteria**:
  - Exige usuário autenticado.
  - Aplica rate limit por organização.
  - Registra tentativas bloqueadas e auditoria interna.
