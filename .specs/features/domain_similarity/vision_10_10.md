# North Star 10/10 - Brand Protection

## 1. Proposito deste documento

Este documento define o estado ideal do mecanismo principal do Observador de Dominios.
Ele existe para servir como alvo continuo de produto, engenharia, operacao e priorizacao.

Nao e um PRD de uma unica feature.
Nao e um backlog.
Nao e um texto inspiracional generico.

Ele responde:

- O que precisa ser verdade para o produto ser 10/10?
- Como reconhecemos que estamos nos aproximando disso?
- O que nunca devemos aceitar como "bom o bastante"?
- Como esse alvo deve orientar decisoes dia apos dia?

## 2. Visao do produto

O Observador de Dominios, no seu estado ideal, e a plataforma mais confiavel para times enxutos detectarem, priorizarem e agirem sobre ameacas reais de uso indevido de marca em dominios.

O produto nao ganha porque mostra mais dados.
O produto ganha porque transforma superficie de ataque em decisao clara, cedo o suficiente para evitar dano.

Em um produto 10/10:

- a marca oficial e corretamente entendida em qualquer TLD relevante, inclusive sufixos multi-nivel como `com.br`, `gov.br`, `net.br` e `org.br`
- a descoberta e ampla, mas o ranking e seletivo
- o sistema diferencia ruido de ameaca real
- a deteccao chega cedo
- o analista entende por que um dominio foi priorizado
- cada resultado sugere a proxima acao correta
- o monitoramento continuo e confiavel o bastante para o cliente depender dele

## 3. Definicao objetiva de 10/10

O mecanismo e 10/10 quando um cliente de marca critica, apos usar o produto em producao, conclui:

- "Estou vendo os dominios certos"
- "Estou vendo cedo o suficiente"
- "Estou vendo com contexto suficiente"
- "O ranking faz sentido"
- "O produto me ajuda a agir"
- "Nao estou perdendo tempo com lixo"
- "Eu confiaria nisso como camada principal do meu processo"

Se qualquer uma dessas frases ainda falhar com frequencia, o produto ainda nao e 10/10.

## 4. Promessa central ao cliente

Quando eu cadastro minha marca, o produto deve:

1. Cobrir os TLDs e sufixos que realmente importam para minha superficie de risco.
2. Encontrar dominios e sinais que possam causar dano real a marca.
3. Reduzir falsos positivos obvios e auto-infringimento.
4. Enriquecer cada caso com contexto suficiente para triagem.
5. Priorizar o que exige acao agora.
6. Manter monitoramento continuo com estado observavel e confiavel.

## 5. Principios nao negociaveis

### 5.1 Menos dados, mais decisao

Mostrar mais linhas nao cria valor.
Valor existe quando o cliente sabe o que ignorar, o que investigar e o que escalar.

### 5.2 Ruido mata o produto

Se o topo da fila tiver dominios oficiais, self-owned, parked irrelevante ou falso positivo sem contexto, a confianca quebra rapidamente.

### 5.3 Velocidade e parte do produto

Deteccao tardia e quase equivalente a nao deteccao.
Busca lenta ou scan parado destroem valor, mesmo que a modelagem esteja tecnicamente correta.

### 5.4 Contexto vem antes do score

Score sem explicacao e suspeito.
O cliente precisa entender por que aquilo importa.

### 5.5 Cobertura brasileira nao e opcional

Para o contexto do produto, `com.br`, `gov.br`, `net.br` e `org.br` nao sao edge cases.
Sao parte do core.

### 5.6 Todo estado inconclusivo deve ser honesto

Se o sistema nao conseguiu analisar, ele deve dizer isso claramente.
Nunca chamar de `safe` algo que e apenas `unreachable`, `challenge`, `error` ou `unknown`.

## 6. Os 7 pilares do mecanismo 10/10

### Pilar 1 - Cobertura correta

O sistema entende dominio registravel, public suffix e TLD estrategico de forma nativa.

No estado ideal:

