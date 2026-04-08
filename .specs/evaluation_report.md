# Avaliacao — Observador de Dominios

**Data:** 2026-03-27
**Avaliador:** Profissional de Threat Intelligence (simulacao)
**Metodo:** Testes via API de producao (api.observadordedominios.com.br)
**Empresas avaliadas:** 10 grandes marcas brasileiras

---

## Empresa 1: Nubank

### Contexto
- Marca: nubank
- Expectativa: Detectar typosquatting classico (nuibank, nu-bank, nuhbank), dominios de phishing com prefixos (login-nubank, app-nubank), e clones em TLDs alternativos (.xyz, .online, .site)
- Nubank e um dos maiores alvos de phishing do Brasil

### Resultados analisados
- **Total de matches encontrados: 0**
- Scan disparado mas permaneceu no status `queued` indefinidamente
- Ferramenta de similaridade gerou 173 variantes (substitution, duplication, prefix, suffix, tld_variation)
- Nenhuma dessas variantes foi cruzada contra dominios registrados

### Pensamento do avaliador
- "Zero resultados para Nubank? Isso e impossivel. Eu pessoalmente ja vi dezenas de dominios de phishing como nubank-app.com, nubankk.com, nubankseguranca.com.br"
- "O gerador de variantes funciona, mas se o scan nao processa, nao adianta nada"
- "Estou preocupado — se um cliente real cadastrasse Nubank e visse zero matches, cancelaria no primeiro dia"

### Questionamentos
- Por que o scan ficou preso em `queued`? O worker nao esta processando
- A tabela `similarity_scan_job` nao existe no banco de producao — isso e um bug critico
- Mesmo com CertStream ativo (ultimo sucesso 22:56 UTC), nenhum match foi gerado

### Avaliacao

**Pontos positivos:**
- Gerador de variantes e sofisticado (173 variantes com 9 categorias)
- TLD scope e abrangente (21 TLDs configurados)

**Pontos de atencao:**
- Nenhum resultado util para a maior fintech do Brasil

**Problemas criticos:**
- Scan completamente inoperante — tabela `similarity_scan_job` ausente no banco de producao
- Sistema aceita o scan (retorna job_id) mas nunca o processa — falha silenciosa

### Veredito da empresa
- Isso ajuda a detectar ameacas reais? **NAO** — zero deteccao
- Isso geraria acao? **NAO** — nao ha o que agir

---

## Empresa 2: Itau

### Contexto
- Marca: itau
- Expectativa: Marca curta (4 letras) deveria gerar muitas colisoes. Phishing historico massivo — itau-seguranca, itaucard-login, etc.

### Resultados analisados
- **Total de matches encontrados: 0**
- Marca ja existia no sistema (pre-cadastrada)
- 204 variantes geradas pelo gerador de similaridade
- Scan disparado, ficou `queued`

### Pensamento do avaliador
- "Itau tem 4 letras — deveria haver centenas de matches por colisao lexica sozinha"
- "Marcas curtas sao notoriamente dificeis de monitorar. Se o sistema nao encontra nada para 'itau', algo esta fundamentalmente quebrado"
- "Marca ja existia no sistema e MESMO ASSIM tem zero matches — o scan nunca rodou com sucesso?"

### Questionamentos
- A marca foi cadastrada mas nunca escaneada com sucesso?
- O scan anterior tambem falhou por causa do bug da tabela?
- Como o Claro (cadastrado na mesma epoca) tem 1 match e Itau tem 0?

### Avaliacao

**Pontos positivos:**
- 204 variantes geradas (bom coverage de substituicao e duplicacao)
- 17 TLDs no escopo

**Problemas criticos:**
- Zero matches para um dos maiores alvos de phishing bancario do Brasil
- Se o scan nunca rodou, o produto nunca entregou valor para esta marca

### Veredito da empresa
- Isso ajuda a detectar ameacas reais? **NAO**
- Isso geraria acao? **NAO**

---

## Empresa 3: Banco Inter

### Contexto
- Marca: bancointer
- Expectativa: "inter" e uma palavra comum (collisoes esperadas). "bancointer" deveria ter matches de typosquatting e brand_containment

### Resultados analisados
- **Total de matches encontrados: 0**
- Marca recem-cadastrada, scan ficou `queued`

