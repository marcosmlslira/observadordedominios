# TESTE DE FLUXO CORE — Observador de Domínios

**Data**: 13 de Abril de 2026  
**Foco**: Login → Dashboard → Marca BB → Matches → Detalhe  
**Testador**: Agente UX automatizado (Playwright/Chromium, viewport 1440×900)  
**Base URL**: https://observadordedominios.com.br

---

## VEREDICTO GERAL

O fluxo principal funciona parcialmente: login, dashboard e a página de marca operam com dados reais. Porém, **o produto está bloqueado na etapa mais crítica para o usuário**: não é possível acessar o detalhe de nenhum domínio suspeito. As rotas `/admin/matches` e `/admin/brands/{id}/matches` retornam 404, e as linhas clicáveis da tabela de ameaças não navegam para lugar algum, tornando o core loop de investigação inacessível.

**Nota**: 5/10

---

## PASSO A PASSO DO FLUXO

### ✅ Passo 1 — Login

- **Funciona?**: Sim
- **Screenshots**: `core_01_login_empty.png`, `core_02_login_filled.png`, `core_03_after_login.png`
- **O que o usuário vê**: Tela de login minimalista com campos de e-mail e senha, botão "Entrar". Design limpo, sem distrações.
- **Tempo estimado**: ~4 segundos (rede + redirect)
- **URL após login**: `https://observadordedominios.com.br/admin`
- **Problemas**:
  - Nenhum crítico
  - Sem feedback visual de "carregando" após clicar no botão (UI trava por 1–2s antes de redirecionar)
- **Nota**: 8/10

---

### ✅ Passo 2 — Dashboard

- **Funciona?**: Sim
- **Screenshot**: `core_04_dashboard.png`
- **Dados visíveis**:
  - **33** marcas monitoradas (ativas)
  - **693.967.450** domínios totais ingeridos
  - **4 fontes de ingestão** (3 rodando em tempo real)
  - **Threat Intelligence**:
    - 51 ameaças imediatas
    - 40 Defensive Gap
    - 1.574 Watchlist
    - 1.592 novos nos últimos 7 dias (1.573 nas últimas 24h)
  - **Ingestion Sources com status**:
    - CZDS: 624,7M inseridos — `running`
    - CertStream: 14,2M inseridos — `running`
    - crt.sh: 123K inseridos — `success`
    - OpenINTEL: 55M inseridos — `running`
  - **Quick Actions**: Novo Brand, View Ingestion
- **O usuário entende o que está vendo?**: Sim — o dashboard é informativo e orientado a operações. Os números são claros.
- **Problemas**:
  - O card de "Threat Intelligence" redireciona para `/admin/matches?bucket=immediate_attention` que retorna **404** — link quebrado logo na homepage
  - Não há separação visual clara entre "ameaças totais" e "ameaças novas" — pode confundir o operador
- **Nota**: 7/10

---

### ✅ Passo 3 — Lista de Marcas

- **Funciona?**: Sim
- **Screenshot**: `core_05_brands_list.png`
- **URL**: `/admin/brands`
- **Marcas visíveis**:
  | Marca | Status | Immediate | Defensive | Watchlist | Domínios |
  |-------|--------|-----------|-----------|-----------|---------|
  | Banco do Brasil | critical | 0 | 50 | 0 | bb.com.br, bancodobrasil.com.br |
  | Bradesco | unknown | 0 | 0 | 0 | — |
  | Observador de Domínios | critical | 0 | 13 | 0 | observadordedominios.com.br |
- **Informações por marca**: Badge de status (critical/unknown), contadores por bucket, domínios monitorados, botões "Scan" e "View"
- **Problemas**:
  - Bradesco aparece como "unknown" sem nenhuma ameaça — não está claro se é um perfil novo sem dados ou uma falha de scan
  - Falta paginação (não visível com apenas 3 marcas — OK por enquanto)
  - O header da página diz "Monitoring Profiles" mas o link do menu é "Monitored Brands" — inconsistência de nomenclatura
- **Nota**: 8/10

---

### ✅ Passo 4 — Página da Marca BB (Banco do Brasil)

