# PRD: Website Clone Detector

## 1. Product overview

### 1.1 Document title and version

- PRD: Website Clone Detector
- Version: 1.0

### 1.2 Product summary

Este PRD define a ferramenta de detecção de clonagem de sites do Observador de Domínios. O objetivo é comparar o conteúdo e a aparência visual de um domínio suspeito contra o site legítimo do cliente para identificar cópia, imitação parcial ou impersonação de marca.

Diferente do Detector de Página Suspeita (que avalia sinais genéricos de phishing), esta ferramenta responde à pergunta central: **"Este site está copiando o meu?"**. Phishing moderno frequentemente clona o site original de forma quase idêntica — detectar essa similaridade é a evidência mais forte e acionável de brand impersonation.

A comparação opera em três camadas: estrutura HTML, conteúdo textual e aparência visual (screenshot). Cada camada produz um score de similaridade, e a combinação gera uma classificação consolidada de probabilidade de clone.

## 2. Goals

### 2.1 Business goals

- Fornecer a evidência mais direta e compreensível de impersonação de marca.
- Reduzir drasticamente o tempo de confirmação de clonagem (de minutos de análise manual para segundos).
- Criar diferencial competitivo — análise comparativa contra o site do próprio cliente.
- Alimentar o score de risco com o sinal mais forte possível de ameaça.

### 2.2 User goals

- Confirmar rapidamente se um domínio suspeito está imitando o site legítimo da marca.
- Obter evidência visual e técnica comparativa para ações jurídicas e takedown.
- Quantificar o grau de similaridade de forma objetiva (percentual/score).
- Entender quais elementos específicos foram copiados.

### 2.3 Non-goals

- Não detecta clonagem de aplicativos mobile.
- Não compara fluxos internos (login, checkout) — apenas a página inicial/landing page.
- Não garante detecção de clones com ofuscação avançada ou cloaking.
- Não executa ações legais ou takedown automaticamente.

## 3. User personas

### 3.1 Key user types

- Analista de marca/risco
- Gestor de marca
- Analista de segurança
- Operações internas

### 3.2 Basic persona details

- **Analista de marca/risco**: precisa de confirmação objetiva de clonagem para escalar casos.
- **Gestor de marca**: precisa de evidência visual clara para compartilhar com jurídico.
- **Analista de segurança**: precisa de detalhes técnicos sobre quais elementos foram copiados.
- **Operações internas**: precisa de triagem automatizada para priorizar alertas.

### 3.3 Role-based access

- **Cliente autenticado**: executa comparação contra seus domínios legítimos e consulta histórico.
- **Operador interno**: executa comparação em contexto de triagem/suporte.
- **Admin interno**: gerencia configurações de similaridade e observabilidade.

## 4. Functional requirements

### 4.1 Cadastro do site de referência

- **Captura do site legítimo** (Priority: Alta)
  - Permitir que o cliente cadastre o domínio legítimo como referência de comparação.
  - Capturar e armazenar snapshot de referência: screenshot, DOM simplificado, texto extraído, assets principais (logo, favicon, cores dominantes).
  - Permitir atualização manual do snapshot de referência quando o site legítimo mudar.
  - Suportar múltiplos domínios de referência por organização (marca principal + variações legítimas).

### 4.2 Comparação de conteúdo textual

- **Similaridade textual** (Priority: Alta)
  - Extrair texto visível da página suspeita.
  - Comparar com texto do site de referência usando algoritmo de similaridade (ex.: cosine similarity, Jaccard, ou fuzzy matching).
  - Retornar score de similaridade textual (0-100%).
  - Destacar trechos específicos copiados ou muito similares.
  - Detectar: nome da marca, slogan, textos de CTA, disclaimers e termos legais copiados.

### 4.3 Comparação estrutural (HTML/DOM)

- **Similaridade estrutural** (Priority: Média)
  - Extrair estrutura DOM simplificada da página suspeita.
  - Comparar com estrutura do site de referência (tree edit distance ou hash de estrutura).
  - Retornar score de similaridade estrutural (0-100%).
  - Detectar: mesma hierarquia de elementos, mesmas classes CSS, mesmo layout de formulários.
  - Não comparar conteúdo dinâmico (ads, feeds) — focar em estrutura estática principal.

### 4.4 Comparação visual (perceptual)