### Pensamento do avaliador
- "Banco Inter e um banco 100% digital — alvo primario de phishing"
- "'inter' e tao generico que qualquer coisa com 'inter' poderia ser match — interbank, interbanco, etc. Mas o sistema monitorou 'bancointer', nao 'inter'"
- "Sem scan, sem resultados. O padrao se repete"

### Questionamentos
- A keyword "inter" deveria expandir o escopo de busca?
- Dominios como "bancointer-app.com" ou "interdigital.com.br" deveriam aparecer?

### Avaliacao

**Problemas criticos:**
- Mesmo padrao: scan enfileirado, nunca processado
- Sem resultados para avaliar qualidade do algoritmo

### Veredito da empresa
- Isso ajuda a detectar ameacas reais? **NAO**
- Isso geraria acao? **NAO**

---

## Empresa 4: Mercado Livre

### Contexto
- Marca: mercadolivre
- Expectativa: Nome composto longo (12 chars), alvo massivo de phishing. Variantes como mercadolivr3, mercad0livre, mercadolivre-entrega

### Resultados analisados
- **Total de matches encontrados: 0**
- 286 variantes geradas (maior numero entre todas as marcas testadas)
- Scan `queued`

### Pensamento do avaliador
- "Mercado Livre e o maior e-commerce da America Latina. O volume de phishing e absurdo"
- "286 variantes geradas mas nenhuma cruzada — e como ter um radar desligado"
- "O que me preocupa: se um dominio mercadolivre-entrega.com for registrado agora, quanto tempo leva para o sistema detectar?"

### Avaliacao

**Problemas criticos:**
- Zero visibilidade para o maior e-commerce latam
- 286 variantes geradas mas nenhuma verificada contra a base de dominios

### Veredito da empresa
- Isso ajuda a detectar ameacas reais? **NAO**
- Isso geraria acao? **NAO**

---

## Empresa 5: Magazine Luiza (Magalu)

### Contexto
- Marca: magalu
- Expectativa: "magalu" e uma marca de 6 letras com alta penetracao. Phishing via WhatsApp com links tipo "magalu-promo.com" e comum

### Resultados analisados
- **Total de matches encontrados: 0**
- Scan `queued`

### Pensamento do avaliador
- "Magalu e constante alvo de golpes no WhatsApp — 'magalu-blackfriday', 'magalu-promocao'"
- "Mesmo problema de todos"

### Veredito da empresa
- Isso ajuda a detectar ameacas reais? **NAO**
- Isso geraria acao? **NAO**

---

## Empresa 6: Claro

### Contexto
- Marca: claro (ja pre-cadastrada com keywords: minhaclaro, claro)
- Expectativa: Telecom gigante, alvo de phishing para roubo de dados de conta/recarga

### Resultados analisados
- **Total de matches: 1**
  - `clro.link` — TLD=.link, score=0.575, risk=medium, bucket=watchlist, reason=lexical_similarity

- **Enriquecimento do match (clro.link):**
  - DNS: nenhum A record, nenhum MX
  - WHOIS: Amazon Registrar, criado 2023-04-20
  - SSL: invalido
  - Dominio inativo, provavelmente parked

### Pensamento do avaliador
- "Um unico match para a Claro? E esse match e um dominio inativo em .link sem infraestrutura nenhuma"
- "'clro.link' e uma variante por omissao (removeu o 'a'). Score 0.575 e justo"
- "Mas cade os dominios tipo minha-claro.com, claro-fatura.com.br, claro2via.com? Esses sao os que aparecem em campanhas reais"
- "O enrichment mostra que o dominio esta morto — nao e uma ameaca. Mas o sistema o classificou como watchlist, nao descartou. Correto"

### Questionamentos
- Por que apenas 1 match? O scan do .com.br falhou (status=failed no last_scan)
- A keyword "minhaclaro" nao gerou nenhum match — o escopo e restrito demais?

### Avaliacao

**Pontos positivos:**
- O unico match encontrado e razoavel — variante por omissao detectada
- Classificacao como watchlist e correta para dominio inativo
- Enrichment funcional (DNS, WHOIS, SSL retornaram dados)

**Pontos de atencao:**
- Apenas 1 match para uma telecom gigante
- Scan anterior falhou e novo ficou queued

