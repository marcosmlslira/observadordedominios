# PRD: HTTP Headers Analysis

## 1. Product overview

### 1.1 Document title and version

- PRD: HTTP Headers Analysis
- Version: 1.0

### 1.2 Product summary

Este PRD define a ferramenta de análise de HTTP Headers do Observador de Domínios. O objetivo é inspecionar os cabeçalhos de resposta HTTP de um domínio para identificar sinais de segurança, fingerprinting de servidor e comportamento de redirecionamento.

Headers HTTP revelam informações valiosas sobre a infraestrutura do domínio alvo: presença ou ausência de headers de segurança (CSP, HSTS, X-Frame-Options), tecnologias expostas (Server, X-Powered-By), e cadeias de redirecionamento que podem indicar phishing ou cloaking.

## 2. Goals

### 2.1 Business goals

- Complementar a análise técnica com sinais de segurança do servidor.
- Enriquecer o score de risco com dados de configuração HTTP.
- Fornecer evidência técnica adicional para triagem de domínios suspeitos.

### 2.2 User goals

- Identificar rapidamente se um domínio tem configuração de segurança mínima.
- Detectar tecnologias e servidores expostos que indiquem infraestrutura amadora ou maliciosa.
- Visualizar cadeia completa de redirecionamentos para detectar cloaking.

### 2.3 Non-goals

- Não realiza scan de vulnerabilidades no servidor.
- Não testa payloads de ataque.
- Não substitui ferramentas especializadas de pentest.

## 3. User personas

### 3.1 Key user types

- Analista de marca/risco
- Analista de segurança
- Operações internas

### 3.2 Basic persona details

- **Analista de marca/risco**: precisa entender se o domínio suspeito tem configuração profissional ou amadora.
- **Analista de segurança**: precisa de dados brutos de headers para análise técnica.
- **Operações internas**: precisa validar alertas com contexto adicional de infraestrutura.

### 3.3 Role-based access

- **Cliente autenticado**: executa análise e consulta histórico próprio.
- **Operador interno**: executa análise em casos de suporte/triagem.
- **Admin interno**: gerencia limites e observabilidade.

## 4. Functional requirements

- **Coleta de headers HTTP** (Priority: Alta)
  - Realizar requisição HEAD/GET ao domínio alvo (HTTP e HTTPS).
  - Capturar todos os headers de resposta.
  - Seguir redirecionamentos e registrar cada hop da cadeia.
  - Registrar status code final e intermediários.

