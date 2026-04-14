# Catálogo de Ferramentas — Observador de Domínios

> Documento de referência técnica e funcional de todas as ferramentas disponíveis na plataforma.
> Descreve o que cada ferramenta faz, sua importância estratégica, quando é acionada e como contribui
> para o score de risco e acionabilidade dos domínios monitorados.

---

## Visão Geral da Arquitetura

Todas as ferramentas seguem uma arquitetura unificada baseada em `BaseToolService`. Cada ferramenta:

- **Possui cache por organização** (TTL configurável por tipo)
- **Respeita rate limits** por ferramenta (30 execuções/hora) e global (200 execuções/hora por organização)
- **Registra ciclo de vida** completo: `running → completed / failed / timeout`
- **Pode ser acionada de três modos**:
  - `manual` — por ação direta do usuário na área de Ferramentas
  - `similarity_enrichment` — durante enriquecimento inline de matches de alta prioridade (`enrich_similarity_match.py`)
  - `enrichment` — ciclo diário agendado por worker (`run_enrichment_cycle_match.py`, agendado às 12:00 UTC)

O resultado de cada ferramenta é persistido como JSONB na tabela `tool_execution` / `monitoring_event.result_data` e pode ser reutilizado dentro do TTL de cache, evitando chamadas redundantes.

---

## Organização por Ondas

| Onda | Propósito |
|------|-----------|
| **Onda 1 — Essenciais** | Diagnóstico técnico básico e classificação inicial de risco |
| **Onda 2 — Enriquecimento** | Sinais avançados de ameaça, infraestrutura e threat intelligence |
| **LLM Assessment** | Parecer analítico especializado gerado por IA ao final do enriquecimento |
| **Health Check** | Verificação da saúde dos domínios oficiais da marca (health_worker, 06:00 UTC) |
| **Ingestão de Domínios** | Pipeline de descoberta de novos domínios via CT Logs, CZDS e OpenINTEL |

---

## Workers e Agendamento

A plataforma opera um conjunto de workers independentes que acionam as ferramentas de forma programada:

| Worker | Arquivo | Horário | Função |
|--------|---------|---------|--------|
| `health_worker` | `backend/app/worker/health_worker.py` | **06:00 UTC diário** | Executa 10 ferramentas de monitoramento nos domínios oficiais de cada marca ativa |
| `scan_worker` / `similarity_worker` | `backend/app/worker/scan_worker.py` | **09:00 UTC diário** | Varredura de similaridade de todas as marcas ativas contra a tabela de domínios |
| `enrichment_worker` | `backend/app/worker/enrichment_worker.py` | **12:00 UTC diário** | Executa Wave 1 + Wave 2 (12 ferramentas) nos top-500 matches ranqueados por marca |
| `assessment_worker` | `backend/app/worker/assessment_worker.py` | **A cada 15 minutos** | Executa LLM Assessment em snapshots cujo estado mudou desde o último parecer |

> **Ordenamento intencional:** Health (06h) → Scan (09h) → Enrichment (12h). A ingestão de zone files (CZDS) ocorre em horário separado (07:00 UTC), antes do scan.

---

## Onda 1 — Ferramentas Essenciais

### 1. DNS Lookup (`dns_lookup`)

**O que faz:**
Consulta os registros DNS públicos do domínio-alvo: `A`, `AAAA`, `CNAME`, `MX`, `NS`, `TXT`. Registra tempo de resposta e status de resolução. Indica inconsistências como ausência de registros esperados.

**Importância:**
É a base de toda investigação técnica. Sem resolução DNS, o domínio não tem superfície operacional detectável. A presença e ausência de tipos de registro específicos (especialmente MX sem A/AAAA) define estratégias de ameaça distintas.

**Quando é acionada:**
- Consulta manual do usuário
- **Inline enrichment** — enriquecimento imediato de matches de alta prioridade (`enrich_similarity_match.py`)
- **Wave 1** — ciclo diário do `enrichment_worker` às 12:00 UTC (`run_enrichment_cycle_match.py`)
- **Health check** — verificação diária dos domínios oficiais das marcas (`health_worker`, 06:00 UTC)

**TTL de cache:** 5 minutos  
**Timeout:** padrão configurado em `TOOLS_DEFAULT_TIMEOUT_SECONDS`

**Contribuição para o score de risco (enriquecimento):**

| Condição | Ajuste de Score | Sinal Gerado |
|----------|-----------------|--------------|
| Domínio sem registros A, AAAA ou MX | `-0.08` | `dns_not_resolving` (low) |
| Domínio com MX mas sem A/AAAA | `+0.12` | `mail_only_infrastructure` (high) |

> **Interpretação:** Um domínio configurado exclusivamente para e-mail sem presença web é um padrão de ameaça de spoofing de e-mail. Nenhuma resolução reduz a prioridade, pois o domínio pode ainda não estar ativo.

---

### 2. WHOIS Lookup (`whois`)

**O que faz:**
Consulta os dados de registro públicos do domínio: registrador, data de criação, data de expiração, status de domínio e nameservers (quando disponíveis). Normaliza campos principais para consumo padronizado. Exibe carimbo de data/hora da coleta.

**Importância:**
Revela a idade do domínio — fator crítico de risco. Domínios recém-registrados que imitam marcas estabelecidas são o padrão mais frequente em campanhas de phishing e typosquatting.

**Quando é acionada:**
- Consulta manual do usuário
- **Inline enrichment** — enriquecimento imediato de matches de alta prioridade (`enrich_similarity_match.py`)
- **Wave 1** — ciclo diário do `enrichment_worker` às 12:00 UTC (`run_enrichment_cycle_match.py`)
- ⚠️ **Não inclusa no health check** — health_worker verifica apenas domínios oficiais da marca (WHOIS não aplicável)

**TTL de cache:** 24 horas  
**Timeout:** padrão configurado em `TOOLS_DEFAULT_TIMEOUT_SECONDS`

**Contribuição para o score de risco (enriquecimento):**

| Condição | Ajuste de Score | Sinal Gerado |
|----------|-----------------|--------------|
| Domínio registrado nos últimos 30 dias | `+0.18` | `recent_registration` (high) |
| Domínio registrado nos últimos 31–90 dias | `+0.10` | `fresh_registration` (medium) |

> **Interpretação:** Domínios novos próximos a marcas estabelecidas recebem penalidade máxima de score, pois o padrão de "registrar e atacar imediatamente" é dominante em ataques de phishing oportunistas.

---

### 3. SSL Check (`ssl_check`)

**O que faz:**
Conecta ao host-alvo via TLS e inspeciona o certificado: emissor (CA), validade, Subject Alternative Names (SAN), Common Name (CN) e dias restantes até expiração. Sinaliza estados críticos como certificado expirado, próximo de expirar ou hostname inválido. Verifica status OCSP.

