# PRD: Base global de domínios e histórico de observações

## 1. Product overview

### 1.1 Document title and version

- PRD: Base global de domínios e histórico de observações
- Version: 1.0

### 1.2 Product summary

Este PRD define a criação da base central global de domínios do projeto, com ingestão contínua de múltiplas fontes (CT Logs, Zone Files, pDNS e fornecedores pagos), histórico temporal de observações e estado DNS atual. O objetivo é transformar dados heterogêneos em um produto interno de dados consistente, confiável e pronto para inteligência de risco e consultas operacionais.

A abordagem adota arquitetura orientada a eventos e snapshots: observações de fontes externas são registradas como evidências com timestamp e consolidadas em uma entidade canônica de domínio. A plataforma mantém rastreabilidade completa de origem, atualizações e confiança das inferências de data de registro.

O escopo inicial prioriza ingestão e modelagem escalável/modular da base global, com contratos de dados, regras de merge idempotentes, versionamento histórico e APIs mínimas para consumo interno do Observador de Domínios.

## 2. Goals

### 2.1 Business goals

- Construir ativo de dados proprietário para diferenciar o produto no monitoramento de domínios.
- Reduzir dependência operacional de consultas manuais e fontes isoladas.
- Aumentar precisão e velocidade da inteligência de risco com histórico temporal consolidado.
- Preparar base para features futuras de detecção, alertas e priorização automatizada.

### 2.2 User goals

- Consultar rapidamente o histórico de surgimento e atividade de um domínio.
- Entender de qual fonte veio cada evidência e qual o nível de confiança da inferência.
- Obter estado DNS atual e evolução recente sem depender de investigação manual.
- Reprocessar ingestões com segurança, sem duplicação ou corrupção de dados.

### 2.3 Non-goals

- Garantir `registered_at` exato para 100% dos TLDs no MVP.
- Cobrir toda a camada de reputação avançada na primeira fase.
- Implementar derrubada automática de domínio ou ações jurídicas automáticas.
- Entregar pipeline streaming full real-time para todas as fontes já no MVP.

## 3. User personas

### 3.1 Key user types

- Analista de inteligência de domínios
- Operador de dados/plataforma
- Admin interno do produto

### 3.2 Basic persona details

- **Analista de inteligência de domínios**: precisa consultar histórico, evidências e DNS para investigação e triagem.
- **Operador de dados/plataforma**: precisa administrar ingestões, reprocessamentos e qualidade de dados por fonte.
- **Admin interno do produto**: precisa governar acesso, auditoria e evolução de fontes e contratos de dados.

### 3.3 Role-based access

- **Analyst**: leitura de domínios, observações e snapshots DNS.
- **Data Operator**: execução de ingestão, reprocessamento, gestão de ciclos de vida por fonte e visualização de falhas.
- **Platform Admin**: configuração de fontes, políticas de retenção, credenciais e auditoria completa.

## 4. Functional requirements

- **Ingestão multi-fonte com ciclo de vida independente** (Priority: Alta)
  - Cada fonte deve ter estado, agenda, versão de contrato e métricas próprias.
  - Fontes iniciais: CT Logs, Zone Files, pDNS e paid feeds.
  - A ingestão deve ser idempotente e suportar reprocessamento por janela temporal.

- **Normalização canônica de domínio** (Priority: Alta)
  - Canonicalização obrigatória: lowercase, punycode, remoção de trailing dot e validação sintática.
  - Padronização de TLD/eTLD+1 para consolidar consultas e índices.
  - Rejeições devem ser rastreadas com motivo de erro e referência ao payload bruto.

- **Base central global consolidada** (Priority: Alta)
  - Consolidar evidências em entidade única de domínio (`first_seen_at`, `last_seen_at`, status).
  - Preservar rastreabilidade por fonte e timestamp sem perda de granularidade.
  - Suportar consultas de alta cardinalidade para inteligência interna.

