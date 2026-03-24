# PRD: Reverse IP Lookup

## 1. Product overview

### 1.1 Document title and version

- PRD: Reverse IP Lookup
- Version: 1.0

### 1.2 Product summary

Este PRD define a ferramenta de Reverse IP Lookup do Observador de Domínios. O objetivo é descobrir outros domínios hospedados no mesmo endereço IP de um domínio investigado.

Domínios de phishing e typosquatting frequentemente compartilham infraestrutura. Um único servidor pode hospedar dezenas de domínios fraudulentos. Identificar "vizinhos" de IP revela padrões de abuso (múltiplos domínios similares a marcas diferentes no mesmo servidor) e ajuda a dimensionar a operação maliciosa.

## 2. Goals

### 2.1 Business goals

- Revelar infraestrutura compartilhada de operações maliciosas.
- Enriquecer investigação com contexto de co-hospedagem.
- Diferenciar domínios em hosting legítimo vs. infraestrutura suspeita.

### 2.2 User goals

- Descobrir outros domínios no mesmo IP para identificar padrões.
- Avaliar se o IP hospeda múltiplos domínios suspeitos.
- Documentar evidência de infraestrutura maliciosa compartilhada.

### 2.3 Non-goals

- Não realiza scan de portas no IP.
- Não identifica proprietário do IP (use WHOIS de IP para isso).
- Não monitora mudanças contínuas de co-hospedagem.

## 3. User personas

### 3.1 Key user types

- Analista de marca/risco
- Analista de segurança
- Operações internas

### 3.2 Basic persona details

- **Analista de marca/risco**: quer saber se o IP hospeda outros domínios suspeitos similares.
- **Analista de segurança**: precisa mapear infraestrutura para dimensionar ameaça.
- **Operações internas**: precisa de contexto adicional para triagem de alertas.

### 3.3 Role-based access

- **Cliente autenticado**: executa lookup e consulta histórico próprio.
- **Operador interno**: executa lookup em triagem de incidentes.
- **Admin interno**: gerencia fontes de dados e observabilidade.

## 4. Functional requirements

- **Resolução de IP** (Priority: Alta)
  - Resolver domínio para IP(s) caso o input seja um domínio.
  - Aceitar IP direto como input alternativo.
  - Mostrar IP(s) resolvido(s) como contexto.

- **Consulta de domínios co-hospedados** (Priority: Alta)
  - Consultar fonte de dados de reverse DNS / passive DNS.
  - Retornar lista de domínios hospedados no mesmo IP.
  - Limitar resultado a um máximo razoável (ex.: 100 primeiros).
  - Indicar total estimado quando houver mais resultados.

- **Sinais de contexto** (Priority: Média)
  - Indicar quantidade total de domínios encontrados.
  - Sinalizar quando o número é alto (shared hosting massivo).
  - Destacar domínios que contenham palavras-chave relevantes (marca do cliente, se disponível).
  - Indicar se algum domínio co-hospedado já aparece em blacklists (cross-reference).

- **Persistência de histórico** (Priority: Média)
  - Salvar resultado por organização.
  - Permitir comparação com execuções anteriores.

## 5. User experience

### 5.1 Entry points & first-time user flow

- Entrada na área de Ferramentas.
- Campo de domínio ou IP com validação imediata.
- Botão "Reverse IP Lookup".

### 5.2 Core experience

- **Inserir domínio ou IP**: usuário informa o alvo.
  - Se domínio, resolve para IP automaticamente.
- **Executar busca**: sistema consulta base de dados de co-hospedagem.
  - Loading com indicação de progresso.
- **Ver resultados**: contagem total + lista de domínios + sinais de contexto.
  - Facilita identificação de padrões.

### 5.3 Advanced features & edge cases

- IPs de CDNs grandes (Cloudflare, AWS) podem retornar milhares de domínios — sinalizar e limitar.
- Domínios com múltiplos IPs (load balancing) devem ser consultados por cada IP.
- Base de passive DNS pode ter dados defasados — indicar data da última atualização.