**Problemas criticos:**
- Cobertura absurdamente insuficiente

### Veredito da empresa
- Isso ajuda a detectar ameacas reais? **PARCIALMENTE** — o unico match era inativo
- Isso geraria acao? **NAO** — dominio morto, nada a fazer

---

## Empresa 7: Vivo

### Contexto
- Marca: vivo (4 letras)
- Expectativa: Similar ao Itau — marca curta com muitas colisoes possiveis

### Resultados analisados
- **Total de matches: 0**
- Scan `queued`

### Pensamento do avaliador
- "'vivo' tem 4 letras. Deve haver centenas de dominios com 'vivo' no nome — vivoshop, vivo-recarga, meuvivo"
- "Sem scan, sem resultados"

### Veredito da empresa
- Isso ajuda a detectar ameacas reais? **NAO**
- Isso geraria acao? **NAO**

---

## Empresa 8: iFood

### Contexto
- Marca: ifood
- Expectativa: App de delivery #1 do Brasil. Phishing via "ifood-parceiro", "ifood-promo"

### Resultados analisados
- **Total de matches: 0**
- 167 variantes geradas
- Scan `queued`

### Pensamento do avaliador
- "iFood e alvo constante de golpes. 'ifood-parceiro' e 'cadastro-ifood' sao padroes conhecidos"
- "167 variantes nao verificadas = zero valor"

### Veredito da empresa
- Isso ajuda a detectar ameacas reais? **NAO**
- Isso geraria acao? **NAO**

---

## Empresa 9: LATAM Airlines

### Contexto
- Marca: latam
- Expectativa: "latam" e usado como prefixo de muitas empresas (latam, latamex, latamlog). Phishing via "latam-milhas", "latam-passagens"

### Resultados analisados
- **Total de matches: 0**
- Scan `queued`

### Pensamento do avaliador
- "'latam' vai gerar muito ruido (latam e uma abreviacao comum para 'Latin America'). Sera que o sistema filtra isso?"
- "Sem scan, impossivel avaliar"

### Veredito da empresa
- Isso ajuda a detectar ameacas reais? **NAO**
- Isso geraria acao? **NAO**

---

## Empresa 10: Hapvida

### Contexto
- Marca: hapvida
- Expectativa: Marca unica (7 letras, nao e uma palavra real). Colisoes devem ser minimas e altamente relevantes

### Resultados analisados
- **Total de matches: 0**
- Scan `queued`

### Pensamento do avaliador
- "'hapvida' e um nome inventado — qualquer match deveria ser MUITO suspeito"
- "E o tipo ideal de marca para monitorar: pouca ambiguidade, alto sinal"
- "Mas sem scan, zero resultados"

### Veredito da empresa
- Isso ajuda a detectar ameacas reais? **NAO**
- Isso geraria acao? **NAO**

---

# Analise Complementar: Marcas Pre-existentes

Para avaliar a qualidade do algoritmo quando FUNCIONA, analisei marcas ja escaneadas:

## Caixa (101 matches)

### Amostra analisada com enriquecimento profundo:

**1. caixagov.com.br — AMEACA REAL**
- Criado: 2026-03-20 (6 dias atras!)
- A record: 108.179.253.53 (HostGator)
- MX: titan.email (servico de email ativo!)
- SSL: Let's Encrypt, SAN compartilhado com dominios suspeitos (andarquinto.com.br, xn--centrodistribuioextrema-l7b3h.com.br)
- Screenshot: "403 - Acesso negado" (site bloqueado mas no ar)
- Suspicious Page: risk_score=0.45 (medium) — sinais de credential harvesting e social engineering
- Email: SPF configurado (titan.email), SEM DMARC — pode enviar emails falsificados
- Registrante: Pessoa fisica com email Hotmail
- **VEREDITO: Phishing preparatorio. Dominio recem-registrado com infraestrutura de email pronta para campanha**

**2. mycaixa.com.br — FALSO POSITIVO**
- Fintech para PMEs ("mycaixa - Controle Financeiro para PMEs")
- Registrado em 2025-11-21
- SSL valido, DMARC configurado (quarantine)
- Suspicious Page: risk=safe
- **VEREDITO: Negocio legitimo. Falso positivo**

