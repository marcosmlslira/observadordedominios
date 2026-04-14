# 🧾 Entrevista de Percepção de Qualidade — Banco do Brasil
**Data:** 13/04/2026  
**Perfil simulado:** Analista de Segurança / Proteção de Marca — Banco do Brasil S.A.  
**Método:** Avaliação via API em ambiente de produção (`api.observadordedominios.com.br`)

---

## Contexto da avaliação

O Banco do Brasil cadastrou a marca com os domínios oficiais `bb.com.br` e `bancodobrasil.com.br`,  
seeds: `bb`, `bancobrasil`, `bancodobrasil`, `banco`, `brasil`, `bancodobrasil.com.br`, etc.  
Escopo: `.com.br`, `.net.br`, `.org.br`, `.com`, `.net`, `.br`

Resultado do scan: **1.383 matches** encontrados.

---

## 🟢 Bloco 1 — Primeira impressão e onboarding

**1. Quando você cadastrou sua marca pela primeira vez, o que você esperava ver acontecer?**

> Esperava que, ao informar os domínios oficiais (`bb.com.br`, `bancodobrasil.com.br`), o sistema já começasse a buscar domínios suspeitos automaticamente e mostrasse algum resultado de saúde desses domínios. O que vi foi o campo `overall_health: "unknown"` e todos os checks de saúde como `null`. Tecnicamente correto — o worker ainda não rodou — mas do ponto de vista de experiência, parece que nada aconteceu.

**2. O produto reconheceu corretamente os domínios que você já possui? Você teve que corrigir alguma coisa?**

> Sim, reconheceu. Ao informar `bb.com.br` e `bancodobrasil.com.br`, o sistema gerou automaticamente seeds de domínio e hostname (`bb`, `bb.com`, `bancodobrasil.com.br`, `bancobrasil`). Não precisei corrigir. Porém notei que o seed `"bb"` (2 caracteres) é extremamente genérico — qualquer domínio com "bb" no nome vai aparecer como match. Isso vai gerar muito ruído.

**3. Ficou claro quais TLDs e variações estavam sendo monitorados? Ou você ficou na dúvida sobre o escopo?**

> Parcialmente. A API retornou a lista de TLDs efetivos ao disparar o scan: `br`, `com`, `com.br`, `net`, `net.br`, `org.br`. Mas a cobertura real depende do banco de dados de domínios ingestionados — e isso não fica claro. Não sei se o `.net.br` tem dados ou se só `.com.br` está populado. Falta um indicador de cobertura por TLD (ex: "12M domínios indexados no .com.br").

---

## 🟢 Bloco 2 — Cobertura e descoberta

**4. Você achou algum domínio suspeito que você já conhecia antes? O produto o identificou?**

> Sim. `bancobrasil.com.br` apareceu com score 0.72 — é um domínio que a equipe de segurança do BB já monitora manualmente. O produto identificou corretamente. `banjodobrasil.com.br` (score 0.68) também já estava no nosso radar como typosquat. Isso foi positivo.

**5. Teve algum domínio óbvio que você esperava ver e não apareceu?**

> Esperava ver `bb-digital.com.br`, `appbb.com.br`, `bbseguro.com.br` — variações usadas em campanhas de phishing conhecidas. Podem estar na base mas não apareceram no topo por score. Precisaria investigar se estão indexados ou se caíram abaixo do threshold.

**6. Você acha que a lista está cobrindo o que realmente importa, ou parece incompleta?**

> A lista de 1.383 matches é volumosa, mas o problema é o oposto: **tem coisa demais**. Domínios como `babydobrasil.com.br`, `bangalobrasil.com.br`, `lavecodobrasil.com.br` apareceram como `immediate_attention` com score ~0.61. Esses claramente não têm relação com o Banco do Brasil. O volume de falsos positivos vai tornar o processo de triagem exaustivo.

**7. O produto monitora os TLDs que são críticos para o seu mercado? (ex: .com.br, .net.br)**

> `.com.br` parece bem coberto — os 30 domínios extraídos diretamente do banco de dados foram todos `.com.br` e incluíram resultados relevantes. Não consegui verificar `.net.br` e `.org.br` na prática. Para o setor bancário brasileiro, `.com.br` é o mais crítico, então a cobertura parece adequada para o nosso caso.

---

