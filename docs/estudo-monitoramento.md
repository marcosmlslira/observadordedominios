
Monitoramento e validação de domínios para prevenir clonagem e impersonação de marca
Resumo executivo
Impersonação de marca via domínios (lookalike domains) é um problema estrutural do ecossistema de nomes e certificados: um atacante consegue registrar variações visualmente convincentes (typosquatting, TLDs alternativos, IDNs/homoglyphs), publicar DNS e obter certificados TLS válidos, criando sites clonados e infraestrutura de phishing em poucas horas. A defesa eficaz depende de camadas complementares de detecção (registro/RDAP, DNS, certificados/CT, conteúdo, infraestrutura e reputação) e de um processo de resposta capaz de agir rapidamente (takedown, denúncia a registrars/hosts, e caminhos legais como UDRP e SACI-Adm). 

Um programa rigoroso (sem entrar em integração técnica, assumindo base de domínios já existente) deve ser estruturado como:
(1) Descoberta contínua de domínios semelhantes (incluindo IDN e TLDs) + monitoramento de novos registros;
(2) Enriquecimento e validação (RDAP/WHOIS, DNS e e-mail, CT/TLS/OCSP, infraestrutura, reputação);
(3) Confirmação de clonagem (similaridade de conteúdo e visuais com screenshots e hashing);
(4) Pontuação e triagem (alto/médio/baixo risco) com SLAs;
(5) Resposta e remediação (bloqueios, comunicação, denúncias e playbooks legais). 

Este relatório propõe um catálogo completo de verificações, um modelo de pesos (0–100) por verificação (normalizável), frequências recomendadas, sinais típicos de falso positivo/negativo e um cronograma inicial de 30/90/180 dias (a partir de 10/04/2026) com priorização por risco.

Escopo, conceitos e modelo de ameaça
O escopo aqui é proteger a marca contra:
domínios “parecidos” (typosquatting e variações via TLDs), IDNs/homoglyphs/homographs, abuso de subdomínios (incluindo takeover por “dangling DNS”), site clonado (conteúdo/UX semelhantes, páginas de login), e abuso por e-mail (spoofing e envio a partir de domínios lookalike). A prática mostra que atacantes frequentemente combinam site + e-mail e, cada vez mais, usam phishing-as-a-service e kits com técnicas de evasão e escala. 

Do ponto de vista de “dados de registro”, é importante atualizar a mentalidade: para gTLDs, o RDAP é o sucessor do WHOIS e passou a ser a fonte definitiva de dados de registro (com sunset do WHOIS em 28/01/2025, conforme comunicado da ICANN). 
 Para o “.br”, há também RDAP disponível publicamente, e a própria documentação local o posiciona como substituto moderno do WHOIS. 

