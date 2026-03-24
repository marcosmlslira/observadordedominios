# PRD: Email Security Check (SPF / DKIM / DMARC)

## 1. Product overview

### 1.1 Document title and version

- PRD: Email Security Check
- Version: 1.0

### 1.2 Product summary

Este PRD define a ferramenta de verificação de segurança de email do Observador de Domínios. O objetivo é analisar os registros DNS relacionados a email (SPF, DKIM, DMARC) de um domínio para determinar sua capacidade de enviar emails autenticados — ou, no caso de domínios suspeitos, sua capacidade de falsificar remetentes.

Para o contexto do produto, essa ferramenta é crítica: domínios de phishing frequentemente carecem de configuração SPF/DMARC ou configuram de forma permissiva para maximizar entrega de emails fraudulentos. Ausência de autenticação em um domínio recém-registrado similar à marca do cliente é um forte indicador de risco.

## 2. Goals

### 2.1 Business goals

- Enriquecer análise de risco com capacidade de spoofing do domínio.
- Fornecer sinal diferencial para detectar domínios preparados para phishing.
- Agregar valor técnico único ao módulo de ferramentas gratuitas.

### 2.2 User goals

- Verificar se um domínio suspeito pode enviar emails se passando pela marca.
- Entender a postura de autenticação de email do domínio investigado.
- Obter evidência técnica para justificar bloqueios ou alertas.

### 2.3 Non-goals

- Não testa envio real de email.
- Não configura ou corrige registros SPF/DKIM/DMARC.
- Não monitora mudanças contínuas nos registros de email.

## 3. User personas

### 3.1 Key user types

- Analista de marca/risco
- Analista de segurança
- Operações internas

### 3.2 Basic persona details

- **Analista de marca/risco**: precisa saber se o domínio pode enviar emails se passando pela marca.
- **Analista de segurança**: precisa de análise detalhada dos registros SPF/DMARC.
- **Operações internas**: precisa de dados para escalar alertas de phishing.

### 3.3 Role-based access

- **Cliente autenticado**: executa verificação e consulta histórico próprio.
- **Operador interno**: executa verificação em triagem de incidentes.
- **Admin interno**: gerencia observabilidade e limites.

## 4. Functional requirements

- **Verificação SPF** (Priority: Alta)
  - Consultar registro TXT do tipo SPF.
  - Analisar mecanismos: `all`, `include`, `ip4`, `ip6`, `redirect`.
  - Classificar política: restritiva (`-all`), permissiva (`~all`, `?all`), ausente.
  - Detectar erros comuns: múltiplos registros SPF, excesso de lookups (>10).

- **Verificação DMARC** (Priority: Alta)
  - Consultar registro TXT em `_dmarc.<domínio>`.
  - Analisar política: `p=reject`, `p=quarantine`, `p=none`.
  - Extrair: policy, subdomain policy (`sp=`), percentage (`pct=`), report URIs.
  - Classificar postura: forte / moderada / fraca / ausente.

- **Verificação DKIM** (Priority: Média)
  - Consultar seletores DKIM comuns (default, google, selector1, selector2, k1, etc.).
  - Indicar presença/ausência de registros DKIM encontrados.
  - Nota: DKIM requer conhecimento do seletor — verificação é best-effort.

- **Classificação consolidada de risco de spoofing** (Priority: Alta)
  - Combinar resultados de SPF + DMARC + DKIM.
  - Classificar capacidade de spoofing: baixa / média / alta.
  - Alta = sem SPF ou `?all` + sem DMARC ou `p=none` + sem DKIM.
  - Baixa = SPF `-all` + DMARC `p=reject` + DKIM presente.

- **Persistência de histórico** (Priority: Média)
  - Salvar resultado por organização.
  - Permitir comparação temporal.

## 5. User experience

### 5.1 Entry points & first-time user flow

- Entrada na área de Ferramentas.
- Campo de domínio com validação imediata.
- Botão "Verificar Segurança de Email".

### 5.2 Core experience

- **Inserir domínio**: usuário informa o alvo.
  - Aceita domínio raiz (não email).
- **Executar verificação**: sistema consulta registros DNS de email.
  - Retorno rápido com resultado estruturado.
- **Ver resultado**: três blocos (SPF, DMARC, DKIM) + classificação consolidada.
  - Interpretação clara do risco de spoofing.