- `claro.com.br` tem label `claro` e suffix `com.br`
- `caixa.gov.br` tem label `caixa` e suffix `gov.br`
- cobertura publica exposta na API reflete cobertura real
- o cliente sabe o que esta sendo monitorado e o que nao esta

Falha classica a evitar:

- aceitar cadastro de sufixo relevante sem dar prova de cobertura operacional

### Pilar 2 - Descoberta util

A descoberta precisa achar risco real sem explodir o espaco de busca desnecessariamente.

No estado ideal:

- exact match, typo, homoglyph, prefixo/sufixo e TLD variation sao cobertos
- discovered candidates sao plausiveis, nao combinacoes arbitrarias
- o sistema distingue universo gerado de universo observado

Falha classica a evitar:

- devolver listas enormes de variacoes sem priorizacao, contexto ou prova de registro

### Pilar 3 - Ranking confiavel

O topo da fila deve ser defensavel.

No estado ideal:

- dominios oficiais nao aparecem por padrao
- self-owned related e rebaixado automaticamente
- exact-match ativo em TLD estrategico sobe
- parked/for-sale exato vira `defensive_gap`
- typo ativo com site, MX ou credenciais sobe
- terceiro legitimo antigo e rebaixado

Falha classica a evitar:

- score alto por coincidencia lexical e score baixo para risco defensivo obvio

### Pilar 4 - Enriquecimento acionavel

Cada dominio suspeito deve ganhar contexto tecnico e de risco suficiente para decisao.

No estado ideal:

- DNS, WHOIS, SSL, headers, screenshot e page analysis sao coerentes entre si
- mail-only risk e visivel
- parked, for-sale, challenge, unreachable e self-owned sao estados explicitos
- clone detection lida com WAF, TLS e referencias protegidas sem cair em erro opaco

Falha classica a evitar:

- WHOIS dizendo "nao existe" enquanto DNS/TLS/HTTP provam que o dominio esta vivo

### Pilar 5 - Tempo operacional

O produto precisa ser rapido no que e sincrono e confiavel no que e assincrono.

No estado ideal:

- busca sincrona serve para triagem imediata
- jobs de scan entram em fila, iniciam, progridem e terminam
- cada job tem estado, timestamps, erro e throughput observaveis

Falha classica a evitar:

- `queued` eterno
- timeout recorrente no endpoint principal

### Pilar 6 - Explicabilidade

O cliente precisa entender por que o produto concluiu algo.

No estado ideal:

- cada match explica score, sinais, confianca e classificacao
- o usuario entende a diferenca entre `safe`, `inconclusive`, `defensive_gap`, `likely_phishing`, `self_owned_related` e `third_party_legitimate`
- o sistema mostra a fonte e a qualidade do dado quando relevante

Falha classica a evitar:

- score magico, signal nonsense, ou categoria sem criterio visivel

### Pilar 7 - Operacao continua

O produto nao pode depender de "dar sorte" em testes manuais.

No estado ideal:

- pipelines de deploy sao robustos
- scans nao param por falta de observabilidade
- degradacoes sao perceptiveis
- metrica e revisao humana retroalimentam o ranking

Falha classica a evitar:

- deploy entra, mas ninguem consegue provar se o comportamento novo esta efetivamente em uso

## 7. Scorecard permanente do produto

Este scorecard deve ser revisado continuamente.

### 7.1 Cobertura

- TLDs/sufixos estrategicos da marca cobertos
- cobertura publica coerente com cobertura real
- suporte correto a multi-level suffixes

Meta 10/10:

- 100% dos sufixos estrategicos relevantes representados corretamente

### 7.2 Latencia

- P95 da busca sincrona
- tempo medio para primeira evidenca acionavel
- tempo de fila para iniciar scan

Meta 10/10:

- busca principal com P95 abaixo de 5 segundos
- scan iniciando em tempo previsivel

### 7.3 Precisao

- percentual de self-owned nos top resultados
- percentual de third-party legitimate nos top resultados
- falsos positivos grosseiros por batch

