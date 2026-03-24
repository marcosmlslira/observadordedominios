# PRD: IP Geolocation

## 1. Product overview

### 1.1 Document title and version

- PRD: IP Geolocation
- Version: 1.0

### 1.2 Product summary

Este PRD define a ferramenta de geolocalização de IP do Observador de Domínios. O objetivo é identificar a localização geográfica aproximada (país, região, cidade), provedor de hospedagem (ASN/ISP) e tipo de rede do IP associado a um domínio investigado.

A localização do servidor é um sinal contextual valioso: uma marca brasileira cujo domínio suspeito resolve para um IP na Rússia ou em um provedor de hosting conhecido por abrigar operações maliciosas (bulletproof hosting) aumenta significativamente o indicativo de risco.

## 2. Goals

### 2.1 Business goals

- Adicionar contexto geográfico à análise de risco.
- Identificar padrões de hospedagem associados a operações maliciosas.
- Complementar outras ferramentas com dados de localização.

### 2.2 User goals

- Saber onde o servidor do domínio suspeito está localizado.
- Identificar o provedor de hospedagem (ISP/ASN).
- Detectar incompatibilidade geográfica (marca local → servidor em país diferente).

### 2.3 Non-goals

- Não fornece geolocalização precisa (nível rua/bairro).
- Não rastreia mudanças históricas de localização.
- Não identifica pessoa física por trás do IP.

## 3. User personas

### 3.1 Key user types

- Analista de marca/risco
- Analista de segurança
- Operações internas

### 3.2 Basic persona details

- **Analista de marca/risco**: precisa de contexto geográfico rápido para avaliar plausibilidade.
- **Analista de segurança**: precisa de ASN/ISP para identificar bulletproof hosting.
- **Operações internas**: precisa de dados para enriquecer relatórios de incidente.

### 3.3 Role-based access

- **Cliente autenticado**: executa consulta e visualiza histórico próprio.
- **Operador interno**: executa consulta em triagem.
- **Admin interno**: gerencia fontes de dados e observabilidade.

## 4. Functional requirements

- **Resolução e geolocalização** (Priority: Alta)
  - Resolver domínio para IP(s) caso input seja domínio.
  - Consultar base de geolocalização para cada IP.
  - Retornar: país (código + nome), região/estado, cidade, coordenadas aproximadas.

- **Informações de rede** (Priority: Alta)
  - Identificar ASN (Autonomous System Number).
  - Identificar ISP/organização responsável.
  - Classificar tipo de hospedagem quando possível: datacenter / residencial / CDN / VPN-proxy.

- **Sinais de contexto** (Priority: Média)
  - Sinalizar provedores conhecidos por bulletproof hosting.
  - Sinalizar incompatibilidade geográfica quando o domínio tem TLD de país diferente da localização.
  - Indicar se IP é de rede Tor, VPN ou proxy conhecidos.

- **Visualização geográfica** (Priority: Baixa)
  - Exibir mapa simples com marcador na localização aproximada.
  - Mapa estático ou embed leve (sem dependência pesada).

- **Persistência de histórico** (Priority: Média)
  - Salvar resultado por organização.
  - Permitir comparação temporal.

## 5. User experience

### 5.1 Entry points & first-time user flow

- Entrada na área de Ferramentas.
- Campo de domínio ou IP com validação imediata.
- Botão "Geolocalizar IP".

### 5.2 Core experience

- **Inserir domínio ou IP**: usuário informa o alvo.
  - Se domínio, resolve para IP automaticamente.
- **Executar consulta**: sistema consulta base de geolocalização.
  - Retorno rápido (dados locais ou API leve).
- **Ver resultado**: localização + rede + sinais de contexto.
  - Interpretação imediata de plausibilidade geográfica.

### 5.3 Advanced features & edge cases

- CDNs (Cloudflare, Akamai) retornam IPs de edge — sinalizar que localização pode ser do edge, não do origin.
- IPv6 pode ter cobertura de geolocalização menor — indicar confiança.
- Anycast IPs podem ter localização variável — sinalizar.