**3. meucaixa.com.br — FALSO POSITIVO**
- App financeiro (Firebase, Vercel)
- Registrado em 2019
- Suspicious page: low risk (login existente mas legitimo)
- **VEREDITO: App legitimo. Falso positivo**

**4. sbcaixa.com.br — FALSO POSITIVO**
- Softbel Informatica Ltda (CNPJ real)
- Registrado em 2023
- Cloudflare, site corporativo
- **VEREDITO: Empresa real. Falso positivo**

**5. comgasnatural.site — DOMINIO SUSPEITO**
- Hostinger, DNS parking
- SSL invalido
- Registrado 2025-05-06
- **VEREDITO: Domain squatting, potencial phishing futuro**

### Analise da amostra Caixa:
- 1 ameaca real (caixagov.com.br) em 5 dominios analisados = **20% taxa de sinal**
- 3 falsos positivos (60%) — negocios reais que contem "caixa" no nome
- 1 suspeito (20%) — domain squatting
- O sistema classificou TODOS como "defensive_gap" com risk "medium" — **nao diferenciou a ameaca real dos falsos positivos**
- Nenhum match foi classificado como "immediate_attention"

### Score Analysis:
- caixagov.com.br (phishing real): score=0.698 — MESMO SCORE que caixapop e caixatrio
- mycaixa (falso positivo): score=0.699 — SCORE MAIOR que a ameaca real!

**Conclusao: O score de similaridade lexica nao diferencia ameaca real de negocio legitimo. O enrichment PODERIA corrigir isso, mas nao e acionado automaticamente.**

---

## Tenda (2631 matches)

- Top matches sao todos "exact_label_match" em TLDs alternativos: tenda.xyz, tenda.net, tenda.com
- Scores 0.83-0.87 (high)
- Enrichment: NENHUM (enrichment_status=None para todos)
- Bucket: todos "defensive_gap"

### Pensamento:
- "2631 matches para Tenda? 'tenda' e uma palavra real (tent em ingles). Isso e puro ruido"
- "Sem enrichment, nao da para saber quais desses 2631 sao ameacas e quais sao negocios de camping"
- "Se eu fosse o cliente, gastaria HORAS triando 2631 resultados e a maioria seria irrelevante"

---

# Consolidacao Final

## Padroes Identificados

### Problemas Recorrentes
1. **Scan job nao processa** — A tabela `similarity_scan_job` nao existe no banco de producao. Todas as 10 marcas-alvo ficaram com scan `queued` indefinidamente. Bug critico.
2. **Enrichment automatico nao funciona** — Nenhum dos 8800+ matches tem enrichment ativo. Todos sao "skipped" ou "None". Sem enrichment, o score e puramente lexical.
3. **Nenhum match classificado como "immediate_attention"** — Zero em 8800 matches. O bucket mais urgente esta vazio para TODAS as marcas.
4. **Score nao diferencia ameaca real de falso positivo** — caixagov.com.br (phishing real) tem score MENOR que mycaixa.com.br (app legitimo)
5. **Ruido excessivo para marcas com palavras reais** — Tenda (2631), gsuplementos (763), listenx (688) acumulam milhares de matches sem prioridade
6. **Falha silenciosa** — O sistema aceita scans, retorna job_id, mas nunca processa. O cliente acha que esta monitorado quando nao esta.

### Pontos Fortes Recorrentes
1. **Gerador de variantes e robusto** — 155-286 variantes por marca com 9 categorias (substitution, duplication, prefix, suffix, etc.)
2. **Ferramentas individuais funcionam bem** — DNS, WHOIS, SSL, Screenshot, Suspicious Page, Email Security todas retornam dados uteis e rapidos
3. **Cobertura de TLDs e ampla** — 107 TLDs, 3 fontes de ingestao (CZDS, CertStream, crt.sh)
4. **Ingestao esta ativa** — CertStream com ultimo sucesso ha poucas horas, CZDS diario
5. **Estrutura de dados e rica** — Matches incluem score_final, attention_bucket, disposition, recommended_action, delivery_risk
6. **Quick Analysis e poderoso** — Combina 6+ ferramentas em uma chamada com resultados completos
7. **caixagov.com.br demonstra potencial real** — Quando os dados estao la, o enrichment CONSEGUE revelar uma ameaca preparatoria

---

## Principais Falhas do Produto

