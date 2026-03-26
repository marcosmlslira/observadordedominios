# Plano Estrategico de Melhorias — Domain Similarity & Brand Protection

> Data: 2026-03-25
> Baseado em: North Star 10/10 (vision_10_10.md)
> Metodo: Auditoria de producao (API + UI) + analise profunda do codebase
> Objetivo: Mapear gaps entre estado atual e estado 10/10, priorizar por impacto

---

## 1. Resumo Executivo

O mecanismo de similaridade possui uma **arquitetura bem estruturada** com scoring composto
(5 metricas), triage por actionability, auto-enrichment seletivo e delta scanning via watermarks.
A base de dados e robusta (314M+ dominios ingeridos de 4 fontes).

Porem, **o pipeline ponta-a-ponta tem gaps operacionais criticos** que impedem o produto de
entregar valor real ao cliente:

- **`similarity_worker` NAO esta deployado em producao** — servico existe em stack.dev.yml mas
  esta ausente do stack.yml. Este e o motivo raiz de nenhum scan rodar automaticamente.
- Paginas de Matches e Tools retornaram 404 em producao (pode ser queda temporaria OU
  build de producao nao incluindo estas paginas — requer validacao)
- Marcas recem-criadas nao tiveram scans executados (consequencia direta da ausencia do worker)
- Bug de normalizacao de alias gera falsos positivos ("Tenda" → "enda")
- Sem feedback loop do analista

**Causa raiz dominante:** O stack.yml de producao nao inclui o similarity_worker,
efetivamente desabilitando o monitoramento continuo. O codigo esta pronto, mas o deploy
nao esta completo.

O foco principal deve ser **completar o deploy do pipeline e tornar o fluxo ponta-a-ponta
funcional antes de sofisticar algoritmos**.

---

## 2. Estado Atual por Pilar do North Star

### Pilar 1 — Cobertura correta
| Aspecto | Estado | Nota |
|---------|--------|------|
| Parse de public suffix (com.br, gov.br) | Implementado | Codigo lida com multi-level suffixes |
| TLDs estrategicos no scope | Parcial | Algumas marcas nao incluem .br, .com.br, .gov.br |
| Cobertura real vs declarada | Gap | Nao ha prova visivel de que TLDs declarados tem dados ingeridos |
| Marca entende dominio oficial | Parcial | Algumas marcas nao tem official_domains cadastrados |

### Pilar 2 — Descoberta util
| Aspecto | Estado | Nota |
|---------|--------|------|
| Exact match | Implementado | Via trigram similarity = 1.0 |
| Typo/homograph | Implementado | Gerador de variantes completo |
| Prefixo/sufixo | Implementado | brand_containment + substring match |
| Priorizado por registro real | Implementado | Busca contra base CZDS real |
| Universo gerado vs observado | Parcial | Free tool gera variantes mas nao cruza com base |

### Pilar 3 — Ranking confiavel
| Aspecto | Estado | Nota |
|---------|--------|------|
| Score composto | Implementado | 5 metricas com pesos definidos |
| Oficial nao aparece | Implementado | Pre-scan exclusion |
| Self-owned rebaixado | Parcial | WHOIS + redirect detection, mas limitado |
| Exact-match ativo sobe | Implementado | Bonus de actionability |
| Parked/for-sale como defensive_gap | Implementado | Score -0.22 para parked |
| Typo ativo com credenciais sobe | Implementado | +0.26 para credential_collection |
| Terceiro legitimo antigo rebaixado | Implementado | >365 dias = third_party_legitimate |

### Pilar 4 — Enriquecimento acionavel
| Aspecto | Estado | Nota |
|---------|--------|------|
| DNS | Disponivel como tool | Nao integrado no auto-enrich |
| WHOIS | Integrado | Via auto-enrich |
| SSL | Disponivel como tool | Nao integrado no auto-enrich |
| HTTP Headers | Integrado | Via auto-enrich |
| Screenshot | Disponivel como tool | **Nao integrado no auto-enrich** |
| Page analysis | Integrado | suspicious_page no auto-enrich |
| Mail-only risk | Parcial | Email security check existe mas classificacao fraca |
| Estados explicitos (parked, unreachable, etc.) | Parcial | parked detectado, mas outros estados imprecisos |
| Clone detection | Disponivel como tool | Nao integrado no pipeline |

