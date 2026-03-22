# PRD: Mecanismos de Pagamento e Assinaturas

## 1. Product overview

### 1.1 Document title and version
- PRD: Mecanismos de Pagamento - Observador de Domínios
- Version: 1.0

### 1.2 Product summary
Este documento especifica a implementação do módulo de pagamentos e assinaturas para o Observador de Domínios. O objetivo é permitir a monetização da plataforma através da cobrança pelo monitoramento contínuo de domínios, utilizando a infraestrutura do Stripe (Checkout Sessions e Billing) para gerenciar planos, recorrências, faturamento e o portal do cliente, garantindo segurança e escalabilidade.

### 1.3 Definições de Negócio Pendentes (Perguntas de Clarificação)
Para refinar este PRD e iniciar o desenvolvimento, precisamos definir as seguintes regras de negócio. **Para me ajudar a criar a melhor solução, você poderia esclarecer:**

1. **Modelagem de Preços e Planos:** Quais serão os pacotes oferecidos (ex: Free, Pro, Agency) e seus respectivos limites de domínios e preços?
2. **Recorrência:** Os ciclos de cobrança serão apenas mensais, ou teremos opções anuais (com desconto)?
3. **Estratégia de Aquisição:** Haverá um plano Freemium (ex: 1 a 3 domínios grátis para sempre) ou um período de Trial (ex: 14 dias grátis no plano Pro)?
4. **Métodos de Pagamento:** Além de cartão de crédito, será necessário suporte a Pix ou Boleto (muito comuns no Brasil)?
5. **Política de Inadimplência (Churn Involuntário):** Qual será o período de carência (grace period) caso a renovação do cartão falhe, antes de o sistema suspender o monitoramento dos domínios do cliente?

## 2. Goals

### 2.1 Business goals
- Monetizar a plataforma de forma escalável, automatizada e com baixo custo operacional.
- Reduzir a fricção no processo de checkout para maximizar a taxa de conversão.
- Minimizar o churn involuntário através de retentativas automáticas de cobrança (dunning) gerenciadas pelo gateway.

### 2.2 User goals
- Assinar um plano de forma rápida, transparente e segura.
- Gerenciar sua própria assinatura (fazer upgrade, downgrade, atualizar cartão ou cancelar) com total autonomia (Self-service).
- Acessar o histórico de faturas e recibos facilmente para prestação de contas.

### 2.3 Non-goals
- Desenvolver um gateway de pagamento ou cofre de cartões próprio (usaremos a infraestrutura do Stripe).
- Suporte a pagamentos em criptomoedas nesta fase inicial.
- Emissão de Notas Fiscais de Serviço (NFS-e) brasileiras diretamente pelo sistema nesta fase (pode ser integrado via eNotas/Focus NFe no futuro).

## 3. User personas

### 3.1 Key user types
- Investidor de Domínios (Domainer)
- Agência de Marketing / Desenvolvedor Web
- Empreendedor Individual

### 3.2 Basic persona details
- **Carlos (Domainer)**: Monitora dezenas de domínios de alto valor para compra e venda. Precisa de um plano que suporte alto volume com bom custo-benefício e não pode correr o risco de ter o monitoramento pausado por uma falha simples no cartão.
- **Ana (Agência)**: Monitora os domínios de seus clientes para garantir que não expirem. Precisa de faturas claras para repassar os custos e facilidade para fazer upgrade de plano conforme sua carteira de clientes cresce.

### 3.3 Role-based access
- **Subscriber (Assinante)**: Tem acesso aos limites do seu plano pago, pode gerenciar métodos de pagamento, ver faturas e alterar o plano.
- **Free User (Usuário Gratuito)**: Acesso limitado à cota gratuita, com chamadas para ação (CTAs) visíveis para realizar o upgrade.

## 4. Functional requirements

- **Integração com Stripe Checkout** (Priority: High)
  - Redirecionamento para página hospedada pelo Stripe para coleta segura de dados de pagamento, suportando 3D Secure e adequação PCI.
- **Gestão de Assinaturas via Stripe Customer Portal** (Priority: High)
  - Portal self-service para o usuário atualizar cartão, cancelar ou alterar plano sem necessidade de acionar o suporte.