### 5.4 UI/UX highlights

- Badge com contagem total de domínios no IP.
- Lista paginada/scrollável com destaque em domínios relevantes.
- Aviso contextual quando IP é de CDN/shared hosting massivo.
- Ação rápida para investigar qualquer domínio da lista com outras ferramentas.

## 6. Narrative

Um analista investiga um domínio de typosquatting. Executa o Reverse IP e descobre que o mesmo servidor hospeda outros 15 domínios, vários deles imitando marcas diferentes. Isso indica uma operação organizada de phishing, não um incidente isolado. A informação é documentada e escalada.

## 7. Success metrics

### 7.1 User-centric metrics

- Tempo médio de resposta menor que 8 segundos.
- Taxa de consultas com resultados úteis maior que 70%.

### 7.2 Business metrics

- Adoção por pelo menos 30% dos usuários ativos do módulo.
- Contribuição para identificação de operações organizadas em pelo menos 15% dos casos.

### 7.3 Technical metrics

- P95 de latência menor que 15 segundos.
- Taxa de erro técnico menor que 5%.

## 8. Technical considerations

### 8.1 Integration points

- Endpoint backend dedicado para Reverse IP Lookup.
- Integração com APIs de passive DNS (ex.: SecurityTrails, HackerTarget, VirusTotal).
- Cross-reference opcional com Blacklist Check.

### 8.2 Data storage & privacy

- Armazenar lista resumida de domínios encontrados e contagem.
- Escopo de acesso por organização.
- Auditoria de execução interna.

### 8.3 Scalability & performance

- Cache por IP (30-60 minutos) — dados mudam lentamente.
- Rate limit por organização.
- Paginação de resultados grandes.

### 8.4 Potential challenges

- APIs de passive DNS podem ter limites de consulta ou requerer chave.
- IPs de CDN retornam resultados massivos e pouco úteis.
- Dados podem estar defasados dependendo da fonte.

## 9. Milestones & sequencing

### 9.1 Project estimate

- S: 1 a 1,5 semana

### 9.2 Team size & composition

- 2 a 3 pessoas: 1 Backend, 1 Frontend, 1 QA parcial

### 9.3 Suggested phases

- **Fase 1**: API e integração com fonte de dados (3 dias)
  - Resolução de IP, consulta reverse DNS, normalização.
- **Fase 2**: Interface e sinais de contexto (2 a 3 dias)
  - Lista de resultados, destaques, paginação, persistência.

## 10. User stories

### 10.1 Descobrir domínios co-hospedados

- **ID**: GH-RIP-001
- **Description**: Como analista, quero ver quais domínios compartilham o mesmo IP para identificar infraestrutura maliciosa.
- **Acceptance criteria**:
  - Resolve domínio para IP quando necessário.
  - Lista domínios co-hospedados (até 100).
  - Indica total estimado quando há mais resultados.

### 10.2 Identificar padrões de abuso

- **ID**: GH-RIP-002
- **Description**: Como analista, quero sinais visuais que destaquem domínios relevantes na lista para triagem rápida.
- **Acceptance criteria**:
  - Destaca domínios contendo palavras-chave da marca monitorada.
  - Sinaliza IPs de CDN/shared hosting massivo.
  - Indica quantidade total como contexto de risco.

### 10.3 Investigar domínio da lista

- **ID**: GH-RIP-003
- **Description**: Como analista, quero executar outras ferramentas em domínios encontrados para aprofundar investigação.
- **Acceptance criteria**:
  - Cada domínio na lista tem ação rápida para executar Quick Analysis.
  - Navegação sem perder contexto do resultado original.

### 10.4 Revisar histórico de lookups

- **ID**: GH-RIP-004
- **Description**: Como usuário autenticado, quero revisar lookups anteriores para comparar evolução.
- **Acceptance criteria**:
  - Lista consultas com data/hora e contagem de resultados.
  - Permite filtro por domínio/IP e período.
  - Restringe visualização à própria organização.