### 5.3 Advanced features & edge cases

- Domínio sem nenhum registro MX pode indicar que não pretende receber email, mas pode enviar.
- Registros malformados devem ser sinalizados com o erro específico.
- DKIM é best-effort — ausência de resultados não significa ausência de DKIM.

### 5.4 UI/UX highlights

- Cartão por protocolo (SPF, DMARC, DKIM) com status visual.
- Classificação consolidada de risco de spoofing em destaque.
- Explicação em linguagem simples do que cada resultado significa.
- Tooltip com registro DNS bruto para análise técnica.

## 6. Narrative

Um alerta identifica um domínio recém-registrado com nome muito similar ao da marca do cliente. O analista executa o Email Security Check e descobre: SPF com `?all` (neutro), sem DMARC, sem DKIM. Isso significa que qualquer servidor pode enviar email se passando por esse domínio — cenário perfeito para phishing. O risco de spoofing é classificado como alto, priorizando ação imediata.

## 7. Success metrics

### 7.1 User-centric metrics

- Tempo médio de resposta menor que 5 segundos.
- 90%+ dos usuários compreendem a classificação de risco na primeira leitura.

### 7.2 Business metrics

- Adoção por pelo menos 40% dos usuários ativos do módulo.
- Contribuição para detecção de domínios de phishing em pelo menos 30% dos casos.

### 7.3 Technical metrics

- P95 de latência menor que 8 segundos.
- Taxa de erro técnico menor que 3%.

## 8. Technical considerations

### 8.1 Integration points

- Endpoint backend dedicado para Email Security Check.
- Reutiliza infraestrutura de consulta DNS existente.
- Composição com Quick Analysis e motor de score de risco.

### 8.2 Data storage & privacy

- Armazenar registros encontrados e classificação.
- Escopo de acesso por organização.
- Auditoria de execução interna.

### 8.3 Scalability & performance

- Consultas DNS são leves — boa performance natural.
- Cache curto por domínio (5-10 minutos).
- Rate limit por organização.

### 8.4 Potential challenges

- DKIM requer seletores conhecidos — cobertura parcial inevitável.
- Registros SPF com muitos `include` podem exceder limite de lookups.
- Alguns domínios usam configurações não-padrão.

## 9. Milestones & sequencing

### 9.1 Project estimate

- S: 1 semana

### 9.2 Team size & composition

- 2 pessoas: 1 Backend, 1 Frontend

### 9.3 Suggested phases

- **Fase 1**: API de verificação SPF/DMARC/DKIM (2 a 3 dias)
  - Consulta, parsing e classificação dos registros.
- **Fase 2**: Interface e classificação consolidada (2 dias)
  - Tela de resultados, indicadores visuais, persistência.

## 10. User stories

### 10.1 Verificar postura SPF

- **ID**: GH-EML-001
- **Description**: Como analista, quero verificar o registro SPF para entender quem pode enviar email pelo domínio.
- **Acceptance criteria**:
  - Exibe registro SPF bruto e interpretação.
  - Classifica política: restritiva / permissiva / ausente.
  - Detecta erros comuns (múltiplos registros, excesso de lookups).

### 10.2 Verificar postura DMARC

- **ID**: GH-EML-002
- **Description**: Como analista, quero verificar a política DMARC para saber como servidores receptores tratam emails não autenticados.
- **Acceptance criteria**:
  - Exibe registro DMARC e interpreta política.
  - Classifica postura: forte / moderada / fraca / ausente.
  - Mostra subdomain policy e percentage quando presentes.

### 10.3 Avaliar risco de spoofing consolidado

- **ID**: GH-EML-003
- **Description**: Como analista, quero uma classificação consolidada de risco de spoofing para priorizar ações.
- **Acceptance criteria**:
  - Combina SPF + DMARC + DKIM em classificação única.
  - Classifica: baixo / médio / alto.
  - Explica em linguagem simples o que o resultado significa.

### 10.4 Revisar histórico de verificações

- **ID**: GH-EML-004
- **Description**: Como usuário autenticado, quero revisar verificações anteriores para detectar mudanças na postura de email.
- **Acceptance criteria**:
  - Lista verificações com data/hora e classificação.
  - Permite filtro por domínio e período.
  - Restringe visualização à própria organização.