### CRITICO: Worker de Scan Quebrado em Producao
- A tabela `similarity_scan_job` nao existe
- O worker loga o erro continuamente mas nao ha alerta
- Novas marcas NUNCA recebem scan
- Marcas existentes nao recebem re-scans
- **Impacto:** Produto inteiro nao funciona para novos clientes

### CRITICO: Enrichment Automatico Inoperante
- 8800 matches, ZERO enriquecidos automaticamente
- `enrichment_status` = "skipped" ou "None" para todos
- Sem enrichment, o score e puramente lexical e nao diferencia ameacas
- **Impacto:** Cliente precisa clicar em cada dominio manualmente — inviavel com 2631 matches

### ALTO: Zero "Immediate Attention"
- O bucket mais importante (immediate_attention) esta vazio para TODAS as marcas
- Se o produto nunca marca nada como urgente, perde credibilidade
- `caixagov.com.br` (phishing preparatorio) foi classificado como "defensive_gap" em vez de "immediate_attention"
- **Impacto:** O cliente nao sabe no que focar

### ALTO: Falha Silenciosa no Scan
- API aceita POST /brands/{id}/scan e retorna 202 com job_id
- Mas o job nunca e processado
- Nao ha feedback para o usuario de que o scan falhou
- **Impacto:** Falsa sensacao de seguranca

### MEDIO: False Positive Rate Alto
- Para "caixa" (marca com palavra real), 60% dos top matches analisados eram negocios legitimos
- Sem whitelist ou filtro de negocios conhecidos
- **Impacto:** Fadiga de alertas, perda de confianca

### MEDIO: Score Nao Correlaciona com Risco Real
- Score baseado em similaridade lexica, nao em indicadores de ameaca
- mycaixa.com.br (legit, score=0.699) > caixagov.com.br (phishing, score=0.698)
- Enrichment deveria ajustar o score, mas nao esta ativo

---

## Sugestoes

### Urgente (resolver antes de qualquer venda)
1. **Corrigir o bug da tabela `similarity_scan_job`** — Rodar a migracao Alembic em producao
2. **Ativar enrichment automatico** — Pelo menos para matches com score > 0.6
3. **Implementar feedback de scan** — Se o worker nao pode processar, retornar erro na API
4. **Testar o fluxo completo em producao** — Cadastrar marca, scan, matches, enrichment end-to-end

### Importante (resolver para V1)
5. **Recalibrar classification apos enrichment** — Se um dominio tem DNS ativo + MX + SSL recente, subir para immediate_attention
6. **Implementar auto-dismiss** — Dominios com CNPJ no WHOIS ou sites corporativos conhecidos deveriam ser auto-classificados como baixo risco
7. **Reduzir ruido para marcas genericas** — "tenda" com 2631 matches e intratavel. Implementar noise_mode mais agressivo
8. **Dashboard de saude operacional** — O cliente precisa ver se o scan rodou, quando, quantos TLDs cobriu
9. **Adicionar .com.br como TLD critico** — Varios scans nao incluem .com.br que e O TLD mais importante para marcas brasileiras

### Futuro (diferenciacao)
10. **Integrar com listas de phishing conhecidas** (PhishTank, OpenPhish) para enriquecer confidence
11. **Monitoramento de conteudo** — Screenshot + AI para comparar com site original
12. **Alertas por webhook/email quando immediate_attention e detectado**
13. **Timeline de dominio** — Historico de mudancas (DNS, status, conteudo) para mostrar evolucao de ameaca

---

## Veredito Final

| Criterio | Nota | Comentario |
|---|---|---|
| Cobertura de TLDs | 7/10 | 107 TLDs, 3 fontes. Bom, mas .com.br faltou em alguns scans |
| Gerador de variantes | 8/10 | 155-286 variantes com 9 categorias. Robusto |
| Qualidade dos matches | 3/10 | Alto ruido, sem priorizacao por enrichment |
| Enrichment/Ferramentas | 8/10 | Ferramentas individuais excelentes (DNS, WHOIS, SSL, Screenshot, Suspicious Page) |
| Priorizacao/Ranking | 2/10 | Zero immediate_attention, score puramente lexical |
| Acionabilidade | 2/10 | Nao sugere acoes concretas, nao diferencia urgente de ruido |
| Operacao em producao | 1/10 | Worker quebrado, scans nao processam, enrichment inativo |
| Velocidade de deteccao | 4/10 | CertStream ativo (quase real-time), mas scan nao processa |
| Confiabilidade | 1/10 | Falha silenciosa generalizada |
| UX/Feedback | 2/10 | Scan aceito mas nunca processado sem feedback |