Meta 10/10:

- top da fila dominado por ameacas reais ou gaps defensivos reais

### 7.4 Qualidade de contexto

- matches com DNS + WHOIS + HTTP + screenshot coerentes
- casos inconclusivos explicitamente rotulados
- inconsistencias de enrichment tratadas como baixa qualidade

Meta 10/10:

- nenhum caso importante rotulado como `safe` por falta de prova

### 7.5 Acionabilidade

- percentual de matches com classificacao clara
- percentual de casos em que a proxima acao e obvia
- tempo de decisao humana por caso

Meta 10/10:

- o analista sabe o que fazer no topo da fila sem reabrir dez ferramentas

## 8. Taxonomia ideal de saida

Toda saida do mecanismo deve tender a uma destas disposicoes:

- `official`
- `self_owned_related`
- `third_party_legitimate`
- `defensive_gap`
- `live_but_unknown`
- `likely_phishing`
- `mail_spoofing_risk`
- `inconclusive`

Objetivo:

- reduzir estados ambiguos
- evitar `safe` generico
- transformar a leitura em decisao

## 9. O que um cliente 10/10 ve na pratica

Ao cadastrar uma marca, o cliente ideal observa:

1. Seus dominios oficiais foram entendidos corretamente.
2. O produto diz com clareza quais TLDs e sufixos estao monitorados.
3. A busca inicial responde rapido e sem trazer o proprio dominio oficial.
4. O topo da lista traz:
   - exact-match em TLDs alternativos
   - typo ativo relevante
   - casos mail-only perigosos
   - parked/for-sale com risco defensivo claro
5. Cada item vem com:
   - explicacao
   - screenshot ou ausencia honesta de captura
   - contexto DNS/WHOIS/HTTP
   - classificacao
   - proxima acao sugerida
6. O scan continuo entra em execucao, mostra progresso e gera historico

## 10. O que jamais devemos aceitar como "quase la"

- timeout recorrente no endpoint principal
- scan parado em `queued`
- dominio oficial ranqueado como suspeito
- parked exact-match rotulado como `safe`
- page unreachable rotulada como `safe`
- heuristica acusando site oficial da propria marca
- TLD critico aceito no cadastro mas invisivel na cobertura
- erros opacos em clone detection, WHOIS ou fetch

## 11. Como usar este documento dia apos dia

Este documento deve ser usado como filtro de decisao continua.

### Ao priorizar backlog

Pergunta:

- isso reduz risco real?
- isso reduz ruido?
- isso melhora velocidade?
- isso aumenta confianca?

Se a resposta for nao, a prioridade deve cair.

### Ao revisar PR

Pergunta:

- isso aproxima o topo da fila do que um cliente realmente investigaria?
- isso melhora cobertura, tempo, contexto ou decisao?
- isso evita regressao nos principios nao negociaveis?

### Ao validar release

Pergunta:

- a producao agora esta mais proxima do estado 10/10?
- que comportamento concreto mudou?
- que gargalo principal continua intocado?

### Ao testar com marcas reais

Pergunta:

- o produto mostrou o dominio certo?
- mostrou cedo?
- explicou bem?
- ajudou a agir?
- ou so gerou mais trabalho?

## 12. Definicao de progresso real

Nao e progresso real quando:

- o contrato muda, mas o uso continua lento
- a API fica mais bonita, mas o topo da fila continua ruim
- o erro fica menos feio, mas o caso continua sem decisao

E progresso real quando:

- a chance de detectar cedo aumenta
- o tempo de triagem humana cai
- o top 10 fica mais relevante
- o cliente confia mais no produto depois do uso real

## 13. Norte final

Nosso alvo diario nao e "ter mais features".

Nosso alvo diario e fazer o cliente dizer:

"Se eu ignorar o topo da fila, eu corro risco real."

Quando o Observador atingir esse estado com confianca, consistencia e clareza, o mecanismo principal sera 10/10.