Ataques por IDN/homoglyph se apoiam no fato de que o mesmo “texto” pode ser representado por code points diferentes (misturando scripts) e ainda assim parecer idêntico para humanos; por isso, a detecção deve considerar mecanismos de confusable detection e restrições por script, como discutido no padrão de segurança Unicode (UTS #39). 

No plano de “confiança TLS”, dois pontos mudam o jogo defensivo:

certificados TLS podem ser emitidos de forma rápida e “parecerem” legítimos ao usuário final; as Baseline Requirements do CA/Browser Forum descrevem o arcabouço de requisitos para emissão e gestão de certificados publicamente confiáveis; 
já o Certificate Transparency (CT) foi concebido para registrar publicamente certificados emitidos/observados e permitir auditoria e detecção de emissões suspeitas — uma fonte extremamente útil para detectar clones antes de ampliarem a campanha. 
Framework de verificações e pesos relativos
Como ler os pesos e usar em uma pontuação
Cada verificação abaixo recebe um peso sugerido (0–100), onde 100 significa “maior contribuição prática para detectar/confirmar impersonação e priorizar resposta”. Para compor um score final (0–100) sem exigir soma de pesos, use uma média ponderada:

Score_risco = Σ(pesoᵢ × sinalᵢ) / Σ(pesoᵢ)

onde sinalᵢ é a pontuação que sua equipe atribui ao resultado daquela verificação (ex.: 0 = nenhum sinal; 1 = sinal muito forte; ou 0–100 normalizado).

Há um rascunho de framework prático previamente consolidado (com ênfase em variações e CT logs) disponível como referência interna: Markdown.md.

Tabela comparativa de verificações
A tabela resume: o que medir, o tipo de evidência e a frequência. As seções subsequentes detalham método, falsos positivos/negativos e cadência.

Verificação	Peso	Frequência recomendada	Evidência central (o que “prova” algo)
Variações de domínio (typosquatting + TLDs)	90	diária	domínio registrado/resolve e é muito semelhante ao canônico
IDN/homoglyph/homograph	80	diária	confusables (Unicode) gerando “mesma aparência”
Subdomínios: enumeração e takeover (dangling DNS)	75	diária (críticos) / semanal	CNAME “órfão”, recurso externo não reclamado, takeover possível
Observação de novos registros/zone data (brand terms)	70	diária	domínio novo contendo termos de marca/produto
RDAP/WHOIS: registro e histórico	70	diária	idade do domínio, registrador, mudanças rápidas, privacidade, padrões
DNS: resolução, NS, TTL, “fast changes”	75	diária / intradiária	mudanças frequentes, NS suspeito, TTL muito baixo, “fast-flux-like”
DNS de e-mail: MX (capacidade de enviar/receber)	65	diária	MX ativo sugerindo prontidão para campanhas por e-mail
SPF (domínios oficiais e suspeitos)	70	semanal (oficiais) / diária (suspeitos)	política de envio e avaliação de spoofing (envelope)
DKIM (domínios oficiais e suspeitos)	65	semanal (oficiais) / diária (suspeitos)	chaves e assinaturas que sustentam autenticidade e integridade
DMARC (política, alinhamento, relatórios)	85	semanal (oficiais) + análise diária de relatórios	capacidade de reduzir spoofing do “From:” e receber inteligência via reports
MTA-STS e TLS Reporting	50	mensal (oficiais)	postura de TLS entre MTAs e visibilidade de falhas/ataques
CT logs (certificados emitidos para lookalikes)	95	tempo real / a cada 5–15 min	certificado emitido/observado para domínio similar
TLS: validação de certificado e revogação (OCSP) + CAA	70	diária	cadeia, issuer, SAN, status OCSP; CAA limitando CAs autorizadas
Conteúdo: clonagem (screenshots + similaridade + hashing)	90	diária (alto risco) / semanal	“mesma página” (visual/HTML/recursos), captura de credenciais
Infra: IP/ASN/hospedagem/CDN e correlações	70	diária	infraestrutura compartilhada com abuso conhecido
Reputação: blacklists e threat intel	80	diária (ou mais)	listagem em feeds (phishing/malware/spam)
Indicadores de phishing kits/PhaaS	75	diária	padrões de kit (AiTM, evasão, caminhos/recursos) e clusterização
Marca além de domínios: redes sociais e app stores	55	semanal	perfis/apps se passando pela marca (ou suporte falso)
Prontidão legal e de marca (INPI, UDRP, SACI-Adm, TMCH)	60	trimestral + sob incidente	capacidade de acionar mecanismos e acelerar takedown/transferência

Verificações detalhadas
A seguir, cada verificação com método conceitual, falsos positivos/negativos, frequência e interpretação.

Variações de domínio: typosquatting e lookalikes via TLDs (peso 90)
Método: gerar e monitorar permutações do domínio (supressão/adição de caracteres, transposição, substituições por teclado, hífen, pluralização), além de “marca + termos” (ex.: marca-segura, marca-login) e expansões por TLD (gTLDs e ccTLDs relevantes). Complementar com observação de “zone data” quando disponível e com buscas por termos de marca em registros recentes. A disponibilidade de zone files via CZDS apoia estratégias de varredura por TLDs participantes. 

Falso positivo: afiliados/representantes legítimos, campanhas de marketing de terceiros, domínios defensivos comprados pela própria empresa e “parques” (parking) sem abuso.
Falso negativo: uso de nomes “sem marca” porém com conteúdo clonado (ex.: portal-cliente-xyz.tld), e ataques por IDN que não aparecem em permutações ASCII.

IDN/homoglyph/homograph (peso 80)
Método: aplicar confusable detection (skeleton mapping) e regras de mistura de scripts para detectar strings visualmente equivalentes, conforme mecanismos de segurança Unicode; usar também a perspectiva IDNA2008 (IDNs são processados/registrados via regras padronizadas, sem alterar o DNS em si). 

Falso positivo: palavras legitimamente multi-script em idiomas específicos; marcas que, por design, usam caracteres não ASCII.
Falso negativo: ataques que exploram confusáveis “sutis” (mesma família de glifos) ou que combinam IDN com subdomínios/paths.

Subdomínios: enumeração e takeover por dangling DNS (peso 75)
Método: manter inventário de subdomínios “válidos” e varrer DNS para identificar CNAME/ALIAS apontando para serviços externos desprovisionados (dangling records). Se o recurso no provedor não estiver mais “preso” à conta da empresa, um atacante pode reivindicá-lo e assumir o subdomínio. A mitigação inclui higiene de DNS, remoção de registros órfãos, e checagens contínuas. 

Falso positivo: ambientes de teste/desativados de propósito, “placeholder” de migração, subdomínios com tráfego zero mas ainda válidos.
Falso negativo: takeover em serviços que não expõem sinais claros (ou exigem checagens específicas por provedor).

Observação de novos registros/zone data por termos de marca (peso 70)
Método: monitorar registros recentes e domínios recém-ativados contendo tokens de marca/produto/serviço, usando dados de zona quando acessível (CZDS) e outras lentes (busca por strings, listas internas de “strings sensíveis”). A ICANN descreve o CZDS como portal para solicitar acesso a zone files de gTLDs participantes, sendo útil para ampliar varreduras e detecção precoce. 

Falso positivo: imprensa, crítica/“complaint sites”, fóruns e revendedores; páginas de suporte comunitário.
Falso negativo: domínios sem marca (genéricos), mas com clonagem via conteúdo e engenharia social.

RDAP/WHOIS: registro e histórico (peso 70)
Método: enriquecer domínios suspeitos com atributos de registro: data de criação/expiração, registrador, nameservers, mudanças recentes e padrões (ex.: troca de NS e alteração de conteúdo em janelas curtas). Para gTLD, privilegiar RDAP (substituto do WHOIS; comunicado de sunset do WHOIS em 28/01/2025). 

Falso positivo: privacidade de registro legítima (muitos registrantes usam), registradores grandes, domínios “antigos” repassados/abandonados.
Falso negativo: atacantes que comprometem domínios já “reputados” (antigos) ou usam intermediários com dados aparentemente limpos.

DNS: resolução, NS, TTL e mudanças frequentes (peso 75)
Método: monitorar resolução A/AAAA, NS, CNAME, TXT e TTL. Mudanças de NS e TTL muito baixo podem sugerir evasão/infra dinâmica. Avaliar coerência entre NS (provedor), IPs e geografia/ASN, e detectar “flip” frequente de endereços. O DNS, incluindo RR types e semântica de resolução, é normatizado desde os RFCs clássicos e o uso de MX é detalhado no padrão DNS. 

Falso positivo: CDNs e arquiteturas modernas (blue/green, DR), migração de provedor, balanceamento geográfico.
Falso negativo: clones hospedados em infraestrutura estável (sem “churn”), ou atrás de CDNs que mascaram o origin.

DNS de e-mail: MX (peso 65)
Método: verificar se domínios suspeitos publicam MX e se os MX pertencem a provedores comuns (indicando prontidão para envio/recebimento e campanhas). MX é um RR DNS padronizado e usado para roteamento de e-mail. 

Falso positivo: domínios estacionados com MX padrão do registrador; serviços de e-mail legítimos para comunidades.
Falso negativo: phishing que envia a partir de infraestrutura de terceiros sem MX “óbvio” no domínio, ou que usa apenas web (sem e-mail).

SPF (peso 70)
Método: para domínios oficiais, validar consistência e abrangência do SPF (autorização de servidores remetentes), reduzir superfícies de spoofing do envelope (MAIL FROM). Para domínios suspeitos, presença de SPF “bem feito” pode indicar intenção operacional; ausência não impede abuso (muitos ataques não configuram corretamente). O SPF é padronizado no RFC 7208. 

Falso positivo: domínios legítimos com SPF ausente/mal configurado (comum) e domínios que não enviam e-mail.
Falso negativo: spoofing que não depende de SPF por falhas de enforcement em destinos; ou ataques que usam domínios próprios do atacante com SPF correto.

DKIM (peso 65)
Método: para domínios oficiais, garantir DKIM com chaves e rotação adequadas e alinhamento planejado; para domínios suspeitos, DKIM pode aumentar credibilidade em algumas cadeias (mas não é obrigatório para phishing). DKIM é padronizado no RFC 6376. 

Falso positivo: domínios legítimos sem DKIM; provedores que assinam com domínios “shared”.
Falso negativo: phishing que não precisa de DKIM (ou se apoia em comprometimento de contas legítimas).

DMARC (política, alinhamento e relatórios) (peso 85)
Método: DMARC permite que o detentor do domínio publique política e preferências de validação/disposição e receba relatórios; é um pilar para reduzir spoofing do “From:” e produzir inteligência operacional via reports. O mecanismo é normatizado no RFC 7489 e guias de e-mail confiável do NIST tratam SPF/DKIM/DMARC como conjunto recomendado. 

Falso positivo: relatórios agregados podem ser difíceis de interpretar (forwarders, listas, gateways) e podem sugerir “falhas” sem ataque real.
Falso negativo: campanhas que usam domínios lookalike (não spoofam seu domínio) — DMARC protege mais contra spoofing direto do seu domínio, não contra domínios parecidos.

MTA-STS e TLS Reporting (peso 50)
Método: elevar a segurança do transporte de e-mail exigindo TLS e certificados confiáveis entre MTAs (MTA-STS) e coletar relatórios de falhas (TLS Reporting). Isso reduz downgrade/mitm em SMTP e fornece telemetria útil de ataques e misconfigurações. 

Falso positivo: falhas de TLS por misconfiguração de terceiros; relatórios ruidosos.
Falso negativo: ataques puramente web (sem e-mail) ou campanhas que não dependem de SMTP/TLS.

CT logs (Certificate Transparency) (peso 95)
Método: monitorar logs de CT para certificados emitidos/observados contendo domínios da sua base e variações suspeitas (inclusive subdomínios e SANs). CT foi desenhado para permitir auditoria das autoridades certificadoras e detectar emissão suspeita. Na prática, CT é um dos sinais mais precoces de que um ator está materializando um clone com HTTPS. 

Falso positivo: certificados para ambientes legítimos (parceiros, agências, fornecedores) e certificados solicitados pelo próprio time por engano.
Falso negativo: sites sem TLS (cada vez menos comuns), campanhas que atuam “curto prazo” antes de serem capturadas, ou uso de certificados não públicos (menos comum em phishing voltado a grande público).

TLS: validação de certificado, revogação (OCSP) e CAA (peso 70)
Método: para domínios suspeitos, validar cadeia, sujeito/SAN, issuer, datas e “padrões” de emissão; consultar status de revogação via OCSP (protocolo padronizado). Avaliar também se o domínio legítimo publica CAA para limitar CAs autorizadas, reduzindo risco de mis-issue. 

Falso positivo: certificados legítimos emitidos por CAs comuns; OCSP pode falhar por indisponibilidade de responder.
Falso negativo: cenários em que clientes não checam revogação de forma efetiva; abuso pode ocorrer mesmo com certificados “válidos”.

Conteúdo: clonagem (scripts, DOM, recursos e screenshots) (peso 90)
Método: capturar evidência do site suspeito (HTML, recursos estáticos, structure/DOM, formulários, endpoints) e comparar com “golden set” do site legítimo. Para robustez contra pequenas mudanças, combinar:

hashing visual com screenshots (ex.: perceptual hashing / pHash); 
similaridade de conteúdo/HTML via fuzzy hashing (ex.: ssdeep/CTPH) e/ou locality sensitive hashing (ex.: TLSH), úteis para identificar conteúdo “muito parecido” mesmo com mutações. 

Falso positivo: templates comuns (CMS), landing pages genéricas, uso de bibliotecas padrão e páginas de notícia/review que embedam conteúdo.
Falso negativo: clones “parciais” (somente a página de login), conteúdo servido dinamicamente por geolocalização, cloaking (bots veem conteúdo benigno; humanos veem phishing).
Infraestrutura: IP/ASN/hospedagem/CDN e correlações (peso 70)
Método: correlacionar IPs, ASN, provedores de hospedagem e CDNs com histórico de abuso; clusterizar domínios que compartilham infraestrutura e padrões de DNS/TLS. Isso ajuda a ligar uma detecção isolada a campanhas maiores e a priorizar incidentes.
Falso positivo: CDNs/hosts populares (muitos clientes bons e ruins misturados).
Falso negativo: infra “bulletproof” que muda rapidamente, ou uso de infra comprometida de terceiros.

Reputação: blacklists e threat intel (peso 80)
Método: consultar listas e APIs de reputação/ameaças para URLs e domínios suspeitos:

listas de navegação segura (phishing/malware) para validação rápida; 
blocklists de spam/abuso para IP/domínios; 
feeds de URLs maliciosas (malware/phishing) com APIs; 

Falso positivo: listagens por “herança” (IP compartilhado), erros de classificação, sites comprometidos que já foram limpos (defasagem).
Falso negativo: “zero day phishing” (domínio recém-criado) antes de entrar em listas, e campanhas com rotação rápida.
Indicadores de phishing kits e phishing-as-a-service (PhaaS) (peso 75)
Método: identificar assinaturas e padrões de kits (estrutura de paths, recursos/JS, endpoints de exfil, técnicas de adversary-in-the-middle para roubo de sessão/MFA) e clusterizar campanhas. Relatórios públicos sobre operações e kits em escala (incluindo kits AiTM) mostram que esse ecossistema reduz barreira e acelera replicação. 

Falso positivo: páginas legítimas com fluxos de autenticação complexos e muitos scripts; SSO corporativo pode parecer “suspeito” sem contexto.
Falso negativo: kits altamente obfuscados, servidos sob demanda, com cloaking agressivo.

Marca além de domínios: redes sociais e app stores (peso 55)
Método: monitorar contas e páginas que usam nome/logotipo/copy similares e publicam links para domínios suspeitos; monitorar também apps que se passam por “suporte”, “token”, “segurança”, “2FA” ou “atualização” da marca. Plataformas descrevem políticas e canais de denúncia específicos: por exemplo, regras contra apps que impersonam terceiros e formulários para reportar impersonação em redes sociais. 

Falso positivo: perfis de fãs/comunidades e apps de terceiros legítimos (integrações, carteiras, automação) — exige curadoria.
Falso negativo: golpes que operam em canais fechados (mensageria) e só usam redes sociais como “trânsito”.

Prontidão legal e de marca (trademarks, disputas e denúncias) (peso 60)
Método: assegurar trilhas jurídicas e administrativas para agir rápido. No Brasil, isso inclui maturidade de marca registrada e procedimentos para disputa/transferência de domínios “.br” via SACI-Adm (mecanismo administrativo descrito pelo Registro.br). 
 Para gTLDs, considerar UDRP como estrutura de resolução de disputas baseadas em marca (ICANN/WIPO) e, preventivamente, mecanismos do ecossistema de novos gTLDs (Trademark Clearinghouse: Sunrise e Claims). 

Falso positivo: disputas legítimas (crítica, uso nominativo) e casos que exigem análise jurídica contextual.
Falso negativo: ataques “descartáveis” (domínios de vida curta), onde o caminho legal é mais lento que a campanha.

Monitoramento contínuo, alertas e governança operacional
Um programa que realmente diminui risco opera como ciclo contínuo: coletar → correlacionar → pontuar → investigar → responder → aprender. Diretrizes recentes de resposta a incidentes enfatizam integração com gestão de risco e melhoria contínua, com incidentes frequentes e impacto elevado exigindo processos permanentes. 

Para “monitoramento contínuo e alertas”, práticas recomendadas (conceitualmente) incluem:

Telemetria orientada a evidências: cada alerta deve carregar “provas” suficientes para ação (prints, HTML, registro RDAP, DNS atual e anterior, certificado/CT e reputação), reduzindo retrabalho e acelerando decisões.
Normalização e correlação: unificar o que é “domínio candidato” (variações), o que é “infra compartilhada” (IP/ASN/NS/cert issuer), e o que é “comportamento” (página de login, coleta de credenciais, redirecionamentos).
Alertas com thresholds claros: por exemplo, CT + alta similaridade visual + formulário de credencial é diferente de “apenas domínio parecido recém-registrado”.
Revisão periódica de pesos: calibrar com base em incidentes reais e falsos positivos.
Na prática, o tempo de detecção é determinante. Relatórios de tendência mostram grandes volumes de phishing, reforçando que listas e denúncias chegam tarde para parte da cauda “nova”; por isso CT, variações e clonagem são tão importantes como “early warning”. 

Resposta, remediação e playbooks legais
A resposta deve separar confirmação técnica (é clone? há phishing?) de caminhos de derrubada (host/CDN/registrar/registry) e caminhos legais (transferência/cancelamento, ou preservação de prova). O playbook deve também prever comunicação (clientes, parceiros, atendimento), e ações preventivas (endurecer e-mail, reduzir spoofing).

Playbook técnico-operacional (alto nível conceitual)

Preservar evidências: screenshots, HTML, headers, certificados, registros DNS e dados RDAP (carimbo de data/hora).
Confirmar mecanismo de abuso: login falso, exfiltração, malware, redirecionamentos, cloaking.
Conter: bloquear em proxies/secure web gateways, EDR browser protections, filtros de e-mail e listas internas.
Derrubar: acionar provedor de hospedagem/CDN e registrar/registry (quando aplicável).
Notificar: canais internos, atendimento, jurídico; se necessário, comunicação externa.
Lições aprendidas: ajuste de pesos e regras, inclusão de novos padrões e domínios defensivos.
Caminho de denúncias e takedown no ecossistema de domínios

Para casos de abuso em domínios gTLD, um caminho comum é registrar abuso junto ao registrar/registry e, se persistir, escalar via mecanismos de compliance/abuse reporting associados ao ecossistema ICANN. Há orientações para submissão de reclamações e requisitos de contato/abuse do registrar. 
Para “.br”, o SACI-Adm é explicitamente descrito como sistema administrativo para solução de conflitos relativos a nomes de domínio sob “.br”, com regulamento público e funcionamento por instituições credenciadas. 
Para disputas baseadas em marca em gTLDs, UDRP se apresenta como estrutura de referência (ICANN) e WIPO mantém material explicativo e prática consolidada. 
Para prevenção e reação em novos gTLDs, mecanismos como TMCH (Sunrise/Claims) fornecem avisos e janelas de proteção, úteis como parte do playbook jurídico. 
Endurecimento de e-mail como remediação estrutural
Mesmo que parte do abuso venha de domínios lookalike, é comum haver também spoofing direto do domínio da marca. DMARC/SPF/DKIM (e, quando aplicável, MTA-STS/TLS Reporting) reduzem espaço de manobra e aumentam telemetria (relatórios). 

Plano de priorização por risco e cronograma inicial
Classificação de risco e ações
A classificação abaixo é prática e se alinha aos sinais mais “condenatórios” (CT + clonagem + credenciais + reputação). Ela não depende de integração específica; depende de critérios operacionais claros.

Nível de risco	Critérios típicos (exemplos)	SLA sugerido	Ações mínimas
Alto	CT para domínio similar e página altamente similar (screenshot/HTML) ou coleta de credenciais ou listagem em Safe Browsing/feeds; MX ativo + tema “login/2FA”	horas	preservar prova; bloquear; acionar host/CDN/registrar; comunicação interna; iniciar trilha legal
Médio	domínio similar recém-registrado (RDAP) + DNS ativo; sinais de infraestrutura suspeita; conteúdo parcial (login) sem confirmação de coleta	1–2 dias	investigação guiada por evidência; monitorar mudanças; preparar takedown
Baixo	domínio parecido mas inerte (sem DNS útil), parked, ou sem sinais adicionais; possível uso legítimo (revendedor/comunidade)	semanal	manter em watchlist; reavaliar em mudanças de DNS/CT

Critérios e SLAs devem ser documentados e revisados após incidentes, em linha com práticas de melhoria contínua discutidas em guias de resposta a incidentes. 

Cronograma de 30/90/180 dias a partir de 10/04/2026
Horizonte de 30 dias (até 10/05/2026)
Mesmo sem integração sofisticada, o foco deve ser “sinais de alto valor e baixo arrependimento”:

Definir o padrão ouro do que é “domínio oficial”: lista canônica + subdomínios críticos + provedores autorizados (e-mail, hospedagem).
Implantar monitoramento contínuo de CT logs para domínios oficiais e variações mais prováveis (CT é fonte precoce para clones HTTPS). 
Rodar geração/observação diária de variações incluindo IDN/homoglyph (Unicode confusables) e TLDs de maior risco para seu setor/país. 
Revisar postura de e-mail do domínio oficial: SPF/DKIM/DMARC (ao menos iniciar DMARC com coleta de relatórios). 
Formalizar um playbook de resposta (takedown + comunicação + jurídico) e contatos mínimos (registrars/hosts; trilhas ICANN quando aplicável). 
Horizonte de 90 dias (até 09/07/2026)

Expandir confirmação de clonagem com pipeline conceitual de screenshots e similaridade (pHash) e similaridade de HTML/recursos (ssdeep/TLSH) para os candidatos de maior risco. 
Implementar verificação contínua de dangling DNS/subdomain takeover com inventário e checagem de CNAMEs externos. 
Incluir consultas sistemáticas a reputação (Safe Browsing, Spamhaus, URLhaus/PhishTank ou equivalentes) para bloquear e enriquecer triagem. 
Adicionar monitoramento semanal de redes sociais e app stores com procedimentos de denúncia documentados (políticas e formulários). 
Evoluir playbooks para cobrir sinais de PhaaS/phishing kits, adotando clusterização e hunting por padrões. 
Horizonte de 180 dias (até 07/10/2026)

Consolidar governança e métricas: tempo médio de detecção, tempo de takedown, taxa de falsos positivos por verificação, e efetividade de bloqueios.
Fortalecer instrumentos legais e de marca: prontidão para UDRP (gTLD) e SACI-Adm (.br) com checklists de evidências e templates; manter organização de documentação de marca (cadastros, procurações, etc.). 
Revisar CAA/TLS e postura de e-mail (incluindo MTA-STS/TLS Reporting onde fizer sentido) como parte de “redução estrutural” de superfície. 
Formalizar um ciclo de melhoria contínua alinhado a práticas modernas de resposta a incidentes e gestão de risco. 
Visualizações sugeridas
Fluxo de detecção e resposta (Mermaid)

Alto

Médio

Baixo

Base de domínios oficiais

Descoberta de candidatos
typosquatting, TLDs, IDN, novos registros

Enriquecimento
RDAP/WHOIS, DNS, MX/SPF/DKIM/DMARC, CT/TLS/OCSP, IP/ASN, reputação

Coleta de evidências
HTTP headers, HTML, recursos, screenshots

Score de risco + regras de correlação

Triage acelerada
confirmar clonagem/phishing

Investigar + monitorar mudanças

Watchlist

Ação imediata
bloqueios + takedown + comunicação

Trilha legal
UDRP/SACI-Adm/denúncias

Lições aprendidas
ajustar pesos, regras e inventário



Exibir código
Gráficos para distribuição de risco (para dashboards executivos e operação)

Histograma (ou barras) com a distribuição do score dos candidatos na semana/mês (ex.: 0–25 / 26–50 / 51–75 / 76–100), para ver “pressão” de risco e efeito de campanhas.
“Pareto” de verificações: quais verificações mais contribuíram para classificar casos como alto risco (CT, clonagem, reputação, etc.).
Série temporal: “novos candidatos por dia” vs “incidentes confirmados” vs “takedowns concluídos”, para medir eficiência e capacidade.
Sankey/flow: origem dos alertas (CT, variações, reputação) → classificação (alto/médio/baixo) → resultado (takedown, falso positivo, monitorar).