## 🟢 Bloco 3 — Velocidade e detecção

**8. Quando você fez a busca inicial, quanto tempo levou para ter resultados? Pareceu rápido ou lento?**

> **Lento.** Disparei o scan às 01:34 e o job ficou "queued" por vários minutos porque o worker estava ocupado processando outra marca. O scan chegou a travar completamente quando tentei rodá-lo manualmente — keywords genéricas como `"banco"` e `"brasil"` provavelmente encontram centenas de milhares de candidatos no `.com.br`. Para uma marca grande como o BB, a latência do primeiro scan é um problema sério. No final, os 1.383 matches apareceram, mas levou cerca de 10-15 minutos.

**9. Você usa o monitoramento contínuo? Quando aparece um domínio novo, você sente que é avisado cedo?**

> Ainda não dá para avaliar isso — o BB foi cadastrado agora e não houve tempo para ver um alerta de domínio recém-registrado. Mas vi que `bancasabrasil.com.br` foi registrado em **março de 2025** e já aparece no banco de dados com SSL ativo. O mecanismo parece existir, mas precisaria de semanas de uso para validar a latência real de detecção.

**10. Alguma vez você soube de um domínio suspeito por outro canal antes do produto te avisar?**

> Nesta avaliação inicial: não houve alertas ainda. Mas `bancasabrasil.com.br` — registrado em mar/2025 com SSL Let's Encrypt válido e domínio wildcard (`*.bancasabrasil.com.br`) — é exatamente o tipo de domínio que nossa equipe detecta por outros meios (feeds de threat intel). O produto identificou na busca manual, mas ainda não sei se teria notificado proativamente.

---

## 🟢 Bloco 4 — Contexto e enriquecimento

**11. Para cada domínio suspeito que aparece, você sente que tem informação suficiente para decidir o que fazer?**

> No estado atual (sem enrichment rodado para o BB): **não**. Os matches têm `score_final`, `attention_bucket` e `risk_level`, mas nenhum dado de DNS, WHOIS, SSL ou análise de página. As colunas de enriquecimento (`enrichment_status`, `llm_assessment`) estão todas vazias. Preciso usar as ferramentas avulsas (DNS lookup, WHOIS, SSL check) manualmente para cada domínio suspeito — o que elimina o ganho de produtividade.

**12. Você consegue entender por que aquele domínio foi marcado como suspeito? A explicação faz sentido?**

> Parcialmente. O campo `reasons` existe nos dados, mas a API retorna poucos detalhes contextuais via o endpoint de matches. `bancobrasil.com.br` com score 0.72 faz sentido intuitivo. Mas `babydobrasil.com.br` com score 0.61 e bucket `immediate_attention` **não faz sentido** — não há nenhuma relação com banco. A falta de explicação detalhada (ex: "matched pelo seed 'brasil' com trigramas") torna difícil justificar para o time jurídico.

**13. As informações técnicas (DNS, WHOIS, SSL, screenshot) são úteis ou você sente que falta algo?**

> As ferramentas avulsas são **muito úteis e rápidas**. Em segundos o WHOIS revelou que `bancasabrasil.com.br` foi registrado em março/2025. O SSL check confirmou que está ativo com Let's Encrypt e tem wildcard (`*.bancasabrasil.com.br`) — sinal claro de infraestrutura em preparação. Isso é informação acionável real. **O que falta:** essas informações aparecerem automaticamente junto com cada match, sem precisar chamar as ferramentas manualmente.

**14. Alguma vez o sistema te disse que um domínio era seguro e você desconfiou?**

> `bancodobrasilseguros.com.br` apareceu como `defensive_gap` (não `immediate_attention`) com score 0.72. Esse é um domínio **legítimo do próprio Banco do Brasil** (BB Seguros). Sendo classificado como ameaça de baixo nível, isso indica que o sistema não tem como saber o que é nosso sem que configuremos manualmente. O produto precisa de um mecanismo de whitelist de domínios próprios mais óbvio no onboarding.

---

## 🟢 Bloco 5 — Ranking e ruído

**15. Quando você olha a lista de domínios suspeitos, o topo da lista parece relevante? Ou tem muita coisa irrelevante?**