- **Sincronização via Webhooks** (Priority: High)
  - O backend (FastAPI) deve escutar eventos do Stripe (`checkout.session.completed`, `invoice.payment_succeeded`, `customer.subscription.deleted`) para atualizar o status e os limites do usuário no banco de dados local.
- **Enforcement de Limites (Paywall)** (Priority: High)
  - O sistema deve restringir a adição de novos domínios com base no limite do plano ativo do usuário.

## 5. User experience

### 5.1 Entry points & first-time user flow
- Banner não intrusivo na dashboard indicando a cota de uso (ex: "3/5 domínios monitorados. Faça upgrade para monitorar mais").
- Modal de "Limite Atingido" ao tentar adicionar um domínio além da cota permitida.
- Página de "Pricing" clara, acessível pelo menu principal, comparando os planos disponíveis.

### 5.2 Core experience
- **Checkout**: O usuário escolhe o plano, clica em "Assinar", é redirecionado ao Stripe Checkout, insere os dados e retorna para uma página de sucesso na plataforma. O limite de domínios é atualizado instantaneamente.
- **Gestão**: Na página de "Configurações > Faturamento", o usuário clica em "Gerenciar Assinatura" e é levado ao Stripe Customer Portal de forma transparente.

### 5.3 Advanced features & edge cases
- **Falha no pagamento**: O usuário recebe um e-mail automático (via Stripe) e um aviso em destaque na dashboard (via webhook no backend) informando que o pagamento falhou e o monitoramento será suspenso em X dias.
- **Proration (Proporcionalidade)**: Ao fazer upgrade no meio do mês, o sistema calcula automaticamente o valor proporcional (prorated) a ser cobrado, garantindo justiça no faturamento.

### 5.4 UI/UX highlights
- Tabelas de preços responsivas usando componentes do `shadcn/ui` (Cards, Buttons, Badges para destacar o plano "Recomendado").
- Feedback visual imediato (Toast/Alert) após o retorno do checkout ou atualização de plano.

## 6. Narrative

Carlos, um investidor de domínios, atinge o limite de 5 domínios gratuitos no Observador de Domínios. Ele tenta adicionar um sexto domínio e recebe um aviso amigável de que atingiu seu limite. Ele clica em "Fazer Upgrade", visualiza a tabela de preços e escolhe o plano "Pro" (até 50 domínios). Ele é redirecionado para o ambiente seguro do Stripe, insere seu cartão de crédito e, em segundos, retorna à plataforma com sua conta atualizada. Ele imediatamente adiciona seus novos domínios para monitoramento, sem precisar contatar o suporte, enquanto a plataforma cuida da cobrança recorrente mensalmente de forma invisível.

## 7. Success metrics

### 7.1 User-centric metrics
- Tempo médio para completar o checkout (< 2 minutos).
- Taxa de sucesso na primeira tentativa de pagamento.

### 7.2 Business metrics
- MRR (Monthly Recurring Revenue).
- Taxa de conversão de usuários Free para Paid.
- Churn rate (voluntário e involuntário).

### 7.3 Technical metrics
- Latência no processamento dos webhooks do Stripe (< 2 segundos).
- Zero divergências de estado entre o banco de dados local e o Stripe.

## 8. Technical considerations

### 8.1 Integration points
- **Frontend (Next.js)**: Integração com Stripe.js para redirecionamento ao Checkout e Customer Portal.
- **Backend (FastAPI)**: Endpoints para criar Checkout Sessions, gerar links do Customer Portal e escutar Webhooks.
- **Stripe API**: Uso exclusivo das APIs modernas `CheckoutSessions` e `Billing/Subscriptions` (conforme best practices do Stripe).

### 8.2 Data storage & privacy
- O banco de dados local (PostgreSQL) armazenará apenas metadados: `stripe_customer_id`, `stripe_subscription_id`, `plan_id` e `status` da assinatura.
- Nenhum dado sensível de cartão de crédito (PAN) transitará ou será armazenado nos servidores do Observador de Domínios, garantindo total conformidade com as normas PCI-DSS.

### 8.3 Scalability & performance
- Webhooks devem ser processados de forma assíncrona (background tasks no FastAPI) para responder rapidamente ao Stripe (evitando timeouts e retentativas desnecessárias).
- Implementação de idempotência no processamento de webhooks para evitar atualizações duplicadas no banco de dados caso o Stripe reenvie um evento.