- **Modelo temporal event + snapshot** (Priority: Alta)
  - Eventos de observação append-only para histórico completo.
  - Snapshot DNS atual com histórico configurável para domínios relevantes.
  - Materialização de visão “current state” para leitura rápida.

- **Inferência de `registered_at_best` por evidência** (Priority: Alta)
  - Calcular melhor estimativa por ranking de confiança por fonte.
  - Persistir score de confiança e fonte vencedora.
  - Aplicar regra determinística de desempate com preferência pela data mais antiga.

- **APIs internas de consulta e operação** (Priority: Alta)
  - Consultas por domínio, TLD, intervalo temporal e origem.
  - Endpoint de observações históricas por domínio e fonte.
  - Endpoints administrativos para executar ingestão e acompanhar execuções.

- **Governança, segurança e auditoria** (Priority: Alta)
  - Autenticação/autorização por papel para operações administrativas.
  - Auditoria de execução de ingestão, falhas, retries e mudanças de configuração.
  - Proteção de segredos de fontes pagas e trilha de acesso.

## 5. User experience

### 5.1 Entry points & first-time user flow

- Operador cadastra e habilita fontes com credenciais e política de execução.
- Plataforma executa a primeira ingestão e publica relatório de qualidade por fonte.
- Base central passa a responder consultas por domínio com evidências e DNS atual.
- Analista consulta domínio e obtém linha do tempo unificada para investigação.

### 5.2 Core experience

- **Executar ingestão por fonte**: operador agenda ou dispara execução manual.
  - Garante ciclo de vida independente e operação resiliente por conector.
- **Consolidar domínio canônico**: serviço aplica normalização e merge idempotente.
  - Mantém consistência global da base mesmo com fontes heterogêneas.
- **Consultar histórico e estado atual**: analista acessa domínio, observações e DNS.
  - Reduz tempo de investigação e melhora confiança da decisão.

### 5.3 Advanced features & edge cases

- Reprocessamento de janela histórica sem criar duplicatas.
- Fonte atrasada ou indisponível não interrompe ingestão de outras fontes.
- Domínio inválido é descartado com rastreabilidade para auditoria.
- Evidências conflitantes atualizam `registered_at_best` com regra determinística.
- DNS timeout/servfail/nx_domain é persistido como status observável.

### 5.4 UI/UX highlights

- Painel operacional por fonte com status, latência, volume, falhas e retries.
- Detalhe de domínio com timeline de observações e confiança da inferência.
- Visualização clara de “first_seen” versus “registered_at_best”.
- Ações administrativas com feedback acionável e histórico de execuções.

## 6. Narrative

O operador ativa conectores de CT Logs, Zone Files, pDNS e fontes pagas, cada um com agenda e política de retry próprias. As observações chegam como eventos, são normalizadas e consolidadas em uma base global de domínio canônico, preservando rastreabilidade e confiança da inferência temporal. O analista então consulta um único ponto de verdade com histórico e DNS atual para orientar decisões de risco no Observador de Domínios.

## 7. Success metrics

### 7.1 User-centric metrics

- Tempo médio de consulta de detalhe de domínio abaixo de 500 ms (p95).
- Tempo de investigação manual reduzido em pelo menos 40%.
- Cobertura de histórico disponível para domínios consultados acima de 95%.

### 7.2 Business metrics

- Aumento de precisão de priorização de risco em detecções internas.
- Redução de custo operacional por investigação em fontes externas ad-hoc.
- Aceleração de entrega de novas features de inteligência baseadas em domínio.

### 7.3 Technical metrics

- Taxa de duplicação pós-merge abaixo de 0.1%.
- Taxa de sucesso de ingestão por fonte acima de 99% (com retry).
- SLA de atualização de `last_seen_at` dentro da janela acordada por fonte.
- Backfill/reprocessamento de janela diária concluído no tempo operacional definido.

## 8. Technical considerations

### 8.1 Integration points

- Conectores de ingestão para CT Logs, Zone Files, pDNS e providers pagos.
- Orquestração de jobs de ingestão, normalização, merge e enriquecimento DNS.
- APIs FastAPI para consulta e operação administrativa.
- PostgreSQL como armazenamento central transacional.