### Pilar 5 — Tempo operacional
| Aspecto | Estado | Nota |
|---------|--------|------|
| Busca sincrona rapida | **Endpoint retorna 404 em prod** | Nao operacional |
| Scan assincrono com progresso | Implementado no codigo | Sem evidencia de execucao em prod |
| Job com estado observavel | Parcial | scan_cursor existe mas UI nao mostra progresso |
| Queued eterno | Risco | Sem agendamento automatico |

### Pilar 6 — Explicabilidade
| Aspecto | Estado | Nota |
|---------|--------|------|
| Reasons por match | Implementado | Codigos tecnicos (exact_label_match, etc.) |
| Score breakdown | Implementado | 5 sub-scores individuais |
| Recommended action | Implementado | Texto generico, nao contextual |
| Confianca e classificacao | Parcial | attention_bucket existe, disposition incompleto |
| Fonte e qualidade do dado | Gap | Nao mostrado ao usuario |

### Pilar 7 — Operacao continua
| Aspecto | Estado | Nota |
|---------|--------|------|
| Scan automatico recorrente | **Nao implementado** | Somente manual |
| Observabilidade de scans | Parcial | Logs estruturados, sem dashboard |
| Degradacoes perceptiveis | Gap | Sem metricas de performance/qualidade |
| Feedback loop | **Nao implementado** | Decisoes do analista nao retroalimentam |

---

## 3. Bugs e Problemas Criticos Encontrados

### BUG-000: similarity_worker ausente do stack.yml de producao
- **Severidade:** CRITICA (causa raiz de multiplos problemas)
- **Descricao:** O servico `similarity_worker` esta definido em `infra/stack.dev.yml` (linhas 160-176)
  mas esta **completamente ausente** do `infra/stack.yml` (producao)
- **Impacto direto:**
  - Nenhum scan automatico roda em producao (cron `0 9 * * *` nao existe)
  - Nenhum scan manual via fila e processado (worker nao esta consumindo jobs)
  - Marcas com 0 matches (Itau, Caixa, Claro, Sabesp) — nenhum dado de monitoramento
- **Correcao:** Adicionar bloco similarity_worker ao stack.yml identico ao stack.dev.yml
  (com env vars de producao: DATABASE_URL, SIMILARITY_SCAN_CRON)
- **Pilares afetados:** Pilar 5 (Tempo operacional), Pilar 7 (Operacao continua)
- **Nota:** Esta unica correcao resolve T1.3 (primeiro scan) e T2.1 (agendamento automatico)
  simultaneamente, pois o worker ja tem cron integrado

### BUG-001: Normalizacao incorreta de alias
- **Severidade:** Alta
- **Descricao:** O alias "Tenda" (brand_primary) esta normalizado como "enda" ao inves de "tenda"
- **Impacto:** Gera matches falsos positivos (enda.studio, enda.chat, enda.pro) rankeados como high risk
- **Localizacao provavel:** `backend/app/services/monitoring_profile.py` ou `sync_monitoring_profile.py`
- **Correcao:** Verificar logica de normalizacao — parece estar removendo primeira letra
- **Pilar afetado:** Pilar 3 (Ranking confiavel) — viola "dominio oficial ranqueado como suspeito"

### BUG-002: Paginas de Matches e Tools retornam 404
- **Severidade:** Critica
- **Descricao:** Rotas `/admin/matches` e `/admin/tools` retornam 404 em producao
- **Impacto:** Funcionalidade core do produto inacessivel — usuario nao consegue ver resultados
- **Causa provavel:** Frontend build de producao nao inclui estas paginas, ou Traefik nao roteia
- **Pilar afetado:** Pilar 5, 6 (Tempo operacional, Explicabilidade) — produto nao entrega valor

### BUG-003: Endpoint /v1/similarity/search retorna 404
- **Severidade:** Alta
- **Descricao:** API de busca sincrona nao funciona em producao
- **Causa provavel:** Rota nao registrada no deploy ou problema de roteamento Traefik
- **Pilar afetado:** Pilar 5 — "busca sincrona serve para triagem imediata"

### BUG-004: Endpoint /v1/matches/{id} retorna 404
- **Severidade:** Alta
- **Descricao:** Detalhe de match individual nao acessivel via API
- **Pilar afetado:** Pilar 4, 6 — sem acesso a dados de enriquecimento

### BUG-005: Marcas sem official_domains
- **Severidade:** Media
- **Descricao:** Tenda, comgas (versao sem .com.br), gsuplementos (sem .com.br), listenx (sem .com.br) nao tem dominios oficiais cadastrados
- **Impacto:** Sistema nao consegue excluir dominios oficiais dos resultados
- **Pilar afetado:** Pilar 3 — "dominio oficial nao aparece por padrao"