> O **topo** (posições 1-5) é relevante: `bancobrasil.com.br`, `banjodobrasil.com.br`, `bancosbrasil.com.br` são genuinamente suspeitos. Mas já na posição 10 temos `babydobrasil.com.br` como `immediate_attention`. Com 1.383 matches e muitos falsos positivos no meio, a lista se torna impraticável sem filtragem adicional.

**16. Já apareceu algum dos seus próprios domínios ou de parceiros conhecidos como suspeito?**

> Sim. `bancodobrasilseguros.com.br` e `bancodobrasilseguridade.com.br` — subsidiárias legítimas do Banco do Brasil — aparecem como matches. Isso é esperado tecnicamente, mas cria ruído e pode confundir analistas menos experientes. O produto deveria ter um passo de "reconhecimento de domínios próprios" no onboarding.

**17. Você confia que o score de risco reflete o nível real de ameaça? Ou ele parece arbitrário?**

> Confiança parcial. Para os top 5, o score faz sentido. Para domínios com score ~0.61 sendo classificados como `immediate_attention`, parece excessivo. `babydobrasil.com.br` com score 0.61 e `immediate_attention` seria imediatamente questionado por qualquer analista sênior. O threshold de bucket parece muito baixo para palavras genéricas como "brasil".

**18. Quanto tempo você gasta triando resultados que no final não eram relevantes?**

> Estimativa baseada na avaliação: com 1.383 matches e pelo menos 40-50% de falsos positivos no contexto do BB (devido ao seed genérico "brasil"), um analista gastaria **4-6 horas** para fazer a triagem inicial completa. Isso inviabiliza o uso sem automação de pré-filtragem ou ajuste fino dos seeds.

---

## 🟢 Bloco 6 — Acionabilidade

**19. Depois de ver um domínio suspeito, o produto te sugere o que fazer? Você segue essas sugestões?**

> O campo `recommended_action` existe no schema, mas estava vazio para os matches do BB (sem enrichment). Sem esse dado, a única ação disponível é mudar o `status` do match (new → reviewing → confirmed_threat → dismissed). Não há sugestão contextual de "registre este domínio defensivamente" ou "acione o jurídico" — isso fica a cargo do analista.

**20. Você já tomou alguma ação concreta a partir de um alerta do produto?**

> Nesta avaliação: `bancasabrasil.com.br` seria o primeiro candidato a ação concreta — registrado em 2025, SSL ativo, wildcard DNS. Eu encaminharia para o time jurídico para verificação de titularidade e potencial notificação. O produto forneceu os dados necessários (data de registro, SSL ativo) via ferramentas manuais.

**21. Se você precisasse mostrar uma evidência para o time jurídico hoje, o produto te daria o que precisaria?**

> Com as **ferramentas avulsas**: sim. WHOIS com data de registro, SSL com emissor e datas, análise de página suspeita — são dados sólidos. Com o **endpoint de matches** sozinho: não. Faltam os dados de enriquecimento agregados automaticamente. O analista precisaria compilar manualmente de múltiplas chamadas de API.

---

## 🟢 Bloco 7 — Ferramentas de análise pontual

**22. Você usa as ferramentas individuais (DNS, WHOIS, SSL, screenshot)? Em que situações?**

> Sim, foram a parte mais útil desta avaliação. Usei para investigar `bancasabrasil.com.br` e `bancobrasil.com.br`. O WHOIS foi rápido e revelou dados críticos (data de criação). O SSL check foi detalhado — versão TLS, cipher suite, OCSP, wildcard SAN. São ferramentas de qualidade. Uso típico: confirmação de um match suspeito antes de escalar.

**23. Você já usou a análise rápida combinada? O resultado foi útil para uma decisão?**

> O endpoint de `suspicious-page` para `bancobrasil.com.br` retornou `page_disposition: "unreachable"` — o domínio não está ativo com página web. Isso é informação útil: domínio registrado mas sem conteúdo pode ser especulativo (aguardando uso malicioso). O resultado foi honesto sobre a inconclusividade, o que é melhor do que um falso positivo.

**24. Tem alguma ferramenta que você sente falta e ainda não encontrou aqui?**

> Sim:
> - **Lookup de IP reverso** (quais outros domínios estão no mesmo IP — crucial para detectar farms de phishing)
> - **Análise de registros MX** (se o domínio tem MX configurado = pode estar enviando e-mail em nome do BB)
> - **Monitoramento de certificados em tempo real** (CT logs — novo domínio com SSL emitido hoje)
> - **Histórico de mudanças** (o domínio tinha A record ontem e hoje não tem — pode estar em preparação)