- **Similaridade visual** (Priority: Alta)
  - Capturar screenshot da página suspeita (reutilizar ferramenta de Screenshot).
  - Comparar visualmente com screenshot de referência usando perceptual hashing (pHash, dHash) ou SSIM.
  - Retornar score de similaridade visual (0-100%).
  - Gerar imagem de diferença (diff visual) destacando áreas idênticas e diferentes.
  - Comparar elementos específicos: logo, esquema de cores, layout geral.

### 4.5 Detecção de assets copiados

- **Identificação de assets** (Priority: Média)
  - Detectar se a página suspeita usa o mesmo favicon do site de referência.
  - Comparar logos/imagens principais por similaridade visual.
  - Identificar se assets estão sendo servidos diretamente do domínio legítimo (hotlinking).
  - Verificar uso de mesmas fontes e paleta de cores.

### 4.6 Classificação consolidada

- **Score de clonagem** (Priority: Alta)
  - Combinar scores das três camadas (texto, estrutura, visual) em classificação única.
  - Classificar probabilidade de clone: improvável / possível / provável / quase certo.
  - Peso sugerido: visual (40%) + textual (35%) + estrutural (25%) — configurável.
  - Retornar explicação em linguagem simples do resultado.

- **Níveis de classificação**:
  - **Improvável** (0-25%): Sem semelhança significativa.
  - **Possível** (26-50%): Alguns elementos similares — pode ser coincidência ou inspiração.
  - **Provável** (51-75%): Múltiplos elementos copiados — forte indicação de imitação intencional.
  - **Quase certo** (76-100%): Clone direto ou cópia quase idêntica.

### 4.7 Persistência e evidência

- **Histórico e evidência** (Priority: Média)
  - Salvar resultado completo por organização com timestamps.
  - Armazenar screenshots comparativos e diff visual como evidência.
  - Permitir exportação de relatório de similaridade (PDF) para uso jurídico.
  - Registrar evolução temporal (site suspeito ficou mais similar? menos?).

## 5. User experience

### 5.1 Entry points & first-time user flow

- Entrada na área de Ferramentas.
- Primeira execução: solicitar cadastro do domínio legítimo de referência (se não houver).
- Campos: "Domínio suspeito" + seleção do "Domínio de referência" (já cadastrado).
- Botão "Comparar Sites".
- Fluxo alternativo: a partir do resultado de outra ferramenta (ex.: Domain Similarity Generator encontrou domínio registrado → ação "Comparar com meu site").

### 5.2 Core experience

- **Selecionar referência e alvo**: usuário escolhe domínio de referência e informa o suspeito.
  - Se organização tem apenas um domínio de referência, pré-selecionar automaticamente.
- **Executar comparação**: sistema captura página suspeita e compara nas três camadas.
  - Loading progressivo: primeiro visual (mais rápido de interpretar), depois textual, depois estrutural.
- **Ver resultado comparativo**: visualização lado a lado com scores por camada.
  - Foco na evidência visual — é o que o usuário entende mais rápido.
- **Exportar evidência**: gerar relatório para compartilhar com jurídico/segurança.

### 5.3 Advanced features & edge cases

- Site suspeito offline/inacessível: comparar apenas com dados já capturados (se houver screenshot anterior).
- Site de referência mudou: alertar que o snapshot de referência pode estar desatualizado.
- Cloaking: site suspeito pode mostrar conteúdo diferente por User-Agent ou IP — sinalizar se detectado.
- Sites com muito conteúdo dinâmico (SPAs): captura pode ser parcial — indicar limitação.
- Domínio suspeito em idioma diferente: similaridade textual será baixa, mas visual pode ser alta — ponderar.

### 5.4 UI/UX highlights

- **Visualização lado a lado**: screenshot do site legítimo vs. suspeito.
- **Diff visual**: overlay colorido mostrando áreas idênticas (verde) e diferentes (vermelho).
- **Score consolidado em destaque**: badge grande com classificação e percentual.
- **Breakdown por camada**: barras de progresso para cada score (visual, textual, estrutural).
- **Trechos copiados**: highlight de textos idênticos encontrados.
- **Botão de exportação**: gerar PDF com toda a evidência comparativa.

## 6. Narrative