### BUG-006: Perfis de marca duplicados
- **Severidade:** Media
- **Descricao:** Existem pares duplicados: comgas/comgas.com.br, gsuplementos/gsuplementos.com.br, listenx/listenx.com.br
- **Impacto:** Confusao operacional, scans duplicados, matches inconsistentes
- **Pilar afetado:** Pilar 1 — cobertura confusa

---

## 4. Plano de Melhorias Priorizado

### TIER 1 — Fundacao Funcional (Sem isso, produto nao entrega valor)
> Prioridade: CRITICA | Prazo sugerido: 1-2 sprints

#### T1.0: Adicionar similarity_worker ao stack.yml de producao ★ CAUSA RAIZ
- Adicionar servico `similarity_worker` ao `infra/stack.yml` espelhando `stack.dev.yml`
- Configurar env vars de producao: DATABASE_URL, SIMILARITY_SCAN_CRON=0 9 * * *
- Rebuild e deploy da imagem backend para producao
- **Entregavel:** Worker rodando em producao, consumindo fila de scans e executando cron diario
- **Validacao:** `docker service ls` mostra similarity_worker com 1/1 replicas
- **Impacto:** Esta UNICA mudanca habilita scan automatico diario + consumo de scan jobs manuais
- **Complexidade:** Baixa (copiar bloco de stack.dev.yml, ajustar env vars)

#### T1.1: Validar deploy completo de frontend e API
- Verificar se `/admin/matches` e `/admin/tools` funcionam apos deploy (os 404 observados
  podem ter sido queda temporaria da API — ambas as paginas existem no codigo fonte)
- Se persistir, investigar: build de producao pode estar excluindo paginas por erro de import
- Validar que endpoints de API respondem: `/v1/similarity/search`, `/v1/matches/{id}`,
  `/v1/ingestion/summary`, `/v1/similarity/health`
- **Entregavel:** Todas as paginas do sidebar funcional em producao
- **Validacao:** Acessar cada link do sidebar e confirmar que nenhum retorna 404

#### T1.2: Corrigir bug de normalizacao de alias
- Investigar por que "Tenda" normaliza como "enda"
- Provavel: logica de normalizacao esta removendo primeira letra ou aplicando stemming incorreto
- Corrigir logica em `sync_monitoring_profile.py`
- Re-gerar seeds para marcas afetadas
- Limpar matches espurios (enda.*)
- Tambem corrigir: "comgas.com.br" normalizado como "comgascombr" (inclui TLD na normalizacao)
- **Entregavel:** Aliases normalizados corretamente para todas as marcas
- **Validacao:** Alias "Tenda" → "tenda", "comgas.com.br" → "comgas"

#### T1.3: Executar primeiro scan completo para marcas criticas
- Com T1.0 feito, trigger scan para Itau, Caixa, Claro (marcas de alto risco)
- Pode ser via API `POST /v1/brands/{id}/scan` ou aguardar cron diario
- Documentar resultado: quantos matches, distribuicao de buckets, qualidade do top 10
- **Entregavel:** Pelo menos 3 marcas com matches reais em producao
- **Validacao:** Top 10 dos matches faz sentido para cada marca

#### T1.4: Validar pipeline completo ponta-a-ponta
- Cadastrar marca → Gerar seeds → Trigger scan → Ver matches → Ver enriquecimento → Tomar acao
- Documentar cada passo com evidencia (screenshot, API response)
- **Entregavel:** Documento de validacao E2E com evidencias
- **Validacao:** Fluxo funciona sem 404s, erros opacos ou dados vazios

#### T1.5: Consolidar perfis de marca duplicados
- Remover perfis duplicados: comgas (sem .com.br), gsuplementos (sem .com.br), listenx (sem .com.br)
- Ou merge: migrar seeds/matches do perfil sem dominio para o perfil com dominio oficial
- Garantir que perfis restantes tenham official_domains configurados (Tenda tambem)
- **Entregavel:** 1 perfil limpo por marca, todos com official_domains
- **Validacao:** GET /v1/brands nao mostra perfis duplicados

---

### TIER 2 — Qualidade do Core (Diferenca entre "funciona" e "confiavel")
> Prioridade: ALTA | Prazo sugerido: 2-4 sprints