**Nota geral: 3.8/10**

**Eu confiaria neste sistema como camada principal do meu processo de protecao de marca?**
**NAO.** O sistema tem uma base tecnica solida (variantes, ferramentas de enrichment, fontes de ingestao) mas esta operacionalmente quebrado em producao. Nenhuma das 10 maiores marcas que testei recebeu um resultado acionavel. O unico resultado util (caixagov.com.br) foi encontrado em uma marca pre-existente e mesmo assim nao foi priorizado corretamente.

**Eu pagaria por este sistema?**
**NAO no estado atual.** O potencial esta la — se o worker funcionasse, o enrichment fosse automatico, e a priorizacao incorporasse indicadores de ameaca (nao so similaridade lexica), este poderia ser um produto valioso. Mas hoje, um cliente pagante estaria pagando por uma falsa sensacao de seguranca.

**Esse sistema realmente detecta ameacas antes que causem dano?**
**NAO no estado atual.** O sistema tem a infraestrutura para detectar (ingestao ativa, gerador de variantes robusto, ferramentas de enrichment excelentes) mas o pipeline esta quebrado. E como ter um sistema de alarme com sensores desligados: o painel existe, os cabos estao la, mas nada dispara.

---

# Questionario de Percepcao de Qualidade

*Respostas baseadas na simulacao completa das 10 empresas*

---

## Bloco 1 — Primeira impressao e onboarding

**1. Quando voce cadastrou sua marca pela primeira vez, o que voce esperava ver acontecer?**
Esperava que o sistema fizesse um scan inicial e mostrasse dominios suspeitos em minutos. Para uma marca como Nubank, esperava ver pelo menos 50-100 matches relevantes incluindo typosquatting classico. O que vi: zero resultados. O scan foi aceito mas nunca processado.

**2. O produto reconheceu corretamente os dominios que voce ja possui? Voce teve que corrigir alguma coisa?**
O cadastro de `official_domains` funcionou, mas nao ha indicacao de que esses dominios sao usados para filtrar matches. Nao vi nenhuma logica de "owned domain" automatica.

**3. Ficou claro quais TLDs e variacoes estavam sendo monitorados? Ou voce ficou na duvida sobre o escopo?**
A API retorna `tlds_effective` no scan, o que e bom. Mas o frontend provavelmente deveria mostrar isso de forma mais clara. Fiquei em duvida se .com.br estava incluido (nao estava para algumas marcas).

---

## Bloco 2 — Cobertura e descoberta

**4. Voce achou algum dominio suspeito que voce ja conhecia antes? O produto o identificou?**
Nao — o produto nao retornou nenhum resultado para 9 das 10 marcas. Para Claro, o unico match (clro.link) era um dominio inativo que eu NAO conhecia. Os dominios de phishing conhecidos (tipo claro-fatura.com) nao apareceram.

**5. Teve algum dominio obvio que voce esperava ver e nao apareceu?**
Sim. Para cada marca, ha dominios de phishing CONHECIDOS que nao apareceram. Exemplos: nubank-app.com, itau-seguranca.com.br, minha-claro.com. O sistema deveria encontrar esses — sao os mais obvios.

**6. Voce acha que a lista esta cobrindo o que realmente importa, ou parece incompleta?**
Completamente incompleta para as 10 marcas testadas. Para Caixa (unica com matches uteis), a cobertura era razoavel mas cheia de falsos positivos.

**7. O produto monitora os TLDs que sao criticos para o seu mercado? (ex: .com.br, .net.br)**
Parcialmente. .com.br esta no escopo mas o scan de .com.br falhou para Claro (status=failed). Para algumas marcas recentes, .com.br estava incluido no tld_scope.

---

## Bloco 3 — Velocidade e deteccao