Uma empresa monitora variações do seu domínio principal. O Domain Similarity Generator detecta que `marca-login.com` foi registrado há 2 dias. O analista clica em "Comparar com meu site" e em segundos vê os dois sites lado a lado. O score visual é 87%, o textual 72% (mesmos textos de boas-vindas e footer), e o estrutural 65%. Classificação: **provável clone**. O diff visual mostra que o logo, o formulário de login e o esquema de cores são praticamente idênticos, com pequenas diferenças no footer. O analista exporta o relatório em PDF e encaminha para o jurídico, que tem evidência objetiva para solicitar takedown.

## 7. Success metrics

### 7.1 User-centric metrics

- Tempo médio de comparação completa menor que 15 segundos.
- 90%+ dos usuários compreendem o resultado na primeira leitura.
- 85%+ de concordância entre classificação automática e julgamento humano.

### 7.2 Business metrics

- Adoção por pelo menos 50% dos usuários ativos — é a ferramenta mais diretamente ligada à proposta de valor de proteção de marca.
- Redução de 60% no tempo médio de confirmação de clonagem vs. análise manual.
- Pelo menos 25% das detecções de clone levam a ação concreta (takedown, notificação, bloqueio).
- Conversão para monitoramento contínuo em pelo menos 35% dos usuários que usam a ferramenta.

### 7.3 Technical metrics

- P95 de latência menor que 20 segundos para comparação completa.
- Taxa de erro técnico menor que 5% em domínios acessíveis.
- Precisão (precision) da classificação "provável/quase certo" acima de 80%.
- Recall de clones conhecidos acima de 75%.

## 8. Technical considerations

### 8.1 Integration points

- Endpoint backend dedicado para Website Clone Detector.
- Reutiliza ferramenta de Screenshot para captura do site suspeito.
- Integração com módulo de domínios monitorados (referência).
- Composição com Quick Analysis e motor de score de risco.
- Cross-reference com Domain Similarity Generator (ação rápida).
- Integração futura com monitoramento contínuo (comparação periódica automática).

### 8.2 Data storage & privacy

- **Snapshots de referência**: armazenar screenshot, DOM simplificado, texto, assets hash por organização.
- **Resultados de comparação**: armazenar scores, classificação, diff visual, trechos destacados.
- **Evidência exportável**: gerar e cachear PDFs de relatório.
- Segregação estrita por organização.
- Retenção configurável para snapshots e resultados.
- Auditoria de execução interna.

### 8.3 Scalability & performance

- Captura de página suspeita: reutilizar infra de Screenshot (com fila e timeout).
- Comparação textual: leve, executa em memória.
- Comparação visual (pHash/SSIM): moderada, pode executar em worker dedicado.
- Comparação estrutural: moderada, DOM parsing com limite de profundidade.
- Cache de snapshots de referência — atualizar apenas quando solicitado.
- Rate limit por organização.

### 8.4 Potential challenges

- **Cloaking**: sites maliciosos podem mostrar conteúdo diferente para bots vs. humanos. Mitigação: usar User-Agent de navegador real, considerar múltiplas capturas.
- **SPAs e conteúdo dinâmico**: captura pode não refletir o conteúdo real. Mitigação: aguardar carregamento, executar JavaScript.
- **Sites com CDN/WAF**: podem bloquear captura. Mitigação: sinalizar explicitamente quando captura falha.
- **Threshold de similaridade**: calibrar o que é "clone" vs. "template genérico". Mitigação: usar datasets de validação, permitir ajuste manual.
- **Performance de comparação visual**: SSIM é mais preciso mas mais pesado que pHash. Mitigação: pHash para triagem rápida, SSIM para confirmação.
- **Idiomas diferentes**: clone pode traduzir o site. Mitigação: ponderar camada visual mais que textual nesses casos.

## 9. Milestones & sequencing

### 9.1 Project estimate

- L: 3 a 4 semanas

### 9.2 Team size & composition

- 4 a 5 pessoas: 1 Backend (comparação/algoritmos), 1 Backend (captura/infra), 1 Frontend, 1 QA, 1 Designer (parcial para diff visual)

### 9.3 Suggested phases

- **Fase 1**: Captura de referência e comparação textual (5 a 6 dias)
  - Cadastro de domínio de referência com snapshot.
  - Extração de texto e algoritmo de similaridade textual.
  - API funcional com score textual.

- **Fase 2**: Comparação visual e diff (5 a 6 dias)
  - Captura de screenshot do suspeito (reutilizar Screenshot tool).
  - Implementação de perceptual hashing e/ou SSIM.
  - Geração de diff visual (overlay de diferenças).
  - API funcional com score visual.