### 8.2 Data storage & privacy

- Base classificada como **global do sistema** (ownership level: System).
- Tabela de domínio canônico + tabela de observações append-only + snapshots DNS.
- Retenção temporal definida por tipo de dado (eventos, snapshots e raw payload).
- Criptografia de credenciais e segregação de acesso por papel operacional.

### 8.3 Scalability & performance

- Particionamento por tempo e/ou fonte em tabelas de observação de alto volume.
- Índices compostos orientados a filtros reais (`domain`, `source`, `observed_at`).
- Processamento idempotente com chave natural/hash de observação.
- Pipeline modular por estágios: ingest, normalize, merge, enrich.
- Estratégia de filas/jobs com retry exponencial, DLQ lógica e observabilidade.

### 8.4 Potential challenges

- Heterogeneidade semântica e qualidade variável entre fontes.
- Volume e cardinalidade elevados em picos de ingestão.
- Diferença entre “primeira observação” e “registro real” em determinados TLDs.
- Custos de armazenamento para histórico completo e payload bruto.
- Controle de latência entre atualização de fonte e disponibilidade para consulta.

## 9. Milestones & sequencing

### 9.1 Project estimate

- XL: 8 a 12 semanas

### 9.2 Team size & composition

- 5 a 7 pessoas: 2 Backend (API/serviços), 2 Data/Backend (ingestão/modelagem), 1 DevOps/SRE, 1 QA, 1 apoio de produto parcial

### 9.3 Suggested phases

- **Fase 1**: Fundação de modelo e ingestão inicial (2 a 3 semanas)
  - Modelagem de `domains`, `domain_observations`, `ingestion_runs` e contratos de fonte.
  - Conector inicial com ingestão idempotente e reprocessamento básico.

- **Fase 2**: Multi-fonte e merge robusto (2 a 3 semanas)
  - Conectores CT Logs, Zone Files e pDNS com ciclo de vida independente.
  - Regras de merge e cálculo de `registered_at_best` com confiança.

- **Fase 3**: DNS snapshots e APIs de consulta (2 semanas)
  - Persistência de snapshots DNS atual/histórico para domínios priorizados.
  - Endpoints de domínio, observações, operações de ingestão e health operacional.

- **Fase 4**: Escalabilidade, governança e hardening (2 a 4 semanas)
  - Particionamento, tuning de índices, observabilidade e auditoria completa.
  - Políticas de retenção, controles de acesso e runbooks operacionais.

## 10. User stories

### 10.1 Cadastrar e versionar fonte de ingestão

- **ID**: GH-DDB-001
- **Description**: Como admin da plataforma, quero cadastrar uma fonte com contrato versionado para controlar mudanças sem quebrar o pipeline.
- **Acceptance criteria**:
  - Permite criar fonte com tipo, credenciais, janela e política de execução.
  - Registra versão do contrato de dados por fonte.
  - Bloqueia ativação quando campos obrigatórios do contrato estiverem ausentes.

### 10.2 Executar ingestão por fonte com ciclo de vida independente

- **ID**: GH-DDB-002
- **Description**: Como operador, quero executar ingestão por fonte de forma isolada para evitar impacto cruzado entre conectores.
- **Acceptance criteria**:
  - Cada fonte possui status independente (`ready`, `running`, `failed`, `paused`).
  - Falha em uma fonte não interrompe execução das demais.
  - Execuções registram início, fim, volume processado e motivo de falha.

### 10.3 Normalizar domínio para formato canônico

- **ID**: GH-DDB-003
- **Description**: Como sistema, quero normalizar domínios recebidos para garantir deduplicação consistente.
- **Acceptance criteria**:
  - Aplica lowercase, punycode e remoção de trailing dot.
  - Valida formato e rejeita entradas inválidas com motivo persistido.
  - Mesmo domínio de fontes diferentes converge para a mesma chave canônica.

### 10.4 Consolidar base central com merge idempotente

