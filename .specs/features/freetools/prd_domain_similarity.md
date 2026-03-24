# PRD: Domain Similarity Generator

## 1. Product overview

### 1.1 Document title and version

- PRD: Domain Similarity Generator
- Version: 1.0

### 1.2 Product summary

Este PRD define a ferramenta de geração de domínios similares do Observador de Domínios. O objetivo é, dado um domínio legítimo (geralmente a marca do cliente), gerar sistematicamente todas as variações que um atacante poderia registrar para typosquatting, homoglyph attacks, ou brand impersonation.

Esta ferramenta é o núcleo proativo do produto: ao invés de apenas reagir a domínios suspeitos detectados, ela antecipa ameaças gerando o universo de possíveis variações e verificando quais já estão registradas.

## 2. Goals

### 2.1 Business goals

- Transformar o produto de reativo para proativo na detecção de ameaças.
- Criar o pipeline de descoberta que alimenta o monitoramento contínuo.
- Diferenciar o produto com capacidade de antecipação de typosquatting.

### 2.2 User goals

- Visualizar todas as variações possíveis da marca que poderiam ser exploradas.
- Descobrir quais variações já foram registradas.
- Priorizar monitoramento nas variações mais perigosas.

### 2.3 Non-goals

- Não registra domínios defensivamente.
- Não envia takedown requests.
- Não monitora registro de novas variações em tempo real (isso é do módulo de monitoramento contínuo).

## 3. User personas

### 3.1 Key user types

- Analista de marca/risco
- Gestor de marca
- Operações internas

### 3.2 Basic persona details

- **Analista de marca/risco**: precisa mapear superfície de ataque da marca em domínios.
- **Gestor de marca**: quer entender quantas e quais variações já existem.
- **Operações internas**: precisa alimentar listas de monitoramento.

### 3.3 Role-based access

- **Cliente autenticado**: gera variações e consulta histórico.
- **Operador interno**: gera variações para suporte de triagem.
- **Admin interno**: gerencia algoritmos e observabilidade.

## 4. Functional requirements

- **Geração de variações por typosquatting** (Priority: Alta)
  - Teclas adjacentes no teclado (ex.: `gogle.com`, `goofle.com`).
  - Omissão de caractere (ex.: `gogle.com`).
  - Duplicação de caractere (ex.: `googgle.com`).
  - Transposição de caracteres (ex.: `googel.com`).
  - Inserção de caractere (ex.: `gooogle.com`).

- **Geração de variações por homoglyph** (Priority: Alta)
  - Substituição de caracteres visualmente similares (ex.: `g00gle.com` com zeros, `googIe.com` com I maiúsculo).
  - Uso de caracteres Unicode similares (ex.: caracteres cirílicos).
  - Cobertura de substituições comuns em ataques reais.

- **Geração de variações por padrão** (Priority: Média)
  - Adição de prefixos/sufixos comuns (ex.: `google-login.com`, `google-secure.com`, `mygoogle.com`).
  - Variações de TLD (ex.: `.net`, `.org`, `.co`, `.app`, TLDs do país).
  - Subdomínio com marca (ex.: `google.dominio-malicioso.com` — detecção por padrão de subdomain).
  - Combinação com palavras de urgência (ex.: `google-alert.com`, `google-verify.com`).

- **Verificação de registro** (Priority: Alta)
  - Para cada variação gerada, verificar se o domínio está registrado (DNS resolve ou WHOIS ativo).
  - Classificar: registrado / não registrado / indeterminado.
  - Priorizar verificação nas variações mais prováveis (score de plausibilidade).

- **Classificação e priorização** (Priority: Média)
  - Atribuir score de plausibilidade a cada variação (quão provável é que um atacante use essa variação).
  - Ordenar resultados por: registrado primeiro, depois por plausibilidade.
  - Agrupar por tipo de variação (typo, homoglyph, padrão).

- **Persistência de histórico** (Priority: Média)
  - Salvar resultado por organização e domínio base.
  - Permitir comparação temporal (quais variações foram registradas desde a última verificação).

## 5. User experience

### 5.1 Entry points & first-time user flow

- Entrada na área de Ferramentas.
- Campo de domínio com label "Domínio da sua marca".
- Botão "Gerar Variações Similares".

### 5.2 Core experience

- **Inserir domínio base**: usuário informa o domínio legítimo da marca.
  - Validação de formato.
- **Gerar variações**: sistema produz lista de variações por categoria.
  - Loading progressivo enquanto verifica registros.
- **Ver resultados**: lista organizada por tipo e status de registro.
  - Foco nos registrados — são as ameaças ativas.

### 5.3 Advanced features & edge cases

- Marcas curtas (2-3 caracteres) geram poucas variações úteis — sinalizar.
- Marcas com caracteres especiais ou hífens expandem significativamente o espaço.
- Verificação de registro em massa pode levar tempo — execução assíncrona com notificação.
- Limitar geração a um máximo razoável (ex.: 500 variações) para evitar sobrecarga.

### 5.4 UI/UX highlights

- Tabs ou filtros por tipo de variação (typo / homoglyph / padrão).
- Badge de status: registrado (vermelho), não registrado (verde), indeterminado (cinza).
- Contadores por categoria e status.
- Ação rápida para executar Quick Analysis em domínios registrados.
- Exportação da lista para CSV/PDF para relatórios.

