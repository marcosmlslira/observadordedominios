# PRD: Ferramentas essenciais de análise pontual de domínios

## 1. Product overview

### 1.1 Document title and version

- PRD: Ferramentas essenciais de análise pontual de domínios
- Version: 1.0

### 1.2 Product summary

Este documento define as ferramentas essenciais de análise pontual de domínios no Observador de Domínios para dois públicos: clientes finais e uso interno da operação. O objetivo é transformar consultas técnicas isoladas em um fluxo simples, padronizado e acionável para prevenção de fraude, phishing e abuso de marca.

No escopo inicial, as ferramentas cobertas são: DNS Lookup, WHOIS, SSL Check, Screenshot de página e Detector de Página Suspeita. Na segunda onda, são adicionadas: HTTP Headers Analysis, Blacklist Check, Email Security Check (SPF/DKIM/DMARC), Reverse IP Lookup, IP Geolocation, Domain Similarity Generator e Website Clone Detector. Todas as ferramentas devem funcionar de forma independente para consulta pontual e também ser reutilizáveis internamente em pipelines de monitoramento e triagem.

## 2. Goals

### 2.1 Business goals

- Aumentar o valor percebido da plataforma com utilitários práticos de investigação imediata.
- Reduzir tempo operacional de triagem do time interno em incidentes de domínio suspeito.
- Criar base para recursos premium (automação, histórico avançado e alertas inteligentes).
- Melhorar retenção ao oferecer capacidades úteis mesmo fora do monitoramento contínuo.

### 2.2 User goals

- Consultar rapidamente o estado técnico e de risco de um domínio.
- Entender sinais de ameaça sem depender de múltiplas ferramentas externas.
- Compartilhar evidências (ex.: screenshot e indicadores) com time de segurança/jurídico.
- Tomar decisão inicial de risco em poucos minutos.

### 2.3 Non-goals

- Não inclui derrubada automática de domínio.
- Não inclui execução automática de ações jurídicas.
- Não inclui threat intelligence avançado de nível SOC.
- Não inclui monitoramento completo de infraestrutura corporativa.

## 3. User personas

### 3.1 Key user types

- Analista de marca/risco (cliente)
- Analista de segurança (cliente)
- Operações internas da plataforma
- Suporte técnico interno

### 3.2 Basic persona details

- **Analista de marca/risco**: precisa validar rapidamente domínios potencialmente infratores com clareza e linguagem acessível.
- **Analista de segurança**: precisa de dados técnicos confiáveis para investigação e priorização.
- **Operações internas**: precisa de ferramentas reusáveis para triagem, validação de alertas e apoio a suporte.
- **Suporte técnico interno**: precisa de diagnóstico rápido para responder clientes com evidências.

### 3.3 Role-based access

- **Cliente autenticado**: executa consultas manuais, visualiza resultados e histórico próprio.
- **Operador interno**: executa consultas manuais em contexto de atendimento/triagem, com visão operacional ampliada.
- **Admin interno**: gerencia limites, provedores, políticas de retenção e observabilidade.

## 4. Functional requirements

- **DNS Lookup** (Priority: Alta)
  - Consultar registros A, AAAA, CNAME, MX, NS, TXT.
  - Mostrar tempo de resposta da consulta e status da resolução.
  - Indicar inconsistências básicas (ex.: ausência de registros esperados).
  - Exibir resultado estruturado para leitura humana e uso interno da plataforma.

- **WHOIS** (Priority: Alta)
  - Consultar dados de registro do domínio (registrar, datas, status, nameservers quando disponíveis).
  - Indicar variação de disponibilidade por TLD e possíveis limitações de privacidade/redação.
  - Exibir carimbo de data/hora da coleta.
  - Normalizar campos principais para consumo padronizado.

- **SSL Check** (Priority: Alta)
  - Validar presença de certificado TLS no host alvo.
  - Exibir emissor, validade, SAN/CN e dias para expiração.
  - Sinalizar estados críticos (expirado, próximo de expirar, hostname inválido).
  - Retornar resultado com nível de severidade.

- **Screenshot de página** (Priority: Média)
  - Capturar screenshot da página inicial do domínio informado.
  - Registrar status de navegação (carregou, timeout, bloqueado).
  - Armazenar evidência com referência temporal para auditoria interna.
  - Garantir timeout e isolamento de execução para evitar travamento de fila.

- **Detector de página suspeita** (Priority: Alta)
  - Avaliar sinais básicos de suspeita na página coletada.
  - Regras iniciais: uso de termos sensíveis de credenciais, imitação de marca, padrão visual de login suspeito e redirecionamentos anômalos.
  - Gerar classificação simples: baixo, médio, alto.
  - Exibir justificativas objetivas dos sinais detectados.