### 5.4 UI/UX highlights

- Flag do país + nome em destaque.
- Badge com tipo de rede (datacenter / residencial / CDN).
- Mapa simples com pin na localização.
- Alerta visual quando há incompatibilidade geográfica ou bulletproof hosting.

## 6. Narrative

Um domínio de typosquatting de uma marca brasileira é detectado. O analista executa a geolocalização e descobre que o IP está em um datacenter na Ucrânia, em um ASN conhecido por abrigar phishing. Esse contexto geográfico, combinado com outros sinais, eleva a prioridade do caso.

## 7. Success metrics

### 7.1 User-centric metrics

- Tempo médio de resposta menor que 3 segundos.
- 95%+ dos resultados incluem pelo menos país e ISP.

### 7.2 Business metrics

- Adoção por pelo menos 45% dos usuários ativos do módulo.
- Contribuição para contexto de risco em pelo menos 50% das análises.

### 7.3 Technical metrics

- P95 de latência menor que 5 segundos.
- Taxa de erro técnico menor que 2%.

## 8. Technical considerations

### 8.1 Integration points

- Endpoint backend dedicado para IP Geolocation.
- Base de dados local (MaxMind GeoLite2) ou API (ipinfo.io, ip-api.com).
- Composição com Quick Analysis e motor de score de risco.

### 8.2 Data storage & privacy

- Armazenar localização e metadados de rede.
- Escopo de acesso por organização.
- Não armazenar coordenadas exatas de IPs residenciais.

### 8.3 Scalability & performance

- Base local (MaxMind) = latência mínima, sem dependência externa.
- Cache por IP (1-24 horas) — geolocalização muda raramente.
- Rate limit por organização.

### 8.4 Potential challenges

- Precisão de geolocalização varia por região e tipo de IP.
- CDNs e anycast IPs retornam localização do edge, não do origin.
- Bases gratuitas (GeoLite2) têm precisão menor que comerciais.

## 9. Milestones & sequencing

### 9.1 Project estimate

- XS: 3 a 5 dias

### 9.2 Team size & composition

- 2 pessoas: 1 Backend, 1 Frontend

### 9.3 Suggested phases

- **Fase 1**: API e integração com base de geolocalização (2 dias)
  - Resolução, consulta, normalização de dados.
- **Fase 2**: Interface e sinais de contexto (1 a 2 dias)
  - Tela de resultados, mapa, alertas, persistência.

## 10. User stories

### 10.1 Geolocalizar IP de domínio

- **ID**: GH-GEO-001
- **Description**: Como analista, quero saber onde o servidor está localizado para avaliar plausibilidade geográfica.
- **Acceptance criteria**:
  - Resolve domínio para IP quando necessário.
  - Retorna país, região, cidade e coordenadas aproximadas.
  - Mostra timestamp da consulta.

### 10.2 Identificar provedor de hospedagem

- **ID**: GH-GEO-002
- **Description**: Como analista, quero identificar o ISP/ASN para detectar provedores suspeitos.
- **Acceptance criteria**:
  - Retorna ASN e nome do ISP/organização.
  - Classifica tipo de rede quando possível.
  - Sinaliza provedores conhecidos por bulletproof hosting.

### 10.3 Detectar incompatibilidade geográfica

- **ID**: GH-GEO-003
- **Description**: Como analista, quero ser alertado sobre incompatibilidades geográficas para priorizar investigação.
- **Acceptance criteria**:
  - Compara TLD do domínio com localização do IP.
  - Sinaliza quando há divergência significativa.
  - Indicação é contextual, não conclusiva.

### 10.4 Revisar histórico de consultas

- **ID**: GH-GEO-004
- **Description**: Como usuário autenticado, quero revisar consultas anteriores para comparar.
- **Acceptance criteria**:
  - Lista consultas com data/hora e localização.
  - Permite filtro por domínio/IP e período.
  - Restringe visualização à própria organização.