## 6. Narrative

O gestor de marca configura o domínio principal da empresa. O sistema gera 200+ variações possíveis e descobre que 12 já estão registradas. Três delas foram registradas na última semana e resolvem para IPs ativos. Essas são priorizadas para investigação imediata com as demais ferramentas (Screenshot, SSL, Headers, Blacklist). As variações não registradas são adicionadas à watchlist de monitoramento contínuo.

## 7. Success metrics

### 7.1 User-centric metrics

- Tempo de geração de variações menor que 5 segundos.
- Tempo de verificação completa de registros menor que 60 segundos (para até 200 variações).
- 90%+ dos usuários compreendem a categorização na primeira leitura.

### 7.2 Business metrics

- Adoção por pelo menos 60% dos usuários ativos — é a ferramenta mais diretamente ligada à proposta de valor.
- Pelo menos 20% das variações registradas detectadas levam a investigação adicional.
- Conversão para monitoramento contínuo em pelo menos 30% dos usuários.

### 7.3 Technical metrics

- P95 de latência para geração menor que 8 segundos.
- P95 de latência para verificação completa menor que 90 segundos.
- Taxa de erro técnico menor que 3%.

## 8. Technical considerations

### 8.1 Integration points

- Endpoint backend dedicado para Domain Similarity Generator.
- Reutiliza DNS Lookup e WHOIS internamente para verificação de registro.
- Alimenta módulo de monitoramento contínuo (watchlist).
- Composição com Quick Analysis para investigação de variações registradas.

### 8.2 Data storage & privacy

- Armazenar variações geradas, status e score por organização.
- Escopo de acesso por organização.
- Auditoria de execução interna.

### 8.3 Scalability & performance

- Geração de variações é CPU-bound — executar em background worker.
- Verificação de registro em batch com rate limiting.
- Cache de status de registro por domínio (1-6 horas).
- Rate limit por organização com limite de execuções por período.

### 8.4 Potential challenges

- Espaço de variações pode ser muito grande para marcas longas.
- Verificação de registro em massa pode triggerar rate limiting de WHOIS/DNS.
- Equilibrar cobertura vs. performance na quantidade de variações.
- Homoglyphs Unicode podem não ser suportados em todos os TLDs.

## 9. Milestones & sequencing

### 9.1 Project estimate

- M: 2 a 3 semanas

### 9.2 Team size & composition

- 3 a 4 pessoas: 1 Backend (algoritmos), 1 Backend (verificação), 1 Frontend, 1 QA parcial

### 9.3 Suggested phases

- **Fase 1**: Algoritmos de geração (4 a 5 dias)
  - Typosquatting, homoglyphs, padrões. Engine de variações com score.
- **Fase 2**: Verificação de registro em batch (3 a 4 dias)
  - DNS resolve + WHOIS check em paralelo, rate limiting, cache.
- **Fase 3**: Interface e integração (3 a 4 dias)
  - Tela de resultados, filtros, ações rápidas, exportação, persistência.

## 10. User stories

### 10.1 Gerar variações de typosquatting

- **ID**: GH-SIM-001
- **Description**: Como analista, quero gerar variações de typosquatting do domínio da marca para mapear superfície de ataque.
- **Acceptance criteria**:
  - Gera variações por tecla adjacente, omissão, duplicação, transposição e inserção.
  - Atribui score de plausibilidade a cada variação.
  - Agrupa por tipo de variação.

### 10.2 Gerar variações de homoglyph

- **ID**: GH-SIM-002
- **Description**: Como analista, quero ver variações com caracteres visualmente similares para detectar ataques sofisticados.
- **Acceptance criteria**:
  - Gera substituições com dígitos, maiúsculas confusas e Unicode similares.
  - Indica quais caracteres foram substituídos.
  - Score reflete dificuldade de detecção visual.

### 10.3 Verificar status de registro

- **ID**: GH-SIM-003
- **Description**: Como analista, quero saber quais variações já estão registradas para priorizar investigação.
- **Acceptance criteria**:
  - Verifica registro via DNS e/ou WHOIS.
  - Classifica: registrado / não registrado / indeterminado.
  - Ordena com registrados primeiro.

### 10.4 Investigar variação registrada

- **ID**: GH-SIM-004
- **Description**: Como analista, quero executar análise completa em variações registradas para avaliar risco.
- **Acceptance criteria**:
  - Ação rápida para Quick Analysis no domínio selecionado.
  - Navegação sem perder contexto da lista de variações.
  - Resultado da análise associado à variação de origem.

### 10.5 Exportar resultados

- **ID**: GH-SIM-005
- **Description**: Como gestor de marca, quero exportar a lista de variações para incluir em relatórios internos.
- **Acceptance criteria**:
  - Exporta em CSV e/ou PDF.
  - Inclui domínio base, variação, tipo, status e score.
  - Respeita filtros aplicados na interface.

### 10.6 Comparar com execução anterior

- **ID**: GH-SIM-006
- **Description**: Como analista, quero comparar com a última execução para detectar novos registros.
- **Acceptance criteria**:
  - Destaca variações recém-registradas (não estavam registradas antes).
  - Indica data da última verificação.
  - Restringe à própria organização.