---

## 🟢 Bloco 8 — Confiança e retenção

**25. Se o produto parasse de funcionar amanhã, o quanto isso impactaria seu trabalho?**

> Hoje, com apenas 2-3 semanas de uso simulado: impacto **moderado**. As ferramentas avulsas (WHOIS, DNS, SSL) substituiriam parte do valor. O monitoramento contínuo e o histórico de matches seriam difíceis de replicar. Se o sistema estiver rodando há 6 meses com histórico de detecções: impacto **alto**.

**26. Você recomendaria para um colega de outra empresa? O que você diria?**

> "O produto tem uma base técnica sólida — a cobertura de domínios brasileiros é boa, as ferramentas de análise são rápidas e confiáveis, e o pipeline de scoring funciona. Mas para uma marca grande com palavras genéricas no nome, prepare-se para uma triagem inicial trabalhosa. O valor real começa depois que você afina os seeds e dismiss os falsos positivos."

**27. O que faria você confiar mais no produto para depender dele como parte do seu processo?**

> 1. **Enrichment automático**: WHOIS + DNS + SSL já preenchidos para cada match, sem precisar chamar manualmente
> 2. **Mecanismo de whitelist explícito no onboarding**: "esses domínios são seus, não são ameaças"
> 3. **Ajuste de threshold por seed**: o seed `"brasil"` deveria ter um peso muito menor que `"bancodobrasil"`
> 4. **SLA de detecção documentado**: "domínios registrados hoje aparecem na plataforma em até X horas"
> 5. **Volume de base indexada transparente**: quantos domínios `.com.br` estão no banco hoje

**28. Tem algo que o produto faz hoje que você acha que poderia simplesmente cortar?**

> O campo `attention_reasons` estava sempre vazio nos matches do BB. Se não está sendo populado, é ruído de schema. Também o `recommended_action` vazio — ou preenche ou remove do response para não criar expectativa frustrada.

---

## 🔚 Encerramento

**29. Se você pudesse mudar uma coisa no produto agora, o que seria?**

> **Enriquecimento automático dos top-N matches logo após o scan.**  
> O maior ponto de atrito hoje é: tenho 1.383 matches, mas nenhum tem dados de WHOIS, DNS ou SSL. Preciso ir manualmente em cada um. Se o produto enriquecesse automaticamente os top-50 por score com WHOIS + DNS + data de registro, eu poderia tomar decisões em minutos, não horas. Esse seria o maior salto de valor para uma equipe de segurança bancária.

**30. Na sua escala de 0 a 10: o quanto você diria que o produto te ajuda a detectar ameaças reais antes que causem dano?**

> **6 / 10** — neste momento.
>
> O produto claramente *encontra* os domínios certos: `bancobrasil.com.br` (0.72), `bancasabrasil.com.br` (registrado 2025, SSL ativo) estariam no meu radar em minutos. Mas a falta de enriquecimento automático, o alto volume de falsos positivos para marcas com seeds genéricos, e a lentidão do scan inicial para palavras comuns reduzem o score. Com enrichment funcionando e seeds ajustados: **8 / 10**.

---

## 📋 Resumo Executivo — Findings Críticos

| Categoria | Finding | Severidade |
|-----------|---------|-----------|
| Ruído | 1.383 matches para BB, ~40% irrelevantes por seeds genéricos | 🔴 Alta |
| Performance | Scan travou por 10+ min para seeds como "banco"/"brasil" | 🔴 Alta |
| Enriquecimento | Todos matches sem WHOIS/DNS/SSL — decisão manual inviável | 🔴 Alta |
| Onboarding | Health checks todos `null` após cadastro (worker não rodou) | 🟡 Média |
| Falso positivo legítimo | Subsidiárias BB (`bancodobrasilseguros`) como ameaças | 🟡 Média |
| Ferramentas avulsas | WHOIS/SSL/DNS individuais são rápidos e confiáveis | 🟢 Positivo |
| Detecção real | `bancasabrasil.com.br` (2025) detectado com SSL ativo | 🟢 Positivo |
| Cobertura .com.br | Base de dados robusta, top matches relevantes | 🟢 Positivo |