#### T2.1: Hardening do agendamento automatico de scans
- O scheduler ja esta implementado (`similarity_worker.py` com cron `0 9 * * *`)
- O que precisa ser feito: monitorar execucao, tratar falhas, adicionar alertas
- Implementar health check do worker (heartbeat, metricas de scans completados)
- Adicionar log estruturado de inicio/fim/erros por marca e TLD
- Definir alerta quando scan nao completa em janela esperada
- **Justificativa North Star:** Pilar 7 — "monitoramento continuo confiavel"
- **Complexidade:** Baixa-Media (worker ja existe, precisa observabilidade)

#### T2.2: Enriquecer auto-enrichment com DNS + SSL + Screenshot
- Adicionar dns_lookup ao pipeline de auto-enrich (barato, alto valor)
- Adicionar ssl_check (revela certificados suspeitos, datas, emissores)
- Adicionar screenshot (evidencia visual critica para triagem rapida)
- Aumentar budget de 8 para 12-15 por scan (com base na reducao de custo por tool)
- **Justificativa North Star:** Pilar 4 — "DNS, WHOIS, SSL, headers, screenshot coerentes"
- **Complexidade:** Media (ferramentas ja existem, precisa integrar no pipeline)

#### T2.3: Implementar taxonomia de disposicao do North Star
- Mapear attention_bucket para a taxonomia 10/10:
  - `official` — dominio oficial da marca (excluido pre-scan)
  - `self_owned_related` — detectado como self-owned via WHOIS/redirect
  - `third_party_legitimate` — registro antigo, provavel uso legitimo
  - `defensive_gap` — exact-match nao registrado em TLD estrategico
  - `live_but_unknown` — ativo mas sem sinais claros
  - `likely_phishing` — credential form + recente + impersonation
  - `mail_spoofing_risk` — SPF/DKIM/DMARC falhos + sem web surface
  - `inconclusive` — enriquecimento falhou ou incompleto
- **Justificativa North Star:** Secao 8 — "Taxonomia ideal de saida"
- **Complexidade:** Media (logica de mapeamento + UI)

#### T2.4: Melhorar explicabilidade dos matches
- Substituir `recommended_action` generico por texto contextual baseado em sinais
- Adicionar "por que este dominio foi priorizado" com linguagem humana
- Exemplos:
  - "Registrado ha 5 dias em TLD estrategico, com formulario de login imitando sua marca"
  - "Exact-match em .com nao registrado pela sua organizacao — gap defensivo"
  - "Typo classico com servidor de email ativo mas sem website — risco de spoofing"
- **Justificativa North Star:** Pilar 6 — "o analista entende por que um dominio foi priorizado"
- **Complexidade:** Media (template engine baseado em sinais)

#### T2.5: Cobertura .br obrigatoria no onboarding
- Ao cadastrar marca brasileira, incluir automaticamente .com.br, .net.br, .org.br no tld_scope
- Sugerir .gov.br para marcas governamentais
- Validar que dados CZDS existem para os TLDs incluidos
- Mostrar aviso se TLD declarado nao tem cobertura de ingestao
- **Justificativa North Star:** Principio 5.5 — "Cobertura brasileira nao e opcional"
- **Complexidade:** Baixa

---

### TIER 3 — Inteligencia e Feedback (Diferenca entre "confiavel" e "aprende")
> Prioridade: MEDIA | Prazo sugerido: 3-6 sprints

#### T3.1: Feedback loop do analista
- Quando analista marca match como `dismissed` ou `confirmed_threat`, registrar decisao
- Usar decisoes para:
  - Ajustar thresholds de noise_mode por marca
  - Identificar padroes de falso positivo recorrentes
  - Treinar heuristica de prioridade (mais dados = melhor ranking)
- Criar metricas: taxa de dismissal, taxa de confirmacao, tempo de triagem
- **Justificativa North Star:** Pilar 7 — "metrica e revisao humana retroalimentam o ranking"
- **Complexidade:** Alta

#### T3.2: Deteccao honesta de estados inconclusivos
- Nunca marcar como `safe` um dominio que e apenas `unreachable`, `challenge`, `error` ou `unknown`
- Criar estados explicitos:
  - `unreachable` — nao respondeu HTTP (timeout, DNS fail)
  - `challenge` — WAF/CAPTCHA bloqueou analise
  - `error` — ferramenta falhou (WHOIS timeout, SSL handshake fail)
  - `unknown` — sem dados suficientes para classificar
- Mostrar esses estados na UI com icones e explicacao
- **Justificativa North Star:** Principio 5.6 — "Todo estado inconclusivo deve ser honesto"
- **Complexidade:** Media