### 8.4 Potential challenges
- Lidar com a complexidade de estados de assinatura do Stripe (`active`, `past_due`, `canceled`, `incomplete`).
- Sincronização do ambiente de teste (Stripe Test Mode) com o banco de dados de desenvolvimento local via Stripe CLI durante a fase de construção.

## 9. Milestones & sequencing

### 9.1 Project estimate
- Tamanho: Médio (M) - Estimativa de 3 a 4 semanas.

### 9.2 Team size & composition
- 1 Desenvolvedor Full-stack (Next.js + FastAPI).
- 1 Product Manager / Designer (para definição de planos e UI).

### 9.3 Suggested phases
- **Fase 1: Configuração e Modelagem** (3 dias)
  - Criação de Produtos e Preços no Dashboard do Stripe.
  - Atualização dos modelos do banco de dados (Alembic migrations) para suportar os campos do Stripe.
- **Fase 2: Backend e Webhooks** (1 semana)
  - Criação dos endpoints de Checkout Session e Customer Portal.
  - Implementação e segurança da rota recebedora de Webhooks.
- **Fase 3: Frontend e Paywall** (1 semana)
  - Desenvolvimento da página de Preços (`/pricing`).
  - Integração dos botões de checkout e portal.
  - Implementação dos bloqueios (paywall) na adição de domínios.
- **Fase 4: Testes e Go-live** (1 semana)
  - Testes end-to-end simulando pagamentos com sucesso, falhas de cartão, upgrades e cancelamentos.
  - Deploy em produção.

## 10. User stories

### 10.1. Visualizar planos e preços
- **ID**: GH-001
- **Description**: Como usuário, quero visualizar uma página com os planos disponíveis e seus benefícios para decidir qual atende minhas necessidades.
- **Acceptance criteria**:
  - A página deve exibir os planos configurados (ex: Free, Pro).
  - Deve mostrar o preço e a periodicidade (mensal/anual).
  - Deve destacar os limites de domínios de cada plano.
  - Deve ser responsiva (mobile e desktop).

### 10.2. Assinar um plano pago
- **ID**: GH-002
- **Description**: Como usuário, quero poder assinar um plano pago usando meu cartão de crédito de forma segura.
- **Acceptance criteria**:
  - Ao clicar em assinar, o usuário deve ser redirecionado ao Stripe Checkout.
  - Após o pagamento com sucesso, o usuário deve ser redirecionado de volta à aplicação (página de sucesso).
  - O limite de domínios da conta deve ser atualizado imediatamente no banco de dados.

### 10.3. Gerenciar assinatura
- **ID**: GH-003
- **Description**: Como assinante, quero poder alterar meu método de pagamento, baixar faturas ou cancelar minha assinatura.
- **Acceptance criteria**:
  - Deve haver um botão "Gerenciar Assinatura" na área de configurações do usuário.
  - O botão deve gerar uma sessão e redirecionar para o Stripe Customer Portal.
  - Alterações feitas no portal (ex: cancelamento) devem refletir na aplicação via webhooks.

### 10.4. Processamento de Webhooks (Backend)
- **ID**: GH-004
- **Description**: Como sistema, preciso escutar eventos do Stripe para manter o status da assinatura do usuário atualizado no banco de dados.
- **Acceptance criteria**:
  - O endpoint de webhook deve validar a assinatura criptográfica (webhook secret) do Stripe.
  - Deve processar `checkout.session.completed` para ativar a assinatura.
  - Deve processar `customer.subscription.deleted` para revogar o acesso premium.
  - Deve processar `invoice.payment_failed` para atualizar o status para inadimplente/past_due.

### 10.5. Restrição de uso por plano (Paywall)
- **ID**: GH-005
- **Description**: Como sistema, devo impedir que o usuário adicione mais domínios do que o limite do seu plano atual permite.
- **Acceptance criteria**:
  - A API de adição de domínio deve verificar a cota atual do usuário antes de salvar.
  - Se o limite for excedido, deve retornar um erro 403 com mensagem clara.
  - O frontend deve interceptar esse erro e exibir um modal sugerindo o upgrade de plano.