**8. Quando voce fez a busca inicial, quanto tempo levou para ter resultados? Pareceu rapido ou lento?**
O scan foi aceito instantaneamente (~200ms para retornar o job_id) mas NUNCA produziu resultados. Tempo efetivo: infinito. As ferramentas individuais (DNS, WHOIS, etc.) sao rapidas (1-17 segundos para quick-analysis completa).

**9. Voce usa o monitoramento continuo? Quando aparece um dominio novo, voce sente que e avisado cedo?**
O CertStream esta ativo (ultimo sucesso ha poucas horas) o que sugere monitoramento near-real-time. Mas como o scan nao processa, mesmo que o dominio seja ingerido, ele nao e matchado contra as marcas.

**10. Alguma vez voce soube de um dominio suspeito por outro canal antes do produto te avisar?**
Na simulacao, EU sabia de dominios de phishing comuns para essas marcas e NENHUM apareceu no sistema. Entao sim — eu saberia antes do produto.

---

## Bloco 4 — Contexto e enriquecimento

**11. Para cada dominio suspeito que aparece, voce sente que tem informacao suficiente para decidir o que fazer?**
Quando eu FORCEI o enrichment manualmente (quick-analysis), os dados eram excelentes. O caso caixagov.com.br e exemplo perfeito: DNS, WHOIS, SSL, screenshot, suspicious page e email security — juntos, pintam um quadro claro de phishing preparatorio. Mas o enrichment NAO roda automaticamente, entao o match vem "cru" — so com score lexical.

**12. Voce consegue entender por que aquele dominio foi marcado como suspeito? A explicacao faz sentido?**
Sim — o campo `reasons` (lexical_similarity, brand_containment, typosquatting, exact_label_match) e claro. O `matched_seed_value` e `matched_rule` ajudam a entender o "porque". Ponto positivo.

**13. As informacoes tecnicas (DNS, WHOIS, SSL, screenshot) sao uteis ou voce sente que falta algo?**
Quando disponivel, sao MUITO uteis. O combo DNS + WHOIS + SSL + Screenshot + Suspicious Page + Email Security e poderoso. O detector de suspicious page com sinais de credential_harvesting e social_engineering e diferencial real. Falta: historico de mudancas (o dominio mudou de DNS recentemente?), comparacao com site oficial.

**14. Alguma vez o sistema te disse que um dominio era seguro e voce desconfiou? O que te fez duvidar?**
mycaixa.com.br foi classificado como "safe" pelo suspicious page detector, e concordo. Mas o MATCH em si (score=0.699, risk=medium) sugere perigo. Essa desconexao entre "match diz que e suspeito" e "enrichment diz que e safe" deveria auto-resolver para rebaixar o match.

---

## Bloco 5 — Ranking e ruido

**15. Quando voce olha a lista de dominios suspeitos, o topo da lista parece relevante? Ou tem muita coisa irrelevante?**
Para Caixa: o topo (caixaap.com.br, score=0.732) nao e particularmente relevante. O dominio mais perigoso (caixagov.com.br, score=0.698) estava na 5a posicao. O ranking e por score lexical, nao por ameaca real.

**16. Ja apareceu algum dos seus proprios dominios ou de parceiros conhecidos como suspeito?**
Nao testei com dominios proprios como `official_domains`, mas o match de `sbcaixa.com.br` (empresa real Softbel) mostra que negocios legitimos aparecem sem diferenciacao.

**17. Voce confia que o score de risco reflete o nivel real de ameaca? Ou ele parece arbitrario?**
Parece arbitrario. O score e puramente lexical — nao incorpora sinais operacionais (DNS ativo, email configurado, site no ar, certificado recente). mycaixa.com.br (legit) tem score MAIOR que caixagov.com.br (phishing real). O score NAO reflete ameaca real.

**18. Quanto tempo voce gasta triando resultados que no final nao eram relevantes?**
Para Tenda com 2631 matches, seria HORAS. Sem filtro automatico de noise ou enrichment-based ranking, triar manualmente e inviavel para marcas com muitos matches.

---

## Bloco 6 — Acionabilidade

**19. Depois de ver um dominio suspeito, o produto te sugere o que fazer? Voce segue essas sugestoes?**
Sim — cada match tem `recommended_action` (ex: "Keep in watchlist unless enrichment adds operational risk"). A sugestao e generica mas correta. O campo `disposition` (defensive_gap, watchlist, phishing) ajuda. Mas sem enrichment automatico, a recomendacao e baseada em dados incompletos.