- **Orquestração e experiência unificada** (Priority: Alta)
  - Permitir execução individual por ferramenta e execução combinada “análise rápida”.
  - Consolidar saída em um resumo único para facilitar decisão.
  - Registrar histórico por organização para uso do cliente e operação interna.

## 5. User experience

### 5.1 Entry points & first-time user flow

- Entrada por menu “Ferramentas” no produto autenticado.
- Campo único para domínio/host com validação imediata.
- Ações rápidas: executar ferramenta individual ou “Análise rápida” (todas essenciais).
- Exibição progressiva de resultados por bloco com estado de carregamento/erro.

### 5.2 Core experience

- **Informar domínio alvo**: usuário digita domínio e escolhe ferramenta(s).
  - Garante rapidez e baixa fricção na investigação.
- **Executar consulta**: backend dispara execução com timeouts por ferramenta.
  - Garante previsibilidade operacional e evita tela travada.
- **Analisar resultado consolidado**: usuário vê sinais técnicos + resumo de risco.
  - Garante leitura orientada à decisão.
- **Salvar e compartilhar evidências**: resultado fica no histórico da organização.
  - Garante rastreabilidade para operação, segurança e jurídico.

### 5.3 Advanced features & edge cases

- Domínio inválido ou malformado retorna erro orientativo.
- Falha parcial em uma ferramenta não interrompe as demais.
- TLD sem dados WHOIS públicos retorna status “indisponível” com motivo.
- Site inacessível ainda permite DNS/WHOIS/SSL quando aplicável.
- Bloqueio anti-bot na captura de screenshot retorna evidência de falha controlada.

### 5.4 UI/UX highlights

- Resultado por cartões de ferramenta com status visual consistente.
- Linguagem clara para sinais de risco e recomendação de próxima ação.
- Destaque de severidade no resumo final (baixo/médio/alto).
- Histórico pesquisável por domínio e data.

## 6. Narrative

Um analista identifica um domínio potencialmente suspeito e abre a área de ferramentas. Em poucos cliques, executa análise rápida e recebe DNS, WHOIS, SSL, screenshot e classificação de suspeita em uma única visão. Com evidências organizadas e linguagem objetiva, ele prioriza resposta imediata e compartilha internamente sem precisar alternar entre plataformas externas.

## 7. Success metrics

### 7.1 User-centric metrics

- Tempo médio para primeira evidência útil menor que 20 segundos em consultas individuais.
- Taxa de conclusão da análise rápida maior que 90% em domínios válidos.
- Satisfação do usuário com clareza dos resultados maior que 4,2/5.

### 7.2 Business metrics

- Aumento de ativação de usuários no módulo de ferramentas em 30% após lançamento.
- Redução de churn em contas com uso recorrente das ferramentas.
- Crescimento de conversão para plano pago com histórico/automação avançada.

### 7.3 Technical metrics

- Disponibilidade do serviço de ferramentas maior ou igual a 99,5%.
- P95 de execução da análise rápida menor que 30 segundos.
- Taxa de falha técnica por ferramenta menor que 5% (excluindo bloqueios externos).

## 8. Technical considerations

### 8.1 Integration points

- API backend FastAPI com rotas versionadas para execução de ferramentas.
- Serviços internos separados por tipo de verificação (dns, whois, ssl, screenshot, suspeita).
- Repositório de resultados para histórico por organização.
- Frontend Next.js consumindo endpoint consolidado e endpoints individuais.

### 8.2 Data storage & privacy

- Armazenar resultados técnicos essenciais e metadados de execução por organização.
- Aplicar retenção configurável para screenshots e resultados brutos.
- Evitar persistência de conteúdo sensível além do necessário para evidência.
- Registrar auditoria de execução interna (quem executou, quando, qual domínio).

### 8.3 Scalability & performance

- Execução assíncrona por ferramenta com timeout e isolamento de falha.
- Limites por organização para evitar abuso e controlar custo operacional.
- Cache curto para consultas repetidas em janela configurada.
- Fila para capturas de screenshot em picos de uso.

### 8.4 Potential challenges

- Variação de disponibilidade e qualidade de dados WHOIS por TLD.
- Bloqueios anti-bot e latência variável na captura de páginas.
- Divergência entre resolução DNS pública e ambiente de execução.
- Balancear custo de processamento com velocidade de resposta.

## 9. Milestones & sequencing

### 9.1 Project estimate

- M: 5 a 7 semanas

### 9.2 Team size & composition

- 4 a 6 pessoas: 1 PM, 1 Designer, 2 Backend, 1 Frontend, 1 QA (parcial)

### 9.3 Suggested phases

- **Fase 1**: Fundamentos técnicos e APIs base (1,5 a 2 semanas)
  - Entrega de endpoints de DNS, WHOIS e SSL com contratos estáveis.
- **Fase 2**: Screenshot e detector de página suspeita (1,5 a 2 semanas)
  - Entrega de coleta visual com timeout e regras iniciais de classificação.