- **Funciona?**: Sim
- **Screenshot**: `core_06_brand_bb.png`
- **URL**: `/admin/brands/4185de60-db89-43ca-95d6-b09b385a2db5`
- **Health/Status visível?**: Sim — badge `critical`
- **Matches count visível?**: Sim — 50 Defensive Gap (via filtro)
- **Categorias de ameaça visíveis?**: Sim — All / Immediate / Defensive Gap / Watchlist
- **Primeira impressão do usuário**:
  - Header: "Banco do Brasil" + status `critical` + tag `bb` + botão "Trigger Scan"
  - Stats cards: 0 Immediate | 50 Defensive | 0 Watchlist
  - **Latest Monitoring Cycle**: Date 2026-04-13, Health `completed`, Scan `pending`, Threats `0`, New Matches `0`
  - **Domain Health** (tabela):
    - `bancodobrasil.com.br` — status `unknown`, DNS/SSL/Email/Headers/Blacklist todos vazios, sem data
    - `bb.com.br` — status `primary`, risco `critical`, última verificação 12/04/2026
  - **Threats** (tabela com 50+ linhas): bancobrasil.com.br (72%), bancodobrasilseguros.com.br (72%), projetobancodobrasil.com.br (71%)...
  - Ao final da página: "Brand Configuration" + "Cycle History (1)"
- **Problemas**:
  - **INCONSISTÊNCIA**: Monitoring Cycle mostra "Threats: 0, New Matches: 0" — mas a marca tem 50 ameaças listadas na tabela abaixo. O usuário não vai entender.
  - `bancodobrasil.com.br` no Domain Health está "unknown" sem dados — o domínio principal da marca não tem dados de saúde
  - Scan status = `pending` mas sem indicação de quando será executado
  - Linhas da tabela de threats têm `cursor-pointer` (sugerindo clique) mas **não navegam** — bug crítico
  - Coluna "Signals" na tabela de threats está vazia para todos os itens
  - "0 Watchlist" nos stats mas o filtro Watchlist mostra 2 linhas (bancodobrasil.com.br e bb.com.br — que são os próprios domínios monitorados, não ameaças)
- **Nota**: 6/10

---

### ✅ Passo 5 — Abas/Filtros da Marca

- **Abas disponíveis**: All, Immediate, Defensive Gap, Watchlist (são buttons de filtro, não tabs navegáveis)
- **Screenshots**: `core_07_brand_tab_all.png`, `core_08_brand_tab_immediate.png`, `core_09_brand_tab_defensive.png`, `core_10_brand_tab_watchlist.png`
- **Resultado de cada filtro**:
  | Filtro | Conteúdo |
  |--------|----------|
  | **All** | 50 domínios suspeitos, todos "Defensive Gap" |
  | **Immediate** | Mensagem: _"No threats found in 'Immediate'"_ + Domain Health |
  | **Defensive Gap** | 50 domínios suspeitos (mesmo que All) |
  | **Watchlist** | 2 linhas — apenas os domínios monitorados da própria marca (bancodobrasil.com.br, bb.com.br) — sem ameaças reais |
- **Abas com problema**:
  - Filtro **Watchlist** exibe os domínios monitorados da marca, não ameaças em watchlist — confuso e potencialmente incorreto
  - Filtro **Immediate** mostra 0 ameaças mas não filtra a tabela de Domain Health — comportamento inconsistente
- **Nota**: 6/10

---

### ❌ Passo 6 — Lista de Matches

- **Funciona?**: **NÃO**
- **Screenshot**: `core_11_matches_list.png`, `core_11b_admin_matches.png`, `core_11c_admin_matches_filtered.png`
- **Matches visíveis**: **NÃO** — página retorna 404
- **URLs testadas**:
  - `/admin/brands/{id}/matches` → **404**
  - `/admin/matches` → **404**
  - `/admin/matches?bucket=immediate_attention` → **404**
- **Filtros disponíveis**: N/A
- **Colunas da tabela**: N/A
- **Paginação funciona?**: N/A
- **Problemas**:
  - **ROTA NÃO EXISTE** — página de matches dedicada não está implementada
  - O dashboard faz referência a esta rota no card de "Immediate Threats" — link quebrado visível na homepage
  - O usuário que ver "51 ameaças imediatas" e clicar no link vai receber uma tela de erro 404
- **Nota**: 0/10

---

### ❌ Passo 7 — Detalhe de Match