#### T3.3: Deteccao de risco mail-only
- Dominio sem website ativo mas com MX records configurados = risco de spoofing
- Combinar com analise de SPF/DKIM/DMARC para classificar risco
- Criar categoria `mail_spoofing_risk` na taxonomia
- Priorizar quando email security check mostra vulnerabilidade
- **Justificativa North Star:** Pilar 4 — "mail-only risk e visivel"
- **Complexidade:** Media (dados ja disponiveis, precisa de logica de correlacao)

#### T3.4: Melhorar deteccao de self-owned
- Alem de WHOIS registrant matching e redirect chains:
  - Comparar nameservers com os da marca oficial
  - Verificar se IP pertence ao mesmo ASN
  - Verificar se certificado SSL e emitido para a mesma organizacao
  - Verificar se Google Analytics / tag manager IDs coincidem
- **Justificativa North Star:** Pilar 3 — "self-owned related e rebaixado automaticamente"
- **Complexidade:** Alta

#### T3.5: Clone detection no pipeline
- Integrar `website_clone` tool no auto-enrichment para matches high/critical
- Comparar conteudo visual/textual com site oficial
- Classificar como `likely_phishing` se clone score > threshold
- **Justificativa North Star:** Pilar 4 — "clone detection lida com WAF e TLS"
- **Complexidade:** Alta (ferramenta existe mas precisa de robustez)

---

### TIER 4 — Escala e Polimento (Diferenca entre "aprende" e "10/10")
> Prioridade: BAIXA | Prazo sugerido: 6+ sprints

#### T4.1: Dashboard de metricas operacionais
- Graficos de: matches por dia, scans executados, tempo de triagem, taxa de dismissal
- Health check visual de cada fonte de ingestao
- Alerta quando scan nao roda ha mais de X horas
- **Complexidade:** Media

#### T4.2: Notificacoes automaticas
- Alertar por email quando match `immediate_attention` e detectado
- Digest diario/semanal de novos matches por marca
- Integracao com Slack/webhook para times
- **Complexidade:** Media

#### T4.3: Historico e trends
- Timeline de matches por marca (novos vs resolvidos)
- Comparacao temporal de superficie de ataque
- Alerta de pico de atividade
- **Complexidade:** Alta

#### T4.4: Onboarding guiado
- Wizard de cadastro de marca com validacao em tempo real
- Sugestao automatica de aliases, keywords, TLD scope
- Preview de scan antes de executar (mostrar variantes encontradas)
- **Complexidade:** Alta

#### T4.5: API publica para clientes
- Endpoint REST documentado para consulta de matches
- Webhook para notificacao em tempo real
- Rate limiting e autenticacao por API key
- **Complexidade:** Alta

---

## 5. Scorecard Atual vs Meta 10/10

| Dimensao | Codigo | Producao | Meta 10/10 | Gap principal |
|----------|--------|----------|------------|---------------|
| Cobertura | 7/10 | 5/10 | 10/10 | TLDs .br nem sempre incluidos, cobertura nao validada |
| Latencia | 7/10 | 2/10 | 10/10 | Codigo pronto mas worker nao deployado em producao |
| Precisao | 8/10 | 5/10 | 10/10 | Algoritmo bom, mas bug de normalizacao e dados sujos |
| Qualidade de contexto | 6/10 | 3/10 | 10/10 | Auto-enrich limitado (sem DNS, SSL, screenshot) |
| Acionabilidade | 7/10 | 2/10 | 10/10 | Frontend existe mas possivelmente nao deployado |
| Operabilidade E2E | 6/10 | **1/10** | 10/10 | **Worker ausente do stack.yml = pipeline morto** |

**Nota geral estimada:**
- **Codigo/arquitetura: 6.8/10** — bem estruturado, com algoritmos solidos
- **Producao efetiva: 3.0/10** — pipeline nao funciona ponta-a-ponta

**Diagnostico:** O gap principal NAO e de engenharia de algoritmos. O codigo esta
muito mais avancado do que o que esta operacional. A causa raiz e de **DevOps/deploy**:
o similarity_worker precisa estar no stack.yml para o produto funcionar.

Analogia: o motor esta montado e calibrado, mas nao foi instalado no carro.

---

## 6. Recomendacao de Sequenciamento