- **Fase 3**: UX consolidada, histórico e controles operacionais (1,5 a 2 semanas)
  - Entrega de análise rápida, histórico por organização, limites e observabilidade.

## 10. User stories

### 10.1 Consultar DNS de um domínio

- **ID**: GH-001
- **Description**: Como analista, quero consultar registros DNS para validar infraestrutura e sinais técnicos iniciais.
- **Acceptance criteria**:
  - Dado um domínio válido, quando executar DNS Lookup, então devo ver registros A/AAAA/CNAME/MX/NS/TXT quando disponíveis.
  - Se não houver resposta, então devo ver status claro de falha/timeout com mensagem acionável.
  - O resultado deve registrar data e hora da consulta.

### 10.2 Consultar WHOIS de um domínio

- **ID**: GH-002
- **Description**: Como analista, quero visualizar dados WHOIS para entender idade do domínio e contexto de registro.
- **Acceptance criteria**:
  - Dado um domínio consultável, quando executar WHOIS, então devo ver registrador, datas e status quando disponíveis.
  - Quando a TLD limitar dados, então devo ver indicação explícita de indisponibilidade parcial.
  - O resultado deve ser apresentado em campos normalizados.

### 10.3 Validar certificado SSL

- **ID**: GH-003
- **Description**: Como analista, quero checar o SSL para identificar riscos técnicos de confiança.
- **Acceptance criteria**:
  - Dado um host HTTPS, quando executar SSL Check, então devo ver emissor, validade e SAN/CN.
  - Se o certificado estiver expirado ou inválido para hostname, então devo ver severidade alta.
  - Se faltar certificado, então o resultado deve indicar ausência de TLS.

### 10.4 Capturar screenshot do site

- **ID**: GH-004
- **Description**: Como analista, quero capturar a página para registrar evidência visual do conteúdo suspeito.
- **Acceptance criteria**:
  - Dado um domínio acessível, quando executar Screenshot, então devo receber imagem com carimbo temporal.
  - Se houver timeout/bloqueio, então devo receber status técnico correspondente.
  - A evidência deve poder ser recuperada no histórico da organização.

### 10.5 Classificar página suspeita

- **ID**: GH-005
- **Description**: Como analista, quero uma classificação de suspeita para priorizar investigação.
- **Acceptance criteria**:
  - Dado conteúdo coletado, quando executar detector de página suspeita, então devo receber nível baixo/médio/alto.
  - A classificação deve exibir justificativas dos sinais detectados.
  - Em caso de dados insuficientes, o sistema deve informar “não conclusivo” de forma explícita.

### 10.6 Executar análise rápida consolidada

- **ID**: GH-006
- **Description**: Como usuário, quero executar todas as ferramentas essenciais de uma vez para acelerar triagem.
- **Acceptance criteria**:
  - Ao acionar análise rápida, DNS/WHOIS/SSL/Screenshot/Suspeita devem iniciar no mesmo fluxo.
  - Falha de uma ferramenta não deve cancelar as demais.
  - O sistema deve retornar resumo consolidado com severidade final e próximos passos sugeridos.

### 10.7 Acessar histórico de consultas

- **ID**: GH-007
- **Description**: Como usuário autenticado, quero revisar consultas anteriores para comparar evolução e manter rastreabilidade.
- **Acceptance criteria**:
  - O histórico deve listar domínio, ferramentas executadas, data/hora e status.
  - Deve ser possível filtrar por domínio e período.
  - O usuário só pode ver dados da própria organização.

### 10.8 Uso interno para operação e suporte

- **ID**: GH-008
- **Description**: Como operador interno, quero usar as mesmas ferramentas em contexto operacional para acelerar suporte e validação de alertas.
- **Acceptance criteria**:
  - Usuários internos autorizados devem executar consultas com trilha de auditoria.
  - A interface interna deve apresentar identificador da organização relacionada ao caso.
  - O uso interno deve respeitar políticas de retenção e privacidade.

### 10.9 Segurança, autenticação e autorização

- **ID**: GH-009
- **Description**: Como gestor da plataforma, quero que o acesso às ferramentas seja controlado para proteger dados e evitar abuso.
- **Acceptance criteria**:
  - Apenas usuários autenticados podem executar consultas.
  - Permissões devem separar cliente, operador interno e admin interno.
  - O sistema deve aplicar rate limit por organização e registrar tentativas bloqueadas.

### 10.10 Resiliência e observabilidade

- **ID**: GH-010
- **Description**: Como time técnico, queremos monitorar execução das ferramentas para manter confiabilidade operacional.
- **Acceptance criteria**:
  - Cada execução deve registrar duração, status e erro padronizado por ferramenta.
  - Métricas de sucesso/falha e latência devem estar disponíveis para operação.
  - Alertas internos devem disparar quando taxa de falha ultrapassar limite configurado.