- **Análise de security headers** (Priority: Alta)
  - Verificar presença/ausência de: `Strict-Transport-Security`, `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `X-XSS-Protection`, `Referrer-Policy`, `Permissions-Policy`.
  - Classificar cada header como: presente (com valor), ausente, ou mal configurado.
  - Gerar score simplificado de segurança: bom / razoável / fraco.

- **Fingerprinting de servidor** (Priority: Média)
  - Extrair informações de `Server`, `X-Powered-By`, `X-Generator` e headers similares.
  - Identificar tecnologias expostas (Apache, Nginx, IIS, PHP, WordPress etc.).
  - Sinalizar quando informações de versão estão expostas (risco informacional).

- **Cadeia de redirecionamentos** (Priority: Média)
  - Registrar URL inicial, cada redirecionamento (301/302/307/308) e URL final.
  - Sinalizar: mudança de protocolo (HTTP→HTTPS ou vice-versa), redirecionamento para domínio diferente, cadeias longas (>3 hops).
  - Exibir cadeia visual de forma clara.

- **Persistência de histórico** (Priority: Média)
  - Salvar resultado por organização.
  - Permitir comparação com execuções anteriores.

## 5. User experience

### 5.1 Entry points & first-time user flow

- Entrada na área de Ferramentas.
- Campo de domínio com validação imediata.
- Botão "Analisar Headers HTTP".

### 5.2 Core experience

- **Inserir domínio**: usuário informa o alvo.
  - Aceita domínio ou URL completa.
- **Executar análise**: sistema faz requisição e coleta headers.
  - Retorno rápido com resultado estruturado.
- **Ver resultados**: três blocos — security headers, fingerprint, redirecionamentos.
  - Facilita interpretação por nível de experiência.

### 5.3 Advanced features & edge cases

- Domínio sem resposta HTTP retorna status controlado.
- Timeout configurável (padrão: 10 segundos por hop).
- Sites com proteção anti-bot podem retornar headers parciais — sinalizar explicitamente.

### 5.4 UI/UX highlights

- Cartão de security headers com indicadores visuais (presente/ausente/alerta).
- Lista de tecnologias detectadas com ícones quando possível.
- Timeline visual da cadeia de redirecionamentos.

## 6. Narrative

Um analista investiga um domínio recém-detectado. Após ver o DNS e WHOIS, executa a análise de headers. Percebe que o site não tem HSTS, expõe versão do Apache e redireciona de HTTP para um domínio completamente diferente. Esses sinais combinados elevam o score de risco e justificam investigação aprofundada.

## 7. Success metrics

### 7.1 User-centric metrics

- Tempo médio de resposta menor que 6 segundos.
- Taxa de análises concluídas maior que 90% para domínios acessíveis.

### 7.2 Business metrics

- Adoção por pelo menos 35% dos usuários ativos do módulo de ferramentas.
- Contribuição para score de risco em pelo menos 60% das análises consolidadas.

### 7.3 Technical metrics

- P95 de latência menor que 10 segundos.
- Taxa de erro técnico menor que 5%.

## 8. Technical considerations

### 8.1 Integration points

- Endpoint backend dedicado para HTTP Headers Analysis.
- Serviço reutilizável pelo motor de score de risco.
- Composição com Quick Analysis (análise consolidada).

### 8.2 Data storage & privacy

- Armazenar headers relevantes (não payload do body).
- Escopo de acesso por organização.
- Auditoria de execução interna.

### 8.3 Scalability & performance

- Timeout por hop de redirecionamento.
- Rate limit por organização.
- User-Agent neutro para evitar bloqueios desnecessários.

### 8.4 Potential challenges

- Proteção anti-bot (Cloudflare, Akamai) pode mascarar headers reais.
- Domínios com muitos redirecionamentos podem estourar timeout.
- Headers variam significativamente por CDN/proxy.

## 9. Milestones & sequencing

### 9.1 Project estimate

- S: 1 a 1,5 semana

### 9.2 Team size & composition

- 2 a 3 pessoas: 1 Backend, 1 Frontend, 1 QA parcial

### 9.3 Suggested phases

- **Fase 1**: API e coleta de headers (3 dias)
  - Endpoint funcional, coleta de headers e cadeia de redirecionamentos.
- **Fase 2**: Análise de segurança e interface (2 a 3 dias)
  - Classificação de security headers, fingerprinting e tela de resultados.

## 10. User stories

### 10.1 Analisar headers de segurança

- **ID**: GH-HDR-001
- **Description**: Como analista, quero verificar headers de segurança para avaliar a postura de proteção do domínio.
- **Acceptance criteria**:
  - Lista presença/ausência de headers de segurança padrão.
  - Classifica postura geral: bom / razoável / fraco.
  - Mostra timestamp e duração da análise.

### 10.2 Visualizar fingerprint de servidor

- **ID**: GH-HDR-002
- **Description**: Como analista, quero ver tecnologias expostas nos headers para identificar infraestrutura potencialmente vulnerável.
- **Acceptance criteria**:
  - Extrai Server, X-Powered-By e headers de tecnologia.
  - Sinaliza quando versões específicas estão expostas.
  - Não faz juízo de vulnerabilidade, apenas exibe dados.

### 10.3 Inspecionar cadeia de redirecionamentos

- **ID**: GH-HDR-003
- **Description**: Como analista, quero ver a cadeia completa de redirecionamentos para detectar cloaking ou destinos suspeitos.
- **Acceptance criteria**:
  - Mostra cada hop com URL, status code e headers principais.
  - Sinaliza mudanças de domínio e protocolo.
  - Limita seguimento a no máximo 10 hops.

### 10.4 Revisar histórico de análises

- **ID**: GH-HDR-004
- **Description**: Como usuário autenticado, quero revisar análises anteriores para comparar evolução.
- **Acceptance criteria**:
  - Lista domínio, data/hora e score de segurança.
  - Permite filtro por domínio e período.
  - Restringe visualização à própria organização.