```
Semana 1 (URGENTE): TIER 1a — Desbloquear producao
  ├── T1.0: ★ Adicionar similarity_worker ao stack.yml (CAUSA RAIZ)
  ├── T1.1: Validar frontend (matches + tools pages)
  └── T1.2: Fix normalizacao de alias + cleanup perfis duplicados (T1.5)

Semana 2: TIER 1b — Validacao
  ├── T1.3: Executar scans para Itau, Caixa, Claro
  ├── T1.4: Validacao E2E documentada
  └── T2.5: Cobertura .br no onboarding (baixa complexidade, alto valor)

Semana 3-4: TIER 2a (Quick Wins de Qualidade)
  ├── T2.1: Hardening do scheduler (observabilidade + alertas)
  └── T2.3: Taxonomia de disposicao do North Star

Semana 5-8: TIER 2b (Core Experience)
  ├── T2.2: DNS + SSL + Screenshot no auto-enrich
  └── T2.4: Explicabilidade contextual

Semana 9-14: TIER 3 (Inteligencia)
  ├── T3.1: Feedback loop
  ├── T3.2: Estados inconclusivos honestos
  ├── T3.3: Mail-only risk detection
  └── T3.4: Self-owned detection melhorado

Semana 15+: TIER 4 (Escala)
  └── Conforme prioridade do produto
```

**Nota sobre velocidade de impacto:** T1.0 pode ser feito em 30 minutos e desbloqueia
todo o monitoramento. E de longe a acao com maior ratio valor/esforco neste plano.

---

## 7. Criterios de Validacao por Tier

### Validacao TIER 1 (Fundacao)
- [ ] Todas as paginas do sidebar abrem sem 404
- [ ] API de similarity search responde com dados
- [ ] Pelo menos 3 marcas tem matches em producao
- [ ] Top 10 de cada marca nao contem dominio oficial da propria marca
- [ ] Nenhum alias normalizado de forma incorreta

### Validacao TIER 2 (Qualidade)
- [ ] Scans rodam automaticamente sem intervencao manual
- [ ] Cada match mostra DNS + WHOIS + HTTP + screenshot
- [ ] Disposicoes seguem taxonomia do North Star
- [ ] Explicacao em linguagem humana para cada match prioritario
- [ ] Marcas brasileiras incluem .com.br, .net.br, .org.br por padrao

### Validacao TIER 3 (Inteligencia)
- [ ] Decisoes do analista influenciam ranking futuro
- [ ] Estados inconclusivos explicitamente rotulados na UI
- [ ] Mail-only risk aparece como categoria distinta
- [ ] Self-owned detectado por 3+ sinais (WHOIS, NS, redirect, ASN)

### Validacao TIER 4 (Escala)
- [ ] Dashboard mostra saude operacional do sistema
- [ ] Alertas automaticos para ameacas imediatas
- [ ] Historico temporal de ameacas por marca

---

## 8. Riscos e Dependencias

| Risco | Mitigacao |
|-------|----------|
| Deploy de producao pode ter problemas de infraestrutura alem de routing | Validar stack Traefik + Docker Swarm config |
| Bug de normalizacao pode afetar mais marcas que apenas Tenda | Auditar todos os aliases normalizados no banco |
| Aumento de budget de auto-enrich pode impactar performance | Implementar com rate limiting e circuit breaker |
| Agendamento automatico pode sobrecarregar banco | Delta scanning ja implementado; controlar concorrencia |
| Feedback loop precisa de volume de decisoes para ser util | Comecar coletando dados antes de usar para ajustar |

---

## 9. Arquivos-Chave para Implementacao

| Componente | Arquivo | Responsabilidade |
|-----------|---------|-----------------|
| Scoring | `backend/app/services/use_cases/compute_similarity.py` | Calculo dos 5 sub-scores |
| Triage | `backend/app/services/use_cases/compute_actionability.py` | Bucketing e ajustes |
| Enrichment | `backend/app/services/use_cases/enrich_similarity_match.py` | Auto-enrich pipeline |
| Scan | `backend/app/services/use_cases/run_similarity_scan.py` | Orquestracao completa |
| Seeds | `backend/app/services/monitoring_profile.py` | Geracao de seeds |
| Normalizacao | `backend/app/services/sync_monitoring_profile.py` | Sync de aliases/seeds |
| Repository | `backend/app/repositories/similarity_repository.py` | SQL de busca |
| API Matches | `backend/app/api/v1/routers/monitored_brands.py` | Endpoints de matches |
| API Similarity | `backend/app/api/v1/routers/similarity.py` | Endpoint de busca |
| Frontend Matches | `frontend/app/admin/matches/page.tsx` | UI de resultados |
| Frontend Brands | `frontend/app/admin/brands/page.tsx` | UI de gestao |
| Deploy | `infra/stack.yml` | Config de producao |
| Traefik | `infra/stack.yml` (labels) | Roteamento HTTP |