- **Funciona?**: **NÃO**
- **Screenshot**: `core_12_match_detail.png` (exibe a própria página da marca, sem navegação)
- **O que acontece**: Clicar em uma linha da tabela de threats (que tem `cursor-pointer` e `hover:bg-muted/50`) **não faz nada** — a URL permanece idêntica
- **Informações no detalhe**: N/A
- **Ações disponíveis**: N/A
- **O usuário entende por que é suspeito?**: **NÃO** — não existe tela de detalhe
- **Problemas**:
  - Rows da tabela têm estilo de elemento clicável mas sem handler de navegação funcional
  - Não há link explícito nas células (nem `<a href>` nos rows)
  - Sem tela de detalhe, o usuário não pode ver: DNS, SSL, WHOIS, score breakdown, histórico, ações (marcar como falso positivo, bloquear, etc.)
  - Este é o **fluxo mais crítico** do produto — identificar e investigar um domínio suspeito — e está completamente quebrado
- **Nota**: 0/10

---

### ✅ Passo 8 — Scroll / Exploração Vertical da Página BB

- **Conteúdo abaixo da dobra**:
  - Tabela de threats continua por ~50 linhas de domínios suspeitos
  - Ao final: seção "Brand Configuration" (sem detalhes visíveis via text) e "Cycle History (1)"
  - A página inteira tem **2.778px de altura** — o usuário precisa rolar bastante para ver tudo
- **Screenshots**: `core_13_brand_bb_bottom.png`, `core_14_brand_bb_middle.png`, `core_15_brand_bb_top_again.png`
- **Problemas**:
  - Sem paginação na tabela de threats — 50+ linhas carregadas de uma vez
  - Não há indicador visual de "há mais conteúdo abaixo" (ex: scroll indicator, sticky header)
  - "Brand Configuration" e "Cycle History" aparecem muito abaixo — usuário pode nunca encontrá-los
- **Nota**: 6/10

---

## BUGS ENCONTRADOS

### 🔴 Críticos (bloqueiam o fluxo)

| # | Descrição | Passo | Impacto |
|---|-----------|-------|---------|
| 1 | `/admin/brands/{id}/matches` retorna **404** — rota de lista de matches não existe | Passo 6 | Fluxo core interrompido |
| 2 | `/admin/matches` retorna **404** — rota global de matches não existe | Passo 6 | Link do Dashboard quebrado |
| 3 | `/admin/matches?bucket=immediate_attention` retorna **404** | Dashboard + Passo 6 | CTA da homepage leva a erro |
| 4 | Linhas da tabela de threats têm estilo de clicável (`cursor-pointer`) mas **não navegam** para nenhuma tela de detalhe | Passo 7 | Usuário não consegue investigar nenhum domínio suspeito |

### 🟡 Médios (degradam experiência)

| # | Descrição | Passo | Impacto |
|---|-----------|-------|---------|
| 5 | **Inconsistência nos dados do Monitoring Cycle**: exibe "Threats: 0, New Matches: 0" enquanto a marca tem 50 ameaças listadas | Passo 4 | Confunde operador, gera desconfiança nos dados |
| 6 | `bancodobrasil.com.br` no Domain Health mostra status "unknown" sem dados de DNS/SSL/Email/Headers/Blacklist | Passo 4 | Domínio primário da marca sem monitoramento ativo — gap de cobertura |
| 7 | Filtro **Watchlist** exibe os domínios monitorados da própria marca (não ameaças em watchlist) | Passo 5 | Comportamento confuso — usuário espera ver ameaças classificadas como watchlist |
| 8 | Coluna "Signals" na tabela de threats está vazia para todos os 50+ registros | Passo 4 | Informação de diagnóstico ausente — usuário não entende o que disparou o alerta |
| 9 | Status do scan: `pending` sem data/hora estimada de execução | Passo 4 | Operador não sabe quando terá dados atualizados |

### 🟢 Baixos (melhorias de UX)