- **ID**: GH-DDB-004
- **Description**: Como sistema, quero consolidar observações em uma base central sem duplicação para manter consistência histórica.
- **Acceptance criteria**:
  - Primeira ocorrência cria domínio com `first_seen_at` e fonte inicial.
  - Reobservações atualizam apenas `last_seen_at` quando aplicável.
  - Reprocessamento da mesma janela não cria linhas duplicadas.

### 10.5 Armazenar observações append-only por fonte

- **ID**: GH-DDB-005
- **Description**: Como analista, quero histórico imutável de observações para auditar origem e evolução dos dados.
- **Acceptance criteria**:
  - Cada observação persiste `domain`, `source`, `observed_at` e referência bruta.
  - Eventos históricos não são sobrescritos por execuções futuras.
  - Consulta por intervalo temporal retorna observações ordenadas.

### 10.6 Inferir data de registro com confiança

- **ID**: GH-DDB-006
- **Description**: Como analista, quero uma estimativa de `registered_at_best` com score de confiança para priorizar investigação.
- **Acceptance criteria**:
  - Sistema calcula ranking de confiança por fonte.
  - Atualiza `registered_at_best` quando nova evidência tiver maior confiança.
  - Em empate, mantém regra determinística com data mais antiga.

### 10.7 Persistir snapshot DNS atual e histórico

- **ID**: GH-DDB-007
- **Description**: Como analista, quero visualizar estado DNS atual e histórico recente para avaliar atividade técnica do domínio.
- **Acceptance criteria**:
  - Captura A, AAAA, NS, MX, TXT, CNAME e status da coleta.
  - Mantém referência ao último snapshot para leitura rápida.
  - Falhas de resolução (timeout, nx_domain, servfail) são persistidas como estado.

### 10.8 Consultar domínios e observações via API

- **ID**: GH-DDB-008
- **Description**: Como consumidor interno, quero APIs de consulta para usar a base em inteligência e detecção.
- **Acceptance criteria**:
  - Endpoint lista domínios com filtros por TLD e faixa de `first_seen_at`.
  - Endpoint de detalhe retorna domínio, fontes recentes e DNS atual.
  - Endpoint de observações suporta filtro por fonte e período.

### 10.9 Reprocessar janela de ingestão com segurança

- **ID**: GH-DDB-009
- **Description**: Como operador, quero reprocessar períodos específicos para corrigir lacunas sem corromper histórico.
- **Acceptance criteria**:
  - Permite reprocessamento por fonte e intervalo temporal.
  - Mantém idempotência e consistência após reexecução.
  - Registra trilha de auditoria com motivo e usuário executor.

### 10.10 Monitorar saúde operacional do pipeline

- **ID**: GH-DDB-010
- **Description**: Como operador, quero métricas e status de execução para agir rapidamente em falhas.
- **Acceptance criteria**:
  - Disponibiliza métricas de throughput, latência e taxa de erro por fonte.
  - Exibe últimas execuções com status final e erros acionáveis.
  - Permite identificar backlog e tempo de atraso por conector.

### 10.11 Garantir segurança e autorização nas operações administrativas

- **ID**: GH-DDB-011
- **Description**: Como admin da plataforma, quero controles de acesso e auditoria para proteger ingestões e credenciais.
- **Acceptance criteria**:
  - Apenas perfis autorizados acessam endpoints administrativos.
  - Alterações de configuração e execuções críticas geram eventos de auditoria.
  - Credenciais de fontes pagas são armazenadas de forma protegida e nunca retornadas em leitura.

### 10.12 Escalar modelagem para volume total de internet

- **ID**: GH-DDB-012
- **Description**: Como arquitetura de plataforma, quero modelagem particionável e modular para suportar crescimento contínuo de volume.
- **Acceptance criteria**:
  - Tabelas de observação suportam particionamento temporal e estratégia de retenção.
  - Índices críticos cobrem filtros de consulta mais frequentes.
  - Pipeline permite adicionar nova fonte sem alterar contrato das fontes já existentes.