---

## 10. Log de Progresso de Implementacao

> Atualizado em: 2026-03-25

### Implementado nesta sessao (commits em main)

| Task | Commit | Descricao |
|------|--------|-----------|
| T1.0 ✅ | `394c65c` | similarity_worker adicionado ao infra/stack.yml e config.py |
| T1.2 ✅ | auto | Normalizacao de alias auto-reparada via ensure_monitoring_profile_integrity |
| T2.5 ✅ | `fbc37ae` | enrich_tld_scope_for_brazil — TLDs .com.br, .net.br, .org.br automaticos |
| T2.1 ✅ | `3555799` | HEARTBEAT + CYCLE_SUMMARY logs no similarity_worker |
| T2.3 ✅ | `28f5289` | Taxonomia North Star alinhada: third_party_legitimate, mail_spoofing_risk, inconclusive |
| T2.4 ✅ | `e4a0bb8` | recommended_action contextual com nome do dominio e da marca |
| T3.2 ✅ | `2e2f26b` | Estados inconclusivos honestos: unreachable/all-tools-failed → "inconclusive" |
| T3.4 ✅ | `2e2f26b` | Self-owned detection via nameserver overlap (WHOIS name_servers) |

### Pendente (proximas sessoes)

| Task | Prioridade | Bloqueador |
|------|-----------|------------|
| Todo 004 | P0 | Agente do docker-stack-infra (.specs/todos/004/plan.md) |
| T1.4 | P0 | Depende de Todo 004 (worker em producao) |
| T1.5 | P1 | Limpeza manual de perfis duplicados |
| T2.2 | P2 | DNS + SSL + Screenshot no auto-enrich |
| T3.1 | P2 | Feedback loop do analista |
| T3.3 | P3 | Mail-only risk detection (logica ja parcialmente pronta) |

---

## 11. Como Usar Este Documento

### Para quem vai implementar
1. Leia o TIER 1 inteiro antes de comecar
2. Cada item do TIER 1 e independente — pode ser paralelizado
3. Valide cada item contra os criterios antes de seguir
4. Documente evidencias (screenshots, API responses) no PR

### Para quem vai revisar
1. Confira se o PR reduz algum gap listado aqui
2. Confira se o top 10 de matches faz sentido apos a mudanca
3. Use o scorecard (secao 5) como referencia

### Para product owner
1. Use os TIERs como guia de priorizacao
2. O TIER 1 e pre-requisito para qualquer demonstracao do produto
3. O TIER 2 e o que transforma o produto em algo confiavel
4. Revise o scorecard mensalmente

---

## Apendice A: Arquitetura de Scoring Atual (Referencia Tecnica)

### Nivel 1: Score de Similaridade Lexical
| Metrica | Peso | Deteccao |
|---------|------|----------|
| Trigram (pg_trgm) | 30% | Fuzzy string similarity |
| Levenshtein | 25% | Edit distance normalizado |
| Brand Hit | 20% | Brand no label com boundary-aware |
| Keyword Risk | 15% | Palavras de risco (login, secure, verify, bank) |
| Homograph | 10% | Unicode confusables (Cyrillic а→a, leet 0→o) |

Threshold dinamico: 0.5 para brands ≤5 chars, 0.3 para maiores.
Noise modes: conservative (0.60), standard (0.50), broad (0.42).

### Nivel 2: Score de Actionability
Base = score_final × 0.35, depois ajustes:
- newly_observed (≤30 dias): +0.18
- exact_match_on_official_label: +0.32
- typosquatting_pattern: +0.38
- homograph_pattern: +0.42
- brand_plus_risky_keyword: +0.34
- strategic_tld: +0.05

Buckets: immediate_attention | defensive_gap | watchlist

### Auto-Enrichment (budget: 8 matches/scan)
Ferramentas: WHOIS, HTTP headers, suspicious page, email security, IP geolocation.
Ajustes pos-enrichment: credential form (+0.26), recent registration (+0.18),
parked page (-0.22), high spoofing risk (+0.16), unusual hosting (+0.12).

### Decisao: sem pgvector
Justificativa: 33GB storage para 200M rows + custo de GPU para inference.
pg_trgm cobre 90%+ do sinal necessario com custo operacional minimo.