**20. Voce ja tomou alguma acao concreta (contato juridico, registro defensivo, bloqueio) a partir de um alerta do produto?**
Na simulacao: para caixagov.com.br, SIM — os dados do enrichment (dominio de 6 dias com email e sinais de credential harvesting) seriam suficientes para acionar o juridico. Mas eu tive que rodar o enrichment MANUALMENTE. Se dependesse do automatico, nao teria os dados.

**21. Se voce precisasse mostrar uma evidencia para o time juridico ou de seguranca hoje, o produto te daria o que precisaria?**
A quick-analysis para caixagov.com.br daria: screenshot, WHOIS com dados do registrante, DNS mostrando infraestrutura ativa, email security mostrando capacidade de envio. E um bom pacote de evidencias. Mas so quando forcado manualmente.

---

## Bloco 7 — Ferramentas de analise pontual

**22. Voce usa as ferramentas individuais (DNS, WHOIS, SSL, screenshot)? Em que situacoes?**
Sim — todas funcionam bem individualmente. Uso para investigacao ad-hoc de dominios especificos. A resposta e rapida (1-3 segundos por ferramenta).

**23. Voce ja usou a analise rapida combinada? O resultado foi util para uma decisao?**
Quick-analysis e o ponto forte do produto. 6 ferramentas em 17 segundos, resultado consolidado. Foi DECISIVO para classificar caixagov.com.br como phishing preparatorio. Excelente.

**24. Tem alguma ferramenta que voce sente falta e ainda nao encontrou aqui?**
Falta: (1) Comparacao visual de screenshots (site suspeito vs original), (2) Historico de DNS/WHOIS (quando mudou?), (3) Checagem contra bases de phishing (PhishTank, Google Safe Browsing), (4) Verificacao de redirect chains.

---

## Bloco 8 — Confianca e retencao

**25. Se o produto parasse de funcionar amanha, o quanto isso impactaria seu trabalho do dia a dia?**
No estado atual, ZERO impacto — porque o produto ja nao esta funcionando (scans nao processam). Se estivesse 100% operacional com enrichment automatico, seria ALTO impacto — o combo de monitoramento continuo + enrichment + priorizacao seria dificil de replicar manualmente.

**26. Voce recomendaria para um colega de outra empresa? O que voce diria sobre ele?**
"Tem potencial mas nao esta pronto. As ferramentas individuais sao boas, o conceito e solido, mas o pipeline de deteccao esta quebrado em producao. Espere a proxima versao."

**27. O que faria voce confiar mais no produto para depender dele como parte do seu processo de protecao de marca?**
(1) Scans que realmente processam e completam, (2) Enrichment automatico que ajusta o score, (3) Zero "immediate_attention" deveria ser IMPOSSIVEL para marcas como Nubank ou Itau — se o bucket esta vazio, algo esta errado, (4) Dashboard mostrando saude do sistema (ultimo scan, coverage, latencia).

**28. Tem algo que o produto faz hoje que voce acha que poderia simplesmente cortar sem sentir falta?**
As centenas de matches "exact_label_match" em TLDs exoticos (.studio, .chat, .pro) para marcas como Tenda poderiam ser agrupados como "defensive registrations" em vez de listar um por um. O volume de ruido nessa categoria e alto e polui a lista.

---

## Encerramento

**29. Se voce pudesse mudar uma coisa no produto agora, o que seria?**
Corrigir o worker de scan e ativar enrichment automatico. Sao dois bugs que, juntos, tornam o produto inteiro inoperante. Com essas correcoes, o produto passaria de "nao funciona" para "funciona e tem potencial real".

**30. Na sua escala de 0 a 10: o quanto voce diria que o produto te ajuda a detectar ameacas reais antes que causem dano?**
**3/10** — O potencial tecnico esta la (gerador de variantes, 3 fontes de ingestao, ferramentas de enrichment excelentes), mas operacionalmente nao entrega. O unico caso de deteccao util (caixagov.com.br) foi para uma marca pre-existente, exigiu enrichment manual, e nao foi priorizado corretamente. Para as 10 marcas-alvo, ZERO deteccao.

---

*Relatorio gerado em 2026-03-27 via teste automatizado da API de producao.*