**Importância:**
A presença de SSL não indica confiabilidade — agentes maliciosos obtêm certificados gratuitos (Let's Encrypt) rotineiramente. Um certificado revogado, entretanto, é um indicador forte de infraestrutura comprometida ou de abuso já identificado por uma CA.

**Quando é acionada:**
- Consulta manual do usuário
- **Inline enrichment** — enriquecimento imediato de matches de alta prioridade (`enrich_similarity_match.py`)
- **Wave 1** — ciclo diário do `enrichment_worker` às 12:00 UTC (`run_enrichment_cycle_match.py`)
- **Health check** — verificação diária dos domínios oficiais das marcas (`health_worker`, 06:00 UTC)

**TTL de cache:** 1 hora  
**Timeout:** padrão configurado em `TOOLS_DEFAULT_TIMEOUT_SECONDS`

**Contribuição para o score de risco (enriquecimento):**

| Condição | Ajuste de Score | Sinal Gerado |
|----------|-----------------|--------------|
| Certificado com status OCSP `revoked` | `+0.25` | `certificate_revoked` (critical) |

> **Interpretação:** Revogação de certificado por uma CA indica que a autoridade emissora identificou uso malicioso ou fraudulento. É um dos sinais mais fortes de infraestrutura de phishing ativa.

---

### 4. HTTP Headers (`http_headers`)

**O que faz:**
Faz uma requisição HTTP ao domínio e coleta os headers da resposta: `Server`, `X-Frame-Options`, `Content-Security-Policy`, `Strict-Transport-Security`, `X-Powered-By`, status HTTP final e URL de redirecionamento. Avalia presença e qualidade dos headers de segurança.

**Importância:**
Determina se o domínio tem uma superfície web ativa. O status HTTP e a URL final de redirect são sinais operacionais importantes — um domínio que resolve e retorna `200` está ativo; redirecionamentos para domínios oficiais podem indicar posse legítima.

**Quando é acionada:**
- Consulta manual do usuário
- **Inline enrichment** — enriquecimento imediato de matches de alta prioridade (`enrich_similarity_match.py`)
- **Wave 1** — ciclo diário do `enrichment_worker` às 12:00 UTC (`run_enrichment_cycle_match.py`)
- **Health check** — verificação diária dos domínios oficiais das marcas (`health_worker`, 06:00 UTC)

**TTL de cache:** 15 minutos
**Timeout:** padrão configurado em `TOOLS_DEFAULT_TIMEOUT_SECONDS`

**Contribuição para o score de risco (enriquecimento):**

| Condição | Ajuste de Score | Sinal Gerado |
|----------|-----------------|--------------|
| Status HTTP 200 | `+0.05` | `live_http_surface` (medium) |
| Status HTTP 401, 403, 429 ou 503 | `+0.06` | `restricted_live_surface` (medium) |
| URL final começa com `https://` | `+0.03` | `https_enabled` (low) |

> **Interpretação:** Superfície HTTP ativa aumenta levemente a prioridade, pois indica que o domínio está operando. A disponibilidade de HTTPS por si só não reduz risco (qualquer domínio pode obtê-lo gratuitamente), mas é registrada como contexto.

---

### 5. Screenshot Capture (`screenshot`)

**O que faz:**
Abre o domínio em um navegador headless e captura uma screenshot da página inicial (viewport 1280×720). Registra o título da página, URL final após redirecionamentos e status de navegação (carregou, timeout, bloqueado). A imagem é armazenada no S3/MinIO com referência temporal, acessível via endpoint `/v1/tools/screenshots/`.

**Importância:**
Gera evidência visual auditável do estado da página em um determinado momento. Essencial para triagem humana, registro legal e validação de alertas. Não contribui diretamente para o score numérico, mas é usada como suporte ao enriquecimento (especialmente no clone detector).

**Quando é acionada:**
- Consulta manual do usuário
- **Inline enrichment** — enriquecimento imediato de matches de alta prioridade (`enrich_similarity_match.py`)
- **Wave 1** — ciclo diário do `enrichment_worker` às 12:00 UTC (`run_enrichment_cycle_match.py`)
- ⚠️ **Não inclusa no health check** — health_worker não coleta screenshots de domínios oficiais

**TTL de cache:** 30 minutos  
**Timeout:** `TOOLS_SCREENSHOT_TIMEOUT_SECONDS` (timeout estendido para captura de browser)

**Contribuição para o score de risco:**
Não gera ajuste numérico direto. Fornece contexto visual para análise humana e é pré-requisito para a ferramenta de clone detection.

---

### 6. Suspicious Page Detector (`suspicious_page`)

**O que faz:**
Acessa o domínio via HTTP/HTTPS, faz parse do HTML e analisa o conteúdo em busca de sinais de ameaça:

- **Formulários de coleta de credenciais**: campos `<input type="password">`, ações de form para URLs externas
- **Termos de credenciais**: `password`, `login`, `CPF`, `cartão`, `CVV`, `bank account` (20+ termos em PT/EN)
- **Linguagem de urgência/engenharia social**: `sua conta foi`, `verify your`, `expires today`, `act now` (20+ frases)
- **Impersonação de marca**: padrões de bancos brasileiros, Correios, Receita Federal, gov.br
- **Infraestrutura PhaaS/phishing kit**: paths como `/admin/login.php`, `/gate.php`, `/api/capture`; padrões no body como `evilginx`, `darcula`, `collectdata(`
- **Página parked/à venda**: domínio inativo com página de revenda
- **Página protegida por challenge**: Cloudflare, DDoS-Guard, acesso restrito

Gera um `risk_score` (0.0–1.0) e `risk_level` (`safe`, `low`, `medium`, `high`, `critical`, `protected`, `inconclusive`).

**Importância:**
É a ferramenta de maior poder discriminatório para detecção de phishing ativo. Identifica diretamente os elementos que compõem um ataque: captura de credenciais, imitação de marca, infraestrutura de kit de phishing. Um resultado `critical` nessa ferramenta sozinho pode elevar o score final do match significativamente.

**Quando é acionada:**
- Consulta manual do usuário
- **Inline enrichment** — enriquecimento imediato de matches de alta prioridade (`enrich_similarity_match.py`)
- **Wave 1** — ciclo diário do `enrichment_worker` às 12:00 UTC (`run_enrichment_cycle_match.py`)
- **Health check** — verificação diária dos domínios oficiais das marcas (`health_worker`, 06:00 UTC)

**TTL de cache:** 30 minutos
**Timeout:** padrão configurado em `TOOLS_DEFAULT_TIMEOUT_SECONDS`

**Contribuição para o score de risco (enriquecimento):**

| Condição | Ajuste de Score | Sinal Gerado |
|----------|-----------------|--------------|
| Página parked/à venda | `-0.22` | `parked_or_for_sale_page` (low) |
| Página com challenge/bloqueio | `+0.05` | `protected_or_blocked_page` (medium) |
| Formulário de login ou campo de senha presente | `+0.26` | `credential_collection_surface` (critical) |
| `risk_level` da página = `critical` | `+0.22` | — |
| `risk_level` da página = `high` | `+0.14` | — |
| `risk_level` da página = `medium` | `+0.06` | — |
| Conteúdo com impersonação de marca | `+0.18` | `brand_impersonation_content` (high) |
| Linguagem de engenharia social detectada | `+0.10` | `social_engineering_language` (medium) |
| Infraestrutura mascarada (DDoS-Guard) | `+0.08` | `shielded_infrastructure` (medium) |
| Padrões de PhaaS/phishing kit | `+0.15` | `phishing_kit_indicator` (high) |

> **Interpretação:** A presença de formulário de coleta de credenciais (`+0.26`) combinada com impersonação de marca (`+0.18`) e conteúdo de risco crítico (`+0.22`) pode resultar em ajuste de `+0.66` só desta ferramenta, praticamente garantindo classificação `immediate_attention` ao match.

---

## Onda 2 — Ferramentas de Enriquecimento

### 7. Blacklist Check (`blacklist_check`)

**O que faz:**
Consulta o IP do domínio-alvo em múltiplas listas DNSBL (DNS-based Blackhole Lists):

| Lista | Categoria |
|-------|-----------|
| Spamhaus ZEN | spam |
| SpamCop | spam |
| SORBS | spam |
| Barracuda | spam |
| SURBL Multi | malware |
| Spamhaus DBL | domain |
| URIBL | spam |
| 0spam | spam |
| PSBL | spam |
| SpamRats NoPtr | spam |

Retorna quais listas identificaram o IP/domínio, categoria de cada listagem e score consolidado.

**Importância:**
Permite correlacionar o domínio suspeito com histórico de abuso já detectado por provedores de segurança globais. Um domínio listado no Spamhaus ou SURBL tem histórico documentado de envio de spam ou distribuição de malware.

**Quando é acionada:**
- Consulta manual do usuário
- **Wave 2** — ciclo diário do `enrichment_worker` às 12:00 UTC (`run_enrichment_cycle_match.py`)
- **Health check** — verificação diária dos domínios oficiais das marcas (`health_worker`, 06:00 UTC)
- ⚠️ **Não inclusa no inline enrichment** — não é chamada em `enrich_similarity_match.py` por ser ferramenta de threat intel externa com quota

**TTL de cache:** 1 hora  
**Timeout:** padrão configurado em `TOOLS_DEFAULT_TIMEOUT_SECONDS`

**Contribuição para o score de risco:**
Os resultados de blacklist são disponibilizados no snapshot do match após o ciclo diário, mas os ajustes de score são calculados indiretamente via `StateAggregator.recalculate_match_snapshot()` que consolida todos os sinais disponíveis.

---

### 8. Email Security Check (`email_security`)

**O que faz:**
Consulta e avalia os registros de segurança de e-mail do domínio:
- **SPF** (Sender Policy Framework): define quais IPs podem enviar e-mail pelo domínio
- **DMARC**: política de autenticação, reporte e descarte de e-mails não autorizados
- **DKIM**: chaves públicas para assinatura digital de e-mails enviados

Calcula um `spoofing_risk` com níveis: `none`, `low`, `medium`, `high`, `critical`.

**Importância:**
Um domínio sem SPF/DMARC configurados pode ser usado para enviar e-mails que parecem vir da marca original, sem nenhum bloqueio técnico. É o vetor principal de ataques BEC (Business Email Compromise) e phishing por e-mail.

**Quando é acionada:**
- Consulta manual do usuário
- **Inline enrichment** — enriquecimento imediato de matches de alta prioridade (`enrich_similarity_match.py`)
- **Wave 2** — ciclo diário do `enrichment_worker` às 12:00 UTC (`run_enrichment_cycle_match.py`)
- **Health check** — verificação diária dos domínios oficiais das marcas (`health_worker`, 06:00 UTC)

**TTL de cache:** 6 horas  
**Timeout:** padrão configurado em `TOOLS_DEFAULT_TIMEOUT_SECONDS`

**Contribuição para o score de risco (enriquecimento):**

| Condição | Ajuste de Score | Sinal Gerado | `delivery_risk` |
|----------|-----------------|--------------|-----------------|
| `spoofing_risk` = `critical` | `+0.16` | `high_spoofing_risk` (high) | `high` (se sem web ou mail-only) |
| `spoofing_risk` = `high` | `+0.09` | `elevated_spoofing_risk` (medium) | `high` (se mail-only) |
| `spoofing_risk` = `medium` (sem web ou mail-only) | sem ajuste | — | `possible` |

> **Interpretação:** A combinação de `mail_only_infrastructure` (DNS) com `spoofing_risk` = `critical` (Email Security) produz `delivery_risk = "high"`, sinalizando que o domínio está configurado especificamente para enviar e-mails fraudulentos em nome da marca.

---

### 9. Reverse IP Lookup (`reverse_ip`)

**O que faz:**
A partir do IP resolvido do domínio-alvo, busca todos os outros domínios hospedados no mesmo endereço IP (passive DNS reverso). Utiliza dados de provedores de passive DNS.

**Importância:**
Permite identificar co-hospedagem suspeita — múltiplos domínios fraudulentos em um mesmo servidor são padrão comum em infraestrutura de phishing em escala. Se o IP hospeda dezenas de domínios com padrões similares, aumenta a certeza de que se trata de infraestrutura coordenada de ataque.

**Quando é acionada:**
- Consulta manual do usuário
- Ferramenta de investigação pontual — **não inclusa em nenhum pipeline de enriquecimento automático**

**TTL de cache:** 6 horas  
**Timeout:** padrão configurado em `TOOLS_DEFAULT_TIMEOUT_SECONDS`

**Contribuição para o score de risco:**
Ferramenta de contexto e investigação. Não possui ajuste de score direto no pipeline atual de enriquecimento.

---

### 10. IP Geolocation (`ip_geolocation`)

**O que faz:**
Resolve o IP do domínio e consulta sua geolocalização: país, cidade, ASN (Autonomous System Number), nome da organização provedora e código de país.

**Importância:**
A localização da infraestrutura é um sinal de risco contextual. Domínios imitando marcas brasileiras hospedados em países com alta associação a cibercrime ou grupos APT (como RU, BY, KP, IR) recebem penalidade adicional. Também detecta uso de DDoS-Guard — infraestrutura frequentemente associada a hosting de conteúdo malicioso.

**Quando é acionada:**
- Consulta manual do usuário
- **Inline enrichment** — enriquecimento imediato de matches de alta prioridade (`enrich_similarity_match.py`)
- **Wave 2** — ciclo diário do `enrichment_worker` às 12:00 UTC (`run_enrichment_cycle_match.py`)
- ⚠️ **Não inclusa no health check** — health_worker não usa ip_geolocation

**TTL de cache:** 24 horas
**Timeout:** padrão configurado em `TOOLS_DEFAULT_TIMEOUT_SECONDS`

**Contribuição para o score de risco (enriquecimento):**

| Condição | Ajuste de Score | Sinal Gerado |
|----------|-----------------|--------------|
| IP hospedado em país de alto risco (RU, BY, KP, IR) | `+0.12` | `unusual_hosting_country` (medium) |
| Provedor/ASN associado ao DDoS-Guard | `+0.08` | `shielded_hosting_provider` (medium) |

> **Interpretação:** Países de alto risco são considerados jurisdições com menor cooperação em remoção de conteúdo malicioso, aumentando a probabilidade de que uma ameaça identificada permaneça ativa por mais tempo.

---

### 11. Domain Similarity Generator (`domain_similarity`)

**O que faz:**
Gera variantes do domínio-alvo aplicando técnicas algorítmicas de typosquatting:
- Substituição de caracteres (teclado adjacente)
- Transposição de letras
- Inserção/remoção de caracteres
- Homógrafos (caracteres visualmente similares)
- Adição de prefixos/sufixos comuns (`login-`, `-app`, `-secure`)
- Variações de TLD com base no corpus de TLDs mais populares no banco de dados

Para cada variante gerada, verifica se o domínio está registrado (DNS resolution).

**Importância:**
Funciona como ferramenta ofensiva reversa — ao gerar o espaço de ataque possível de uma marca, permite que a plataforma descubra domínios infratores proativamente antes de serem usados em ataques.

**Quando é acionada:**
- Consulta manual do usuário (análise ad hoc de um domínio)
- O pipeline principal de monitoramento usa o `similarity_worker` com lógica dedicada (não esta ferramenta diretamente)

**TTL de cache:** 24 horas  
**Timeout:** 60 segundos (estendido por verificar DNS de múltiplas variantes)

**Contribuição para o score de risco:**
Ferramenta de geração de cobertura. Não gera ajuste direto no score de matches individuais.

---

### 12. Website Clone Detector (`website_clone`)

**O que faz:**
Compara dois domínios — o domínio suspeito e o domínio de referência (oficial da marca) — e detecta similaridade visual e estrutural entre as páginas:
- Comparação de HTML estruturado (DOM)
- Comparação de recursos externos carregados
- Análise de similaridade de screenshots (estrutura visual)
- Detecção de reutilização de assets (imagens, fontes, scripts)

Retorna um score de similaridade e indicação de clone confirmado/possível/não detectado.

**Importância:**
Clones de página são o vetor mais direto de phishing — o atacante copia exatamente a aparência do site legítimo para enganar usuários. Detectar um clone confirmado é o sinal mais forte de phishing ativo disponível na plataforma.

**Quando é acionada:**
- Consulta manual do usuário (formato: `dominio-suspeito.com|marca-referencia.com`)
- **Inline enrichment** — automaticamente para matches `immediate_attention` que não são domínios oficiais e cuja marca possui um domínio primário registrado (`enrich_similarity_match.py`)
- **Ciclo diário** — condicionalmente para matches `immediate_attention` no ciclo do `enrichment_worker` às 12:00 UTC (`run_enrichment_cycle_match.py`)

**TTL de cache:** 1 hora  
**Timeout:** 90 segundos (screenshots + análise de duas páginas)

**Contribuição para o score de risco (enriquecimento):**

| Condição | Sinal Gerado |
|----------|--------------|
| Clone detectado | `clone_detected` → reclassificação para `immediate_attention` + score máximo |

> **Interpretação:** A presença de `clone_detected` em `signal_codes` aciona diretamente o bucket `immediate_attention` independentemente do score numérico, pois é evidência direta de impersonação ativa.

---

### 13. Subdomain Takeover Check (`subdomain_takeover_check`)

**O que faz:**
Analisa os registros DNS do domínio em busca de subdomínios com CNAMEs ou registros NS apontando para serviços externos que não estão mais ativos (dangling DNS). Verifica padrões conhecidos de takeover em serviços como GitHub Pages, Heroku, AWS S3, Azure, Fastly, entre outros.

**Importância:**
Um subdomain takeover permite que um atacante reivindique controle sobre um subdomínio de uma marca legítima (ex: `app.marca.com`) apontando-o para infraestrutura que ele controla, usando o domínio oficial para phishing com credibilidade total.

**Quando é acionada:**
- Consulta manual do usuário
- **Health check** — verificação diária dos domínios oficiais das marcas (`health_worker`, 06:00 UTC)
- ⚠️ **Não inclusa em nenhum pipeline de enriquecimento de matches externos** — ferramenta de monitoramento defensivo da própria marca

**TTL de cache:** 6 horas  
**Timeout:** padrão configurado em `TOOLS_DEFAULT_TIMEOUT_SECONDS`

**Contribuição para o score de risco:**
Ferramenta de monitoramento defensivo da própria marca. Não possui ajuste de score direto no pipeline atual de enriquecimento de matches externos.

---

### 14. Safe Browsing Check (`safe_browsing_check`)

**O que faz:**
Consulta a API do Google Safe Browsing para verificar se o domínio ou URL está classificado como ameaça ativa nas bases de dados do Google. Retorna os tipos de ameaça detectados: `MALWARE`, `SOCIAL_ENGINEERING`, `UNWANTED_SOFTWARE`, `POTENTIALLY_HARMFUL_APPLICATION`.

**Importância:**
O Google Safe Browsing é uma das maiores e mais confiáveis bases de dados de ameaças da internet. Um domínio listado ali já foi processado e verificado pelo Google como ativo em atividade maliciosa. É um dos sinais de maior confiança disponíveis.

**Quando é acionada:**
- Consulta manual do usuário
- **Inline enrichment** — enriquecimento imediato de matches de alta prioridade (`enrich_similarity_match.py`)
- **Wave 2** — ciclo diário do `enrichment_worker` às 12:00 UTC (`run_enrichment_cycle_match.py`)
- **Health check** — verificação diária dos domínios oficiais das marcas (`health_worker`, 06:00 UTC)

**TTL de cache:** 1 hora  
**Timeout:** padrão configurado em `TOOLS_DEFAULT_TIMEOUT_SECONDS`

**Contribuição para o score de risco (enriquecimento):**

| Condição | Ajuste de Score | Sinal Gerado |
|----------|-----------------|--------------|
| Domínio listado no Google Safe Browsing | `+0.30` | `safe_browsing_hit` (critical) |

> **Interpretação:** Um hit no Safe Browsing representa uma das penalidades mais altas individuais do sistema (`+0.30`), pois indica que o Google já classificou o domínio como ameaça verificada e ativa.

---

### 15. URLhaus Check (`urlhaus_check`)

**O que faz:**
Consulta o banco de dados do URLhaus (Abuse.ch) para verificar se o domínio está associado a URLs de distribuição de malware. Retorna o status de listagem, número de URLs maliciosas associadas e data da última detecção.

**Importância:**
O URLhaus é uma plataforma colaborativa de threat intelligence focada em URLs de download de malware. Um domínio presente no URLhaus é um indicador forte de C2 (command and control) ou hospedagem de payloads maliciosos.

**Quando é acionada:**
- Consulta manual do usuário
- **Inline enrichment** — enriquecimento imediato de matches de alta prioridade (`enrich_similarity_match.py`)
- **Wave 2** — ciclo diário do `enrichment_worker` às 12:00 UTC (`run_enrichment_cycle_match.py`)
- **Health check** — verificação diária dos domínios oficiais das marcas (`health_worker`, 06:00 UTC)

**TTL de cache:** 1 hora  
**Timeout:** padrão configurado em `TOOLS_DEFAULT_TIMEOUT_SECONDS`

**Contribuição para o score de risco (enriquecimento):**

| Condição | Ajuste de Score | Sinal Gerado |
|----------|-----------------|--------------|
| Domínio listado no URLhaus | `+0.20` | `urlhaus_malware_listed` (high) |

---

### 16. PhishTank Check (`phishtank_check`)

**O que faz:**
Consulta o banco de dados do PhishTank (OpenPhish / Cisco Talos) para verificar se o domínio possui URLs de phishing registradas. Retorna se o domínio está na base de dados, se a URL foi verificada pela comunidade e se ainda está ativa.

**Importância:**
O PhishTank é uma base de dados colaborativa de phishing com verificação comunitária. A presença de uma URL verificada e ativa é um dos sinais mais definitivos de phishing em operação.

**Quando é acionada:**
- Consulta manual do usuário
- **Inline enrichment** — enriquecimento imediato de matches de alta prioridade (`enrich_similarity_match.py`)
- **Wave 2** — ciclo diário do `enrichment_worker` às 12:00 UTC (`run_enrichment_cycle_match.py`)
- **Health check** — verificação diária dos domínios oficiais das marcas (`health_worker`, 06:00 UTC)

**TTL de cache:** 1 hora  
**Timeout:** padrão configurado em `TOOLS_DEFAULT_TIMEOUT_SECONDS`

**Contribuição para o score de risco (enriquecimento):**

| Condição | Ajuste de Score | Sinal Gerado |
|----------|-----------------|--------------|
| URL verificada e ativa no PhishTank | `+0.28` | `phishtank_verified_phish` (critical) |
| Presente na base mas ainda não verificado | `+0.12` | `phishtank_in_database` (high) |

> **Interpretação:** Um phishing verificado pelo PhishTank (`+0.28`) combinado com um hit no Safe Browsing (`+0.30`) pode resultar em `+0.58` de ajuste apenas por threat intelligence, levando qualquer match a `immediate_attention` independentemente dos demais sinais.

---

## LLM Assessment (Parecer por Inteligência Artificial)

### Gerador de Parecer LLM (`generate_llm_assessment`)

**O que faz:**
Ao final do pipeline de enriquecimento, consolida todos os dados coletados pelas ferramentas (WHOIS, DNS, HTTP, Página, Email, Geolocalização, Sinais) em um sumário estruturado e envia para um modelo de linguagem (via OpenRouter) com o papel de especialista em segurança cibernética.

O modelo recebe instrução para raciocinar em três etapas:
1. Avaliação de similaridade visual com a marca
2. Confirmação técnica de atividade maliciosa pelos dados coletados
3. Determinação do nível de risco real considerando todos os sinais

O retorno é um JSON estruturado com:
- `risco_score` (0–100)
- `categoria` (`Phishing Provável`, `Tiposquatting`, `Homograph`, `Legítimo`, `Alto Risco Corporativo`)
- `parecer_resumido` (6–8 linhas em português profissional)
- `principais_motivos` (lista de razões)
- `recomendacao_acao` (`Bloquear imediatamente`, `Monitorar`, `Ignorar`)
- `confianca` (0–100)

**Importância:**
Transforma dados técnicos em linguagem acessível para analistas de marca, jurídico e times de segurança não técnicos. Fornece um parecer especializado contextualizado que seria inviável de produzir manualmente para o volume de domínios monitorados.

**Quando é acionado:**
- **`assessment_worker`** — worker dedicado que roda **a cada 15 minutos**, processando 10 snapshots por ciclo
- Critérios de acionamento (qualquer um):
  - `risk_level` ∈ `{medium, high, critical}` OU `attention_bucket` ∈ `{immediate_attention, defensive_gap}`
  - `llm_source_fingerprint != state_fingerprint` (estado mudou desde o último parecer)
  - Último parecer há mais de 7 dias (`last_derived_at`)
  - Nunca avaliado antes
- **Requer** `OPENROUTER_API_KEY` configurado

**Modelos LLM (ordem de fallback via OpenRouter):**

| Ordem | Modelo |
|-------|--------|
| 1 | `nvidia/nemotron-3-super-120b-a12b:free` |
| 2 | `google/gemma-3-27b-it:free` |
| 3 | `google/gemma-2-9b-it:free` |
| 4 | `mistralai/mistral-7b-instruct:free` |
| 5 | `meta-llama/llama-3.2-3b-instruct:free` |
| 6 | `qwen/qwen-2-7b-instruct:free` |

> Todos os modelos são gratuitos via OpenRouter. Quando o modelo 1 falha, o sistema automaticamente tenta o próximo. Se **todos** os modelos esgotarem a quota diária, `DailyQuotaExhaustedError` é levantado e **o ciclo inteiro do assessment_worker é interrompido** até o próximo ciclo de 15 minutos.

**Contribuição para o score de risco:**
O LLM Assessment não altera o score numérico diretamente. Sua função é enriquecer a apresentação do resultado para tomada de decisão humana. O `risco_score` retornado pelo LLM é um campo separado (`llm_assessment.risco_score`) e não sobrescreve o `actionability_score` calculado algoritmicamente.

---

## Resumo: Score de Risco e Acionabilidade

O **score de acionabilidade** de um match de similaridade é calculado em duas fases:

### Fase 1 — Score Léxico (`compute_actionability`)

Baseado apenas em análise de similaridade de texto e metadados do match:

| Fator | Peso |
|-------|------|
| Score de similaridade final | `× 0.35` (base) |
| Domínio registrado nos últimos 30 dias | `+0.18` |
| Domínio registrado nos últimos 31–90 dias | `+0.08` |
| Regra `typo_candidate` | `+0.38` |
| Regra `homograph` | `+0.42` |
| Regra `brand_plus_keyword` | `+0.34` |
| Regra `exact_label_match` (label oficial) | `+0.32` |
| Regra `exact_label_match` (seed associada à marca) | `+0.16` |
| Regra `brand_containment` (seed oficial) | `+0.10` |
| Regra `brand_containment` (seed associada) | `+0.04` |
| TLD estratégico (com, net, org, app, io, ai...) | `+0.05` |
| `risk_level` alto ou crítico | `+0.10` |
| Keyword `login` no label do domínio | `+0.10` |
| Seed genérica (sem especificidade de marca) | `-0.10` a `-0.12` |

### Fase 2 — Enriquecimento por Ferramentas (`enrich_similarity_match`)

Ajustes aplicados ao score após execução das ferramentas:

| Ferramenta | Sinal | Peso Máximo |
|------------|-------|-------------|
| **WHOIS** | Registro recente (≤30 dias) | `+0.18` |
| **WHOIS** | Registro recente (31–90 dias) | `+0.10` |
| **DNS** | Mail-only infrastructure | `+0.12` |
| **DNS** | Domínio sem resolução | `-0.08` |
| **HTTP Headers** | Live surface (HTTP 200) | `+0.05` |
| **Suspicious Page** | Credential collection surface | `+0.26` |
| **Suspicious Page** | Brand impersonation content | `+0.18` |
| **Suspicious Page** | Phishing kit indicator | `+0.15` |
| **Suspicious Page** | Risk level critical | `+0.22` |
| **Email Security** | High spoofing risk (critical) | `+0.16` |
| **IP Geolocation** | País de alto risco | `+0.12` |
| **SSL Check** | Certificado revogado | `+0.25` |
| **Safe Browsing** | Listed (qualquer ameaça) | `+0.30` |
| **URLhaus** | Malware listed | `+0.20` |
| **PhishTank** | Phish verificado e ativo | `+0.28` |
| **Website Clone** | Clone detectado | → `immediate_attention` direto |

### Classificação Final — Attention Bucket

| Bucket | Critério |
|--------|----------|
| `immediate_attention` | Credential capture + brand impersonation + clone **OU** score ≥ 0.80 com regra de typo/homograph **OU** score ≥ 0.72 com risco high/critical |
| `defensive_gap` | Exact match no label oficial **OU** score entre 0.48 e 0.80 |
| `watchlist` | Score < 0.48 ou match em seed genérico |

---

## Regras de Auto-Descarte (`_check_auto_dismiss`)

Ao final do ciclo diário de enriquecimento (`enrichment_worker`, 12:00 UTC), o sistema avalia 3 regras de auto-descarte. Se qualquer regra for atendida, o match é marcado como `dismissed` automaticamente, removendo-o da fila de atenção ativa.

| Regra | ID | Condição |
|-------|----|----------|
| **Score baixo pós-enriquecimento** | `low_score_post_enrichment` | `derived_score < 0.35` AND sem sinais `critical` ou `high` AND não é `exact_label_match` |
| **Domínio morto** | `dead_domain` | Sem registros DNS + Sem MX + Idade > 365 dias + sem sinais `critical` ou `high` |
| **Domínio à venda / parked** | `parked_for_sale` | Página do tipo `parked` + Sem MX + Safe Browsing limpo + URLhaus limpo + PhishTank limpo |

> **Importante:** A regra `dead_domain` requer que o domínio tenha mais de 365 dias para evitar falso-positivo em domínios recém-registrados que ainda não propagaram DNS. A regra `parked_for_sale` exige que todas as três fontes de threat intelligence estejam limpas — um domínio parked com qualquer hit de ameaça **não** é descartado.

---

## Infraestrutura de Ingestão de Domínios

A plataforma mantém uma infraestrutura de ingestão de domínios multi-fonte para garantir cobertura máxima de TLDs. Os novos domínios registrados alimentam a tabela principal de domínios que é consumida pelo `scan_worker` e `similarity_worker`.

### Clientes de Ingestão

| Cliente | Arquivo | Fonte | Protocolo | Cobertura |
|---------|---------|-------|-----------|-----------|
| `CertStreamClient` | `certstream_client.py` | CT Logs (Certificate Transparency) | WebSocket tempo real | Global — todos os TLDs em que certificados SSL são emitidos |
| `CrtShClient` | `crtsh_client.py` | crt.sh (aggregador de CT Logs) | HTTP batch | TLDs não cobertos pelo CertStream em tempo real; fallback/complemento |
| `CZDSClient` | `czds_client.py` | ICANN CZDS (Zone Data Service) | HTTPS — download de zone files | gTLDs autorizados pela ICANN (`.com`, `.net`, `.org`, `.info`, etc.) |
| `OpenIntelClient` | `openintel_client.py` | OpenINTEL — dados de DNS passivo | S3 Parquet (público, anônimo) | gTLDs principais via bucket S3 público da OpenINTEL |
| `OpenIntelCctldClient` | `openintel_client.py` | OpenINTEL — ccTLDs | HTTP CSV.GZ | 307 ccTLDs (`.br`, `.uk`, `.de`, etc.) via arquivos CSV comprimidos |

### Fluxo de Processamento Compartilhado (`ingest_ct_batch.py`)

O pipeline de ingestão de domínios é compartilhado por CertStream e crt.sh:

1. **Normalizar** — lowercase, strip wildcards (`*.domain` → `domain`), TLD extraction via `tldextract`, filtro por lista de TLDs autorizados, deduplicação
2. **Garantir partições** — cria partições de tabela para novos TLDs se necessário
3. **Bulk upsert** — insere domínios novos, ignora duplicatas (upsert por TLD)
4. **Atualizar métricas** — registra `ingestion_run` com `{domains_seen, domains_inserted, by_tld}`

### Sincronização CZDS (`sync_czds_tld.py`)

O cliente CZDS usa autenticação JWT e inclui:
- Controle de cooldown por TLD (evita re-download desnecessário)
- Detecção de sync já em execução (idempotência)
- Upload para S3 do zone file comprimido antes do processamento
- Aplicação de delta (`apply_zone_delta`) — apenas domínios novos são inseridos

### Sincronização OpenINTEL (`sync_openintel_tld.py`)

- gTLDs: lê arquivos Parquet do S3 público da OpenINTEL anonimamente
- ccTLDs: baixa CSV.GZ via HTTP público
- Verifica se o snapshot mais recente já foi ingerido (idempotência por snapshot date)
- Não pode rodar simultaneamente com CZDS para o mesmo TLD (`CzdsRunningError`)

---

## Estrutura de Dados Retornada por Ferramenta

> Esta seção documenta o payload JSON que cada ferramenta persiste na tabela `tool_execution.result_data`.
> Os exemplos são representativos de resultados reais — campos opcionais podem estar ausentes dependendo do estado da execução.

---

### `dns_lookup` — Payload de Resultado

```json
{
  "records": [
    { "type": "A",    "name": "itau-login-seguro.com", "value": "104.21.45.12",                   "ttl": 300 },
    { "type": "AAAA", "name": "itau-login-seguro.com", "value": "2606:4700::6815:2d0c",            "ttl": 300 },
    { "type": "MX",   "name": "itau-login-seguro.com", "value": "10 mail.itau-login-seguro.com.",  "ttl": 3600 },
    { "type": "NS",   "name": "itau-login-seguro.com", "value": "ns1.hostgator.com.",              "ttl": 86400 },
    { "type": "TXT",  "name": "itau-login-seguro.com", "value": "v=spf1 include:spf.hostgator.com ~all", "ttl": 3600 }
  ],
  "nameservers": ["ns1.hostgator.com", "ns2.hostgator.com"],
  "resolution_time_ms": 87
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `records` | `list[dict]` | Todos os registros DNS encontrados por tipo |
| `records[].type` | `string` | Tipo do registro: `A`, `AAAA`, `MX`, `NS`, `TXT`, `CNAME`, `SOA`, `CAA` |
| `records[].value` | `string` | Valor do registro em formato texto |
| `records[].ttl` | `int` | Time-to-live em segundos |
| `nameservers` | `list[string]` | Nameservers autoritativos do domínio |
| `resolution_time_ms` | `int` | Latência total da consulta em milissegundos |

**Sinal de risco extraído:** presença de `MX` + ausência de `A`/`AAAA` → `mail_only_infrastructure`

---

### `whois` — Payload de Resultado

```json
{
  "domain_name": "itau-login-seguro.com",
  "registrar": "GoDaddy.com, LLC",
  "creation_date": "2026-03-28 14:12:00",
  "expiration_date": "2027-03-28 14:12:00",
  "updated_date": "2026-03-28 14:12:00",
  "name_servers": ["ns1.hostgator.com", "ns2.hostgator.com"],
  "status": ["clientTransferProhibited"],
  "registrant_name": null,
  "registrant_organization": null,
  "registrant_country": "BR",
  "dnssec": "unsigned",
  "raw_text": "Domain Name: ITAU-LOGIN-SEGURO.COM\nRegistrar: GoDaddy.com, LLC\n...",
  "lookup_status": "ok",
  "availability_reason": null,
  "confidence": 0.9,
  "data_quality": "complete"
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `creation_date` | `string \| null` | Data de registro do domínio (ISO 8601 ou string raw) |
| `registrar` | `string \| null` | Registrador |
| `registrant_country` | `string \| null` | País do registrante (quando disponível) |
| `lookup_status` | `string` | `ok` \| `not_found` \| `redacted` \| `rate_limited` \| `technical_error` |
| `data_quality` | `string` | `complete` \| `degraded` \| `inconclusive` |
| `confidence` | `float` | 0.0–1.0 — confiabilidade dos dados retornados |

**Sinal de risco extraído:** `creation_date` ≤ 30 dias → `recent_registration`

---

### `ssl_check` — Payload de Resultado

```json
{
  "is_valid": true,
  "certificate": {
    "subject": "itau-login-seguro.com",
    "issuer": "Let's Encrypt",
    "serial_number": "03A2B4F18E2C9D47",
    "not_before": "Mar 28 00:00:00 2026 UTC",
    "not_after": "Jun 26 00:00:00 2026 UTC",
    "days_remaining": 15,
    "san": ["itau-login-seguro.com", "www.itau-login-seguro.com"],
    "signature_algorithm": null,
    "version": 3,
    "ocsp_status": "revoked"
  },
  "chain_length": 2,
  "protocol_version": "TLSv1.3",
  "cipher_suite": "TLS_AES_256_GCM_SHA384",
  "issues": ["Certificate expires in 15 days"]
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `is_valid` | `bool` | Se o certificado é tecnicamente válido |
| `certificate.issuer` | `string` | Autoridade Certificadora emissora |
| `certificate.days_remaining` | `int \| null` | Dias até expiração (negativo = expirado) |
| `certificate.san` | `list[string]` | Nomes alternativos cobertos pelo certificado |
| `certificate.ocsp_status` | `string` | `good` \| `revoked` \| `unknown` \| `unavailable` |
| `protocol_version` | `string` | Versão do protocolo TLS negociado |
| `issues` | `list[string]` | Lista de problemas detectados |

**Sinal de risco extraído:** `ocsp_status = "revoked"` → `certificate_revoked` (+0.25)

---

### `http_headers` — Payload de Resultado

```json
{
  "final_url": "https://itau-login-seguro.com/acesso",
  "status_code": 200,
  "headers": {
    "server": "nginx/1.18.0",
    "content-type": "text/html; charset=utf-8",
    "x-powered-by": "PHP/7.4.33",
    "set-cookie": "sess=abc123; path=/; HttpOnly"
  },
  "security_headers": [
    { "name": "Strict-Transport-Security", "value": null,        "present": false, "severity": "critical", "description": "Enforces HTTPS connections" },
    { "name": "Content-Security-Policy",   "value": null,        "present": false, "severity": "critical", "description": "Prevents XSS and injection attacks" },
    { "name": "X-Frame-Options",           "value": null,        "present": false, "severity": "warning",  "description": "Prevents clickjacking attacks" },
    { "name": "X-Content-Type-Options",    "value": "nosniff",   "present": true,  "severity": "good",     "description": "Prevents MIME type sniffing" }
  ],
  "redirect_chain": [
    { "url": "http://itau-login-seguro.com/", "status_code": 301 }
  ],
  "server": "nginx/1.18.0",
  "content_type": "text/html; charset=utf-8"
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `final_url` | `string` | URL final após todos os redirecionamentos |
| `status_code` | `int` | Código HTTP da resposta final |
| `security_headers` | `list[dict]` | Avaliação dos 7 headers de segurança padrão |
| `security_headers[].severity` | `string` | `good` \| `warning` \| `critical` (quando ausente) |
| `redirect_chain` | `list[dict]` | Cadeia de redirecionamentos com URL e status |
| `server` | `string \| null` | Identificação do servidor web |

**Sinal de risco extraído:** `status_code == 200` → `live_http_surface` (+0.05)

---

### `screenshot` — Payload de Resultado

```json
{
  "screenshot_url": "/v1/tools/screenshots/itau-login-seguro.com/f47ac10b-58cc-4372-a567-0e02b2c3d479.png",
  "s3_key": "tools/screenshots/itau-login-seguro.com/f47ac10b-58cc-4372-a567-0e02b2c3d479.png",
  "page_title": "Itaú — Acesse sua conta",
  "final_url": "https://itau-login-seguro.com/login",
  "viewport_width": 1280,
  "viewport_height": 720
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `screenshot_url` | `string \| null` | URL relativa para acesso à imagem via API |
| `s3_key` | `string \| null` | Chave no S3/MinIO onde a imagem está armazenada |
| `page_title` | `string \| null` | Título da página HTML no momento da captura |
| `final_url` | `string` | URL final após redirecionamentos do browser |
| `viewport_width` / `viewport_height` | `int` | Dimensões do viewport utilizado (1280×720) |

> **Nota:** `screenshot_url` e `s3_key` serão `null` se o upload para S3 falhar. A imagem é capturada com Playwright (Chromium headless).

---

### `suspicious_page` — Payload de Resultado

```json
{
  "risk_score": 0.85,
  "risk_level": "critical",
  "signals": [
    {
      "category": "credential_harvesting",
      "description": "Found 2 password input field(s)",
      "severity": "high"
    },
    {
      "category": "credential_harvesting",
      "description": "Login form posts to external URL: https://collector.malicious.xyz/gate.php",
      "severity": "critical"
    },
    {
      "category": "brand_impersonation",
      "description": "References brand 'banco itau' not in domain name",
      "severity": "high"
    },
    {
      "category": "social_engineering",
      "description": "Urgency language detected: sua conta foi, verify your, act now",
      "severity": "medium"
    }
  ],
  "page_title": "Itaú — Acesse sua conta",
  "final_url": "https://itau-login-seguro.com/acesso",
  "http_status": 200,
  "page_disposition": "live",
  "has_login_form": true,
  "has_credential_inputs": true,
  "has_phishing_kit_indicators": false,
  "external_resource_count": 8,
  "confidence": 0.85,
  "data_quality": "complete"
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `risk_score` | `float` | Score de risco da página (0.0–1.0) |
| `risk_level` | `string` | `safe` \| `low` \| `medium` \| `high` \| `critical` \| `protected` \| `inconclusive` |
| `signals` | `list[dict]` | Lista de sinais detectados com categoria e severidade |
| `signals[].category` | `string` | `credential_harvesting` \| `brand_impersonation` \| `social_engineering` \| `phishing_kit_infrastructure` \| `parked_domain` \| `protected_page` \| `infrastructure_masking` \| `resource_loading` |
| `signals[].severity` | `string` | `critical` \| `high` \| `medium` \| `low` |
| `page_disposition` | `string` | `live` \| `parked` \| `challenge` \| `unreachable` |
| `has_login_form` | `bool` | Formulário com campo de senha detectado |
| `has_credential_inputs` | `bool` | Inputs de senha (`<input type="password">`) presentes |
| `has_phishing_kit_indicators` | `bool` | Padrões de PhaaS/kit detectados em URL ou body |

**Score calculado:** soma dos pesos por severidade — `critical=0.4`, `high=0.25`, `medium=0.15`, `low=0.05`, limitado a `1.0`

---

### `blacklist_check` — Payload de Resultado

```json
{
  "domain": "itau-login-seguro.com",
  "ip": "104.21.45.12",
  "listed_count": 3,
  "total_checked": 10,
  "risk_level": "medium",
  "listings": [
    { "name": "Spamhaus ZEN",   "zone": "zen.spamhaus.org",       "category": "spam",    "listed": false },
    { "name": "SURBL Multi",    "zone": "multi.surbl.org",         "category": "malware", "listed": true  },
    { "name": "Spamhaus DBL",   "zone": "dbl.spamhaus.org",        "category": "domain",  "listed": true  },
    { "name": "SpamCop",        "zone": "bl.spamcop.net",          "category": "spam",    "listed": false },
    { "name": "SORBS",          "zone": "dnsbl.sorbs.net",         "category": "spam",    "listed": true  },
    { "name": "Barracuda",      "zone": "b.barracudacentral.org",  "category": "spam",    "listed": false },
    { "name": "URIBL",          "zone": "uribl.com",               "category": "spam",    "listed": false },
    { "name": "0spam",          "zone": "0spam.fusioned.net",      "category": "spam",    "listed": false },
    { "name": "PSBL",           "zone": "psbl.surriel.com",        "category": "spam",    "listed": false },
    { "name": "SpamRats NoPtr", "zone": "noptr.spamrats.com",      "category": "spam",    "listed": false }
  ]
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `ip` | `string \| null` | IP resolvido do domínio (usado nas consultas IP-based) |
| `listed_count` | `int` | Quantas listas identificaram o domínio/IP |
| `total_checked` | `int` | Total de listas consultadas (sempre 10) |
| `risk_level` | `string` | `clean` (0) \| `low` (1) \| `medium` (2–3) \| `high` (4+) |
| `listings` | `list[dict]` | Resultado por lista, com `category`: `spam`, `malware`, `domain` |

---

### `email_security` — Payload de Resultado

```json
{
  "domain": "itau-login-seguro.com",
  "spf": {
    "present": false,
    "record": null,
    "policy": null,
    "includes": [],
    "issues": ["No SPF record found — domain may be spoofed"]
  },
  "dmarc": {
    "present": false,
    "record": null,
    "policy": null,
    "subdomain_policy": null,
    "percentage": null,
    "rua": null,
    "ruf": null,
    "issues": ["No DMARC record found — domain not protected against spoofing"]
  },
  "dkim": {
    "found": false,
    "selectors_found": [],
    "selectors_checked": ["default", "google", "k1", "k2", "mail", "dkim", "selector1", "selector2", "s1", "s2", "smtp", "email", "mandrill", "mailjet", "sendgrid"]
  },
  "spoofing_risk": {
    "score": 100,
    "level": "critical"
  },
  "mta_sts": {
    "has_record": false,
    "has_policy_file": false,
    "mode": null,
    "policy_id": null
  }
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `spf.present` | `bool` | Se existe registro SPF no DNS |
| `spf.policy` | `string \| null` | `fail` \| `softfail` \| `pass_all` \| `neutral` \| `none` |
| `dmarc.policy` | `string \| null` | `reject` \| `quarantine` \| `none` |
| `dmarc.rua` | `string \| null` | Endereço de relatórios agregados configurado |
| `dkim.found` | `bool` | Se algum seletor DKIM foi encontrado |
| `dkim.selectors_found` | `list[dict]` | Seletores encontrados com registro DKIM |
| `spoofing_risk.score` | `int` | Score 0–100 (menor = mais seguro) |
| `spoofing_risk.level` | `string` | `low` \| `medium` \| `high` \| `critical` |
| `mta_sts.mode` | `string \| null` | `enforce` \| `testing` \| `none` |

**Score de spoofing calculado:** SPF ausente (+35), DMARC ausente (+40), DKIM ausente (+25) → máximo 100

---

### `reverse_ip` — Payload de Resultado

```json
{
  "domain": "itau-login-seguro.com",
  "ip": "104.21.45.12",
  "domains": [
    "bradesco-acesso-seguro.com",
    "login-nubank-app.net",
    "santander-verificacao.com",
    "itau-conta-digital.com.br"
  ],
  "total": 47,
  "truncated": true
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `ip` | `string \| null` | IP resolvido do domínio consultado |
| `domains` | `list[string]` | Outros domínios hospedados no mesmo IP (máx. 100) |
| `total` | `int` | Total de co-hospedeiros encontrados |
| `truncated` | `bool` | Se a lista foi limitada a 100 registros |
| `error` | `string` | Presente apenas em caso de falha na consulta |

---

### `ip_geolocation` — Payload de Resultado

```json
{
  "domain": "itau-login-seguro.com",
  "ip": "195.82.24.110",
  "country": "Russia",
  "country_code": "RU",
  "region": "Moscow Oblast",
  "city": "Zelenograd",
  "latitude": 55.9842,
  "longitude": 37.1922,
  "isp": "Selectel Ltd",
  "org": "AS197695 Selectel Ltd",
  "asn": "AS197695",
  "source": "ip-api"
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `country_code` | `string \| null` | Código ISO 3166-1 alpha-2 do país |
| `isp` | `string \| null` | Nome do provedor de internet |
| `org` | `string \| null` | Organização responsável pelo bloco de IP |
| `asn` | `string \| null` | Número de sistema autônomo (`AS` + número) |
| `source` | `string` | `geoip2` (base local MaxMind) ou `ip-api` (fallback) |

**Países de alto risco avaliados:** `RU`, `BY`, `KP`, `IR`

---

### `domain_similarity` — Payload de Resultado

```json
{
  "domain": "itau.com.br",
  "total_generated": 312,
  "registered_count": 14,
  "variants": [
    { "domain": "itat.com.br",      "type": "substitution" },
    { "domain": "itau.net.br",      "type": "tld_variation" },
    { "domain": "ìtau.com.br",      "type": "substitution" },
    { "domain": "itauu.com.br",     "type": "duplication_or_insertion" },
    { "domain": "login-itau.com.br","type": "prefix_hyphen" },
    { "domain": "itau-app.com.br",  "type": "suffix_hyphen" }
  ],
  "registered": [
    { "domain": "itat.com.br",      "type": "substitution" },
    { "domain": "itau.net.br",      "type": "tld_variation" },
    { "domain": "login-itau.com.br","type": "prefix_hyphen" }
  ]
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `total_generated` | `int` | Total de variantes algoritmicamente geradas |
| `registered_count` | `int` | Quantas variantes estão ativamente registradas |
| `variants` | `list[dict]` | Todas as variantes geradas com tipo de mutação |
| `registered` | `list[dict]` | Apenas as variantes com resolução DNS confirmada |
| `variants[].type` | `string` | `omission` \| `substitution` \| `duplication_or_insertion` \| `hyphen` \| `tld_variation` \| `prefix` \| `suffix` \| `prefix_hyphen` \| `suffix_hyphen` \| `unknown` |

---

### `website_clone` — Payload de Resultado

```json
{
  "target": "itau-login-seguro.com",
  "reference": "itau.com.br",
  "target_domain": "itau-login-seguro.com",
  "reference_domain": "itau.com.br",
  "scores": {
    "overall": 0.81,
    "visual": 0.88,
    "textual": 0.76,
    "structural": 0.73
  },
  "is_clone": true,
  "confidence": "high",
  "verdict": "likely_clone",
  "errors": [],
  "comparison_state": "complete",
  "target_access_state": "ok",
  "reference_access_state": "ok"
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `scores.overall` | `float` | Score composto: visual (40%) + texto (35%) + estrutura (25%) |
| `scores.visual` | `float \| null` | Similaridade por pHash de screenshots (0.0–1.0) |
| `scores.textual` | `float` | Similaridade de conteúdo texto por cosine similarity |
| `scores.structural` | `float` | Similaridade de estrutura DOM por cosine similarity |
| `is_clone` | `bool` | `true` quando `overall >= 0.75` |
| `verdict` | `string` | `likely_clone` \| `suspicious` \| `low_similarity` \| `not_similar` \| `error` |
| `confidence` | `string` | `high` (≥0.75) \| `medium` (0.50–0.74) \| `low` (<0.50) |
| `comparison_state` | `string` | `complete` \| `partial_comparison` \| `failed` |

---

### `subdomain_takeover_check` — Payload de Resultado

```json
{
  "is_vulnerable": true,
  "cname_chain": ["app.marca.com.br", "marca-app.github.io"],
  "vulnerable_cname": "marca-app.github.io",
  "fingerprint_matched": "There isn't a GitHub Pages site here",
  "service": "GitHub Pages",
  "checked_url": "http://app.marca.com.br"
}
```

Resultado quando **não vulnerável:**
```json
{
  "is_vulnerable": false,
  "cname_chain": ["app.marca.com.br", "active-backend.azurewebsites.net"],
  "vulnerable_cname": "active-backend.azurewebsites.net",
  "fingerprint_matched": null,
  "service": null,
  "checked_url": "http://app.marca.com.br"
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `is_vulnerable` | `bool` | Se takeover é possível (fingerprint confirmado) |
| `cname_chain` | `list[string]` | Cadeia de CNAMEs seguida até o destino final |
| `vulnerable_cname` | `string \| null` | Último CNAME da cadeia (o alvo desprovisionado) |
| `fingerprint_matched` | `string \| null` | Texto de fingerprint encontrado na página HTTP |
| `service` | `string \| null` | Serviço identificado: `GitHub Pages`, `Amazon S3`, `Heroku`, `Fastly`, etc. |

**Serviços monitorados:** GitHub Pages, Amazon S3, Heroku, Fastly, Shopify, Zendesk, Surge.sh, Tumblr, Ghost, Bitbucket (14 fingerprints)

---

### `safe_browsing_check` — Payload de Resultado

```json
{
  "is_listed": true,
  "threat_types": ["SOCIAL_ENGINEERING", "MALWARE"],
  "skipped": false
}
```

Resultado quando **não listado:**
```json
{
  "is_listed": false,
  "threat_types": [],
  "skipped": false
}
```

Resultado quando **API key ausente:**
```json
{
  "is_listed": false,
  "threat_types": [],
  "skipped": true
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `is_listed` | `bool` | Se o domínio está em alguma lista do Google |
| `threat_types` | `list[string]` | Tipos de ameaça: `MALWARE` \| `SOCIAL_ENGINEERING` \| `UNWANTED_SOFTWARE` \| `POTENTIALLY_HARMFUL_APPLICATION` |
| `skipped` | `bool` | `true` quando `GOOGLE_SAFE_BROWSING_API_KEY` não configurado |

---

### `urlhaus_check` — Payload de Resultado

```json
{
  "query_status": "is_host",
  "is_listed": true,
  "urls_count": 7,
  "urls": [
    {
      "id": "2891234",
      "url": "https://itau-login-seguro.com/download/payload.exe",
      "url_status": "online",
      "threat": "malware_download",
      "tags": ["exe", "trojan"],
      "date_added": "2026-03-30 18:22:00"
    }
  ],
  "skipped": false
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `query_status` | `string` | `is_host` (listado) \| `no_results` \| `invalid_host` \| `error` \| `skipped` |
| `is_listed` | `bool` | `true` apenas quando `query_status == "is_host"` |
| `urls_count` | `int` | Total de URLs maliciosas associadas ao host |
| `urls` | `list[dict]` | Amostra de até 10 URLs (payload bruto da API abuse.ch) |
| `skipped` | `bool` | `true` quando `URLHAUS_AUTH_TOKEN` não configurado |

---

### `phishtank_check` — Payload de Resultado

```json
{
  "in_database": true,
  "verified": true,
  "valid": true,
  "phish_id": "7823441"
}
```

Resultado quando **não encontrado:**
```json
{
  "in_database": false,
  "verified": false,
  "valid": false,
  "phish_id": null
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `in_database` | `bool` | URL foi submetida ao PhishTank |
| `verified` | `bool` | Comunidade confirmou como phishing |
| `valid` | `bool` | URL ainda está ativa (não removida) |
| `phish_id` | `string \| null` | ID do registro no PhishTank para referência |

**Combinação mais crítica:** `verified = true` + `valid = true` → `phishtank_verified_phish` (+0.28)

---

### LLM Assessment — Payload de Resultado

```json
{
  "risco_score": 92,
  "categoria": "Phishing Provável",
  "parecer_resumido": "O domínio itau-login-seguro.com apresenta múltiplos indicadores convergentes de campanha de phishing ativa contra clientes do Banco Itaú. Registrado há 14 dias, exibe formulário de captura de credenciais com ação direcionada a servidor externo em jurisdição russa. O certificado SSL foi revogado pela Let's Encrypt, indicando que a própria CA identificou uso malicioso. A similaridade visual com o portal legítimo do banco é de 81%, confirmada como clone provável. O domínio está listado no Google Safe Browsing como SOCIAL_ENGINEERING. Recomenda-se notificação imediata ao CERT.br e solicitação de takedown junto ao registrador.",
  "principais_motivos": [
    "Formulário de login com submissão para servidor externo em RU",
    "Certificado SSL revogado pela CA emissora",
    "Clone visual confirmado do portal itau.com.br (score 0.81)",
    "Listado no Google Safe Browsing como SOCIAL_ENGINEERING",
    "Domínio registrado há 14 dias com infraestrutura mail-only"
  ],
  "recomendacao_acao": "Bloquear imediatamente",
  "confianca": 96
}
```

**Campos-chave:**
| Campo | Tipo | Descrição |
|---|---|---|
| `risco_score` | `int` | Score de risco avaliado pelo LLM (0–100) — não sobrescreve `actionability_score` |
| `categoria` | `string` | `Phishing Provável` \| `Tiposquatting` \| `Homograph` \| `Legítimo` \| `Alto Risco Corporativo` |
| `parecer_resumido` | `string` | Análise em português (6–8 linhas) |
| `principais_motivos` | `list[string]` | Fatores determinantes para a classificação |
| `recomendacao_acao` | `string` | `Bloquear imediatamente` \| `Monitorar` \| `Ignorar` |
| `confianca` | `int` | Confiança do modelo na avaliação (0–100) |

> **Importante:** O `risco_score` do LLM é informativo e armazenado em `llm_assessment.risco_score`. O `actionability_score` principal do match é calculado algoritmicamente pelas Fases 1 e 2 e não é sobrescrito pelo LLM.

---

## Referências de Código

| Componente | Localização |
|-----------|-------------|
| Base de todas as ferramentas | `backend/app/services/use_cases/tools/base.py` |
| Registro de ferramentas | `backend/app/services/use_cases/tools/registry.py` |
| Pipeline de enriquecimento | `backend/app/services/use_cases/enrich_similarity_match.py` |
| Score léxico | `backend/app/services/use_cases/compute_actionability.py` |
| LLM Assessment | `backend/app/services/use_cases/generate_llm_assessment.py` |
| Clientes externos | `backend/app/infra/external/` |
| Configuração (TTLs, timeouts, limites) | `backend/app/core/config.py` |

---

*Documento gerado em Abril de 2026. Manter atualizado ao adicionar ou modificar ferramentas.*