---

## Apendice B: Dados Coletados em Producao (2026-03-25)

> **Nota:** Durante os testes, a API de producao ficou temporariamente indisponivel
> (todos os endpoints passaram a retornar 404 simultaneamente). Os dados abaixo foram
> coletados ANTES da queda. Os 404 nas paginas de Matches e Tools podem ter sido
> consequencia dessa queda temporaria, NAO necessariamente um problema de deploy.
> Requer validacao quando a API estiver estavel.

### Dashboard
- 12 marcas ativas monitoradas
- 314.360.062 dominios ingeridos (4 fontes)
- CZDS: 312.629.372 dominios (running, 43m ago)
- CertStream: 1.715.184 dominios (running, 46m ago)
- crt.sh: 15.506 dominios (success, 11h ago)
- crt.sh Bulk: nunca executado

### Marcas cadastradas
| Marca | Label | Official Domains | Aliases | Seeds | TLD Scope |
|-------|-------|-----------------|---------|-------|-----------|
| Tenda | tenda | (nenhum) | Tenda→enda(!), supermercado | 2 total, 1 scan | 93 TLDs (sem .br) |
| Tenda atacado | tendaatacado | tendaatacado.com.br | tendaatacado, Tenda atacado, Tenda | 6 total, 2 scan | 93 TLDs (sem .br) |
| caixa | caixa | caixa.gov.br | Caixa, Caixa Economica | 5 total, 2 scan | 14 TLDs (com .br) |
| claro | claro | claro.com.br, claro.com | Claro, minhaclaro | 8 total, 2 scan | 17 TLDs (com .br) |
| comgas | comgas | (nenhum) | comgas | 1 total, 1 scan | 93 TLDs (sem .br) |
| comgas.com.br | comgas.com.br | comgas.com.br | comgas.com.br(!) | 4 total, 2 scan | 93 TLDs (sem .br) |
| gsuplementos | gsuplementos | (nenhum) | gsuplementos | 1 total, 1 scan | 93 TLDs (sem .br) |
| gsuplementos.com.br | gsuplementos.com.br | gsuplementos.com.br | gsuplementos.com.br(!), suplementos, whey | 6 total, 2 scan | 93 TLDs (sem .br) |
| itau | itau | itau.com.br, itau.com | Itau | 6 total, 2 scan | 17 TLDs (com .br) |
| listenx | listenx | (nenhum) | listenx, radiocadademia | 2 total, 1 scan | 93 TLDs (sem .br) |
| listenx.com.br | listenx.com.br | listenx.com.br | listenx.com.br(!) | 4 total, 2 scan | 93 TLDs (sem .br) |
| sabesp | sabesp | sabesp.com.br | Sabesp | 5 total, 2 scan | 17 TLDs (com .br) |

### Matches em producao
- Tenda: 2.629 matches (unica marca com resultados)
- Todas as outras marcas: 0 matches (nenhum scan executado)

### Problemas de dados observados
- "Tenda" normaliza como "enda" — gera matches com enda.studio, enda.chat, enda.pro
- comgas.com.br tem alias normalizado como "comgascombr" (incluiu TLD na normalizacao)
- gsuplementos.com.br tem alias normalizado como "gsuplementoscombr" (mesmo problema)
- listenx.com.br tem alias normalizado como "listenxcombr" (mesmo problema)
- Perfis duplicados para comgas, gsuplementos, listenx (com e sem .com.br)

### Endpoints testados
| Endpoint | Status | Nota |
|----------|--------|------|
| POST /v1/auth/login | 200 OK | Funcional |
| GET /v1/brands | 200 OK | Funcional (retorna 12 brands) |
| GET /v1/brands/{id}/matches | 200 OK | Funcional (retorna matches) |
| POST /v1/tools/domain-similarity | 200 OK | Funcional (gera variantes) |
| POST /v1/similarity/search | 404 | Nao funcional |
| GET /v1/similarity/health | 404 | Nao funcional |
| GET /v1/matches/{id} | 404 | Nao funcional |
| GET /v1/ingestion/summary | 404 | Nao funcional |
| Frontend /admin | 200 OK | Dashboard funcional |
| Frontend /admin/ingestion | 200 OK | Funcional |
| Frontend /admin/brands | 200 OK | Funcional |
| Frontend /admin/matches | 404 | Nao funcional |
| Frontend /admin/tools | 404 | Nao funcional |