| # | Descrição | Passo | Impacto |
|---|-----------|-------|---------|
| 10 | Sem loader/spinner visível entre submit do login e redirect | Passo 1 | UI parece "travada" por 1–2s |
| 11 | Header da lista de marcas diz "Monitoring Profiles" mas o menu usa "Monitored Brands" — inconsistência de nomenclatura | Passo 3 | Menor confusão de terminologia |
| 12 | Bradesco aparece com status "unknown" e 0 ameaças em todos os buckets — não está claro se é perfil novo ou falha | Passo 3 | Falta de estado explicativo (ex: "Scan não realizado") |
| 13 | Tabela de threats sem paginação (50+ linhas carregadas de uma vez) | Passo 8 | Performance e usabilidade em tabelas grandes |
| 14 | "Brand Configuration" e "Cycle History" ficam enterrados ao final de uma página longa | Passo 8 | Features importantes com baixa descoberta |

---

## ERROS DE CONSOLE E NETWORK

### Erros de Console (JavaScript)

```
[error] Failed to load resource: 404
  URL: https://observadordedominios.com.br/admin/matches?bucket=immediate_attention&_rsc=1yg7h
  Ocorre: ao carregar dashboard e ao clicar em links de threats

[error] Failed to load resource: 404
  URL: https://observadordedominios.com.br/admin/brands/4185de60-db89-43ca-95d6-b09b385a2db5/matches
  Ocorre: ao tentar acessar matches da marca BB
```

### Erros de Network (HTTP 4xx/5xx)

| Status | URL |
|--------|-----|
| 404 | `/admin/matches?bucket=immediate_attention&_rsc=1yg7h` |
| 404 | `/admin/brands/4185de60-db89-43ca-95d6-b09b385a2db5/matches` |
| 404 | `/admin/matches?bucket=immediate_attention` (acesso direto) |

> **Nota**: O parâmetro `_rsc=` indica que o Next.js está tentando fazer prefetch via React Server Components de uma rota que não está implementada no App Router. Isso sugere que a página **existe referenciada em algum link/componente** mas a route handler nunca foi criada.

---

## ANÁLISE DE UX: O USUÁRIO ENTENDE O PRODUTO?

### O que está BOM ✅

- **Login**: fluxo simples, direto, funcional
- **Dashboard**: dados em tempo real com boa densidade de informação — o operador vê de imediato o estado geral do sistema
- **Volume de dados**: 693M+ domínios ingeridos, 4 fontes ativas — transmite escala e credibilidade
- **Página de marca (Banco do Brasil)**: boa estrutura — header com status, stats por categoria, Domain Health, tabela de threats com filtros
- **Free Tools**: página completa e bem organizada com 11 ferramentas — excelente valor de suporte operacional
- **Ingestion Monitoring**: visibilidade em tempo real das fontes de dados
- **Design system consistente**: visual limpo, tokens de cor coerentes, uso correto de badges e tabelas

### O que está CONFUSO ⚠️

- **"Threats: 0"** no Monitoring Cycle enquanto a marca tem 50 ameaças — nenhum usuário vai entender essa diferença sem documentação
- **Filtro Watchlist** mostrando os domínios monitorados da própria marca em vez de ameaças categorizadas como watchlist
- **Status "unknown"** no Domain Health sem explicação — o usuário não sabe se é normal ou um problema
- **Linhas clicáveis que não clicam** — o hover visual engana o usuário para tentar clicar em algo que não funciona
- **"Scan: pending"** sem contexto de quando vai acontecer
- Diferença entre **"Monitored Brands"** (menu) e **"Monitoring Profiles"** (header da página)

### O que está QUEBRADO ❌

- **Toda a jornada de investigação de domínio suspeito** — não existe tela de detalhe
- **Rota `/admin/matches`** — 404 em todas as variações
- **Links no Dashboard** para ameaças imediatas levam a 404
- **Coluna "Signals"** vazia — informação de diagnóstico ausente

---

## JORNADA DO USUÁRIO — MAPA DE FRICÇÃO

```
Login       Dashboard    Lista Marcas   Página BB     Filtros     Matches    Detalhe
[8/10] ──> [7/10]  ──>  [8/10]   ──>  [6/10]   ──>  [6/10] ──>  [0/10] ──> [0/10]
  ✅           ⚠️            ✅             ⚠️            ⚠️          ❌          ❌
                          link 404                  inconsist.  404 route  não existe
```

**Ponto de ruptura total**: O usuário chega até a tabela de threats, vê 50 domínios suspeitos com scores de risco, tenta clicar em qualquer um deles... e **nada acontece**. O produto promete investigação de ameaças mas não entrega a tela de investigação.

---

## TOP 5 PROBLEMAS MAIS URGENTES