- **Fase 3**: Comparação estrutural e classificação consolidada (3 a 4 dias)
  - DOM parsing e tree comparison simplificado.
  - Detecção de assets copiados (favicon, logo hash).
  - Score consolidado com pesos configuráveis.
  - Classificação final (improvável → quase certo).

- **Fase 4**: Interface, exportação e integração (4 a 5 dias)
  - Tela de comparação lado a lado com diff visual.
  - Breakdown de scores por camada.
  - Exportação de relatório PDF.
  - Integração com Domain Similarity Generator e Quick Analysis.
  - Persistência e histórico.

## 10. User stories

### 10.1 Cadastrar site de referência

- **ID**: GH-CLN-001
- **Description**: Como usuário, quero cadastrar meu site legítimo como referência para comparações futuras.
- **Acceptance criteria**:
  - Permite informar domínio legítimo e capturar snapshot de referência.
  - Armazena screenshot, texto extraído e hash de assets.
  - Permite atualizar snapshot quando o site mudar.
  - Suporta múltiplos domínios de referência por organização.

### 10.2 Comparar site suspeito com referência

- **ID**: GH-CLN-002
- **Description**: Como analista, quero comparar um domínio suspeito com meu site legítimo para confirmar clonagem.
- **Acceptance criteria**:
  - Recebe domínio suspeito e seleciona referência.
  - Retorna scores de similaridade: visual, textual e estrutural.
  - Classificação consolidada: improvável / possível / provável / quase certo.
  - Tempo de execução menor que 20 segundos.

### 10.3 Visualizar diferenças lado a lado

- **ID**: GH-CLN-003
- **Description**: Como analista, quero ver os dois sites lado a lado com diferenças destacadas para entender o grau de cópia.
- **Acceptance criteria**:
  - Exibe screenshots lado a lado (referência vs. suspeito).
  - Overlay de diff visual com áreas idênticas e diferentes.
  - Destaque de trechos de texto copiados.
  - Breakdown de score por camada com barras visuais.

### 10.4 Detectar assets copiados

- **ID**: GH-CLN-004
- **Description**: Como analista, quero saber se o site suspeito usa meu logo, favicon ou elementos visuais da minha marca.
- **Acceptance criteria**:
  - Compara favicon do suspeito com o de referência.
  - Identifica imagens/logos similares por hash visual.
  - Detecta hotlinking de assets do domínio legítimo.
  - Lista assets encontrados com grau de similaridade.

### 10.5 Exportar relatório de evidência

- **ID**: GH-CLN-005
- **Description**: Como gestor de marca, quero exportar um relatório completo da comparação para compartilhar com jurídico.
- **Acceptance criteria**:
  - Gera PDF com: domínios comparados, scores, screenshots, diff visual, trechos copiados.
  - Inclui timestamps e metadados de execução.
  - Formatação profissional adequada para uso em processos legais.
  - Download disponível por pelo menos 30 dias.

### 10.6 Comparar a partir de outra ferramenta

- **ID**: GH-CLN-006
- **Description**: Como analista, quero comparar um domínio encontrado por outra ferramenta sem perder o contexto.
- **Acceptance criteria**:
  - Ação "Comparar com meu site" disponível no resultado do Domain Similarity Generator.
  - Ação disponível no resultado de Quick Analysis.
  - Pré-preenche domínio suspeito e referência automaticamente.
  - Retorna ao contexto original após a comparação.

### 10.7 Acompanhar evolução temporal

- **ID**: GH-CLN-007
- **Description**: Como analista, quero ver como a similaridade evolui ao longo do tempo para detectar clones que estão ficando mais sofisticados.
- **Acceptance criteria**:
  - Lista comparações anteriores do mesmo par (referência + suspeito).
  - Mostra evolução dos scores ao longo do tempo.
  - Destaca quando score aumenta significativamente (clone está melhorando).
  - Restringe à própria organização.

### 10.8 Lidar com limitações de captura

- **ID**: GH-CLN-008
- **Description**: Como analista, quero entender claramente quando a comparação é limitada para não tirar conclusões erradas.
- **Acceptance criteria**:
  - Indica explicitamente quando captura foi parcial (anti-bot, timeout, SPA).
  - Ajusta confiança do score quando dados são incompletos.
  - Sugere ações alternativas (ex.: tentar novamente, verificar manualmente).
  - Nunca classifica como "improvável" apenas por falta de dados — usar "inconclusivo".