1. **🔴 Criar rota e página de detalhe de match/domínio suspeito** — sem ela o produto não tem valor de investigação. O usuário vê ameaças mas não pode agir sobre elas. A tabela de threats precisa de um handler de clique funcional que navegue para `/admin/brands/{id}/threats/{matchId}` (ou equivalente) com DNS, SSL, WHOIS, score breakdown e ações (marcar como falso positivo, adicionar ao watchlist, reportar).

2. **🔴 Implementar rota `/admin/matches` e `/admin/brands/{id}/matches`** — estas rotas estão referenciadas em componentes de navegação (Dashboard card de "Immediate Threats") e geram 404 visível. Ou implementar as pages, ou remover as referências.

3. **🟡 Corrigir inconsistência "Threats: 0" no Monitoring Cycle** — o campo exibe zero enquanto a marca tem 50 ameaças ativas. Verificar se o campo se refere a algo diferente (ex: ameaças do último ciclo de scan vs. ameaças totais) e deixar o label explícito. Se for um bug, corrigir.

4. **🟡 Popular coluna "Signals" na tabela de threats** — esta coluna é o motivo pelo qual um domínio é classificado como suspeito (similaridade lexical, TLD suspeito, padrão de registro, etc.). Sem ela, o usuário não entende POR QUÊ um domínio está na lista.

5. **🟡 Corrigir o filtro Watchlist** — exibe os domínios monitorados da própria marca em vez de ameaças classificadas como watchlist pelo operador. Isso significa que o bucket "Watchlist" ou não está funcionando como esperado, ou a lógica de query está filtrando errado.

---

## RECOMENDAÇÃO FINAL

**O produto NÃO está pronto para uso autônomo por um usuário real.**

O pipeline de descoberta (ingestão → detecção → lista de ameaças) está funcionando bem — há dados reais, volumosos e atualizados. O problema é que a etapa final — **investigar e agir sobre uma ameaça** — está completamente ausente. Um analista de segurança que abrir o Observador de Domínios vai ver a lista de 50 domínios suspeitos do Banco do Brasil, vai tentar clicar em qualquer um deles para entender a ameaça... e vai encontrar o vazio.

**Antes de qualquer beta com usuários reais, é obrigatório**:
1. Implementar a tela de detalhe do domínio/match (incluindo DNS, SSL, WHOIS, score breakdown, sinais detectados, ações)
2. Corrigir as rotas 404 referenciadas no dashboard
3. Corrigir a inconsistência de dados no Monitoring Cycle

Com essas correções, o produto atinge um nível funcional mínimo. O restante da experiência (ausência de loader no login, nomenclaturas inconsistentes, paginação) pode ser tratado em seguida sem urgência crítica.

---

## SCREENSHOTS CAPTURADAS

| Arquivo | Conteúdo |
|---------|----------|
| `core_01_login_empty.png` | Página de login vazia |
| `core_02_login_filled.png` | Login com credenciais preenchidas |
| `core_03_after_login.png` | Dashboard pós-login |
| `core_04_dashboard.png` | Dashboard completo |
| `core_05_brands_list.png` | Lista de marcas monitoradas |
| `core_06_brand_bb.png` | Página Banco do Brasil (topo) |
| `core_07_brand_tab_all.png` | Threats tab "All" (50 ameaças) |
| `core_08_brand_tab_immediate.png` | Threats tab "Immediate" (0 ameaças) |
| `core_09_brand_tab_defensive.png` | Threats tab "Defensive Gap" (50) |
| `core_10_brand_tab_watchlist.png` | Threats tab "Watchlist" (2 linhas) |
| `core_11_matches_list.png` | Página matches — **404** |
| `core_11b_admin_matches.png` | `/admin/matches` — **404** |
| `core_11c_admin_matches_filtered.png` | `/admin/matches?bucket=...` — **404** |
| `core_12_match_detail.png` | Após clicar em threat row — fica na mesma página |
| `core_13_brand_bb_bottom.png` | Página BB scrollada ao fundo |
| `core_14_brand_bb_middle.png` | Página BB no meio |
| `core_15_brand_bb_top_again.png` | Página BB volta ao topo |
| `core_16_free_tools.png` | Página Free Tools |
| `core_17_ingestion.png` | Página Ingestion Monitoring |
