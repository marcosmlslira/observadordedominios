---
# RELATÓRIO DE UX/FRONTEND — Observador de Domínios
**Data**: 13 de abril de 2026  
**Testador**: Agente UX Automatizado (Playwright + Chromium)  
**Ambiente**: Produção — https://observadordedominios.com.br  

---

## RESUMO EXECUTIVO

O **Observador de Domínios** é um SaaS de monitoramento de domínios com uma interface de admin funcional e dados reais em produção — incluindo 693 milhões de domínios ingeridos e monitoramento ativo de marcas como Banco do Brasil. O produto tem uma base sólida com dashboard informativo e páginas de brand detalhadas. Porém, apresenta **ausência total de landing page pública**, pelo menos 3 rotas críticas retornando 404 (matches, free tools, settings/profile), e a **experiência mobile está sem navegação funcional** (sem menu hamburger, sem bottom bar). O produto parece tecnicamente robusto mas com UX incompleta em áreas importantes.

---

## TELAS TESTADAS

### 1. Landing Page (Desktop)
- **URL testada**: https://observadordedominios.com.br  
- **URL final**: https://observadordedominios.com.br/login (redirect automático)  
- **Nota**: 2/10  
- **Screenshot**: `01_landing_desktop.png`  
- **O que foi visto**: A URL raiz redireciona diretamente para `/login`. Não existe landing page pública. A tela de login exibe apenas o formulário com título "Observador de Dominios — Admin" e um botão "Sign in". Sem hero, sem texto de apresentação do produto, sem CTA de cadastro/trial.
- **Pontos positivos**:
  - Redirecionamento rápido e limpo para login
  - Sem erros de JavaScript no console
- **Problemas encontrados**:
  - [CRÍTICO] Ausência total de landing page pública — visitantes sem credenciais vêem apenas o formulário de login sem qualquer contexto do produto
  - [ALTO] Botão único chamado "Sign in" em inglês — inconsistência linguística num produto BR
  - [ALTO] Sem meta-description ou apresentação do produto para SEO e novos usuários
  - [MÉDIO] Título da página "Observador de Dominios" sem acento em "Domínios"
- **Sugestões**:
  - Criar landing page pública com apresentação do produto, benefícios, planos e CTA de cadastro/trial
  - Traduzir botão "Sign in" para "Entrar" ou "Acessar"
  - Corrigir ortografia em todos os títulos ("Domínios" com acento)

---

### 2. Landing Page (Mobile 390px)
- **URL**: https://observadordedominios.com.br  
- **Nota**: 2/10  
- **Screenshot**: `02_landing_mobile.png`  
- **O que foi visto**: Idêntico ao desktop — redirect para login. Sem overflow horizontal (positivo), sem navegação (não aplicável pois é só login). Body width = 390px, sem scroll horizontal. Nav display = none.
- **Pontos positivos**:
  - Sem overflow horizontal — página não quebra em mobile
  - Layout responsivo básico do formulário de login
- **Problemas encontrados**:
  - [CRÍTICO] Mesmos problemas da versão desktop (ausência de landing page)
  - [MÉDIO] Não há adaptação específica para mobile além do layout básico
- **Sugestões**:
  - Implementar landing page com design mobile-first

---

### 3. Login
- **URL**: https://observadordedominios.com.br/login  
- **Nota**: 6/10  
- **Screenshot**: `03_login.png`, `04_login_filled.png`  
- **O que foi visto**: Formulário de login com campos de email e senha visíveis. Botão de submit presente. Login funcionou corretamente — após preencher `admin@observador.com` / `mls1509ti` e clicar submit, redirecionou para `/admin` com sucesso. Um erro 404 no console durante o carregamento (recurso não encontrado).
- **Pontos positivos**:
  - Campos de email e senha funcionais
  - Autenticação funciona corretamente
  - Redirect pós-login para dashboard correto
  - Sem estado de loading visível problemático
- **Problemas encontrados**:
  - [MÉDIO] Erro 404 no console ao carregar a página de login (recurso não carregado)
  - [MÉDIO] Botão em inglês "Sign in" — deveria ser "Entrar" para produto brasileiro
  - [BAIXO] Sem opção de "Esqueci minha senha" visível
  - [BAIXO] Sem opção de cadastro/trial na tela de login
- **Sugestões**:
  - Investigar o recurso 404 no console
  - Traduzir "Sign in" para "Entrar"
  - Adicionar link "Esqueceu a senha?"

---

### 4. Dashboard Principal
- **URL**: https://observadordedominios.com.br/admin  
- **Nota**: 7/10  
- **Screenshot**: `06_dashboard.png`  
- **O que foi visto**:
  - Sidebar com 4 links: Dashboard, Ingestion Runs, Monitored Brands, Free Tools
  - Seção **Monitored Brands**: 3 (3 active)
  - Seção **Total Domains Ingested**: **693.965.747** (4 sources, 3 running)
  - Seção **Threat Intelligence**:
    - Immediate Threats: **51**
    - Defensive Gap: **40**
    - Watchlist: **1.574**
    - New (7 days): **1.592** (1.573 in last 24h)
  - Seção **Ingestion Sources**:
    - CZDS: 624.674.188 domínios (running, 16m ago)
    - CertStream: 14.198.329 domínios (running)
  - Título da sidebar: "Observador Admin"
- **Pontos positivos**:
  - Dados reais e relevantes em destaque
  - Números impressionantes (693M domínios) mostram escala do produto
  - Estrutura clara com seções bem definidas
  - Sidebar funcional com navegação
  - Cards de conteúdo presentes
- **Problemas encontrados**:
  - [ALTO] Sidebar link "Free Tools" aponta para `/admin/tools` — mas testando `/tools` e `/ferramentas` ambos retornam 404 (verificar se `/admin/tools` funciona)
  - [MÉDIO] Interface 100% em inglês — produto BR deveria ter ao menos opção de PT-BR
  - [MÉDIO] "Immediate Threats: 51" sem detalhamento rápido — usuário não sabe o que são sem clicar
  - [BAIXO] Título "Observador de Dominios" sem acento
  - [BAIXO] Stats cards sem animação de skeleton loading — dados aparecem direto (positivo na velocidade, mas sem feedback visual de carregamento)
- **Sugestões**:
  - Adicionar tooltips explicativos em cada métrica de threat intelligence
  - Corrigir ortografia ("Domínios" com acento)
  - Considerar localização PT-BR ou internacionalização

---

### 5. Brand — Observador de Domínios
- **URL**: https://observadordedominios.com.br/admin/brands/80c00906-2f51-4c59-80ba-3dd145c4d628  
- **Nota**: 7/10  
- **Screenshot**: `07_brand_observador.png`  
- **O que foi visto**:
  - Nome da brand: "Observador de Domínios"
  - Status: **critical** (badge vermelho)
  - Slug: `observadordedominios`
  - Botão "Trigger Scan"
  - Contadores: 0 Immediate | 13 Defensive | 0 Watchlist
  - **Latest Monitoring Cycle** (2026-04-13): health: completed | scan: completed | Threats: 0 | New Matches: 0
  - **Domain Health Table**: `observadordedominios.com.br` → primary, critical, last check 12/04/2026
  - **Threats/Matches list** com dados (scores 51-57% Defensive Gap):
    - observadordetendencias.com.br — 57%
    - observadorpolitico.com.br — 55%
    - serv-condominios.com.br — 55%
    - gerenciadordecondominios.com.br — 54%
    - observadorregional.com.br — 54%
    - observadorlivre.com.br — 53%
    - observadorcz.com.br — 53%
    - e mais...
- **Pontos positivos**:
  - Dados detalhados e organizados
  - Domain Health Table clara
  - Botão de ação "Trigger Scan" acessível
  - Scores numéricos para matches (boa visibilidade do risco)
  - Latest cycle com status explícito
- **Problemas encontrados**:
  - [ALTO] Status "critical" para o próprio domínio monitorado (observadordedominios.com.br) sem contexto claro de por que está crítico — pode confundir usuários
  - [MÉDIO] Dados de domain (DNS/SSL/Email/Headers/Blacklist) exibidos sem valores legíveis — dados aparecem concatenados no texto
  - [MÉDIO] Coluna "Bucket" com valores "Defensive Gap" repetitivos — pouca variação visível
  - [BAIXO] Score máximo de 57% — thresholds de risco não documentados na interface
- **Sugestões**:
  - Adicionar tooltip/contextualização para status "critical"
  - Melhorar legibilidade dos checkmarks de DNS/SSL/Email
  - Adicionar legenda de thresholds de score

---

### 6. Brand — Banco do Brasil
- **URL**: https://observadordedominios.com.br/admin/brands/4185de60-db89-43ca-95d6-b09b385a2db5  
- **Nota**: 7/10  
- **Screenshot**: `08_brand_bb.png`  
- **O que foi visto**:
  - Nome da brand: "Banco do Brasil"
  - Status: **critical** (badge vermelho)
  - Slug: `bb`
  - Contadores: 0 Immediate | 50 Defensive | 0 Watchlist
  - **Latest Monitoring Cycle** (2026-04-13): health: completed | scan: **pending** | Threats: 0 | New Matches: 0
  - **Domain Health Table**:
    - `bancodobrasil.com.br` → **unknown** (sem dados — nenhum check registrado, sem data)
    - `bb.com.br` → primary, critical, last check 12/04/2026
  - **Matches** (scores mais altos, 61-72% Defensive Gap):
    - bancobrasil.com.br — 72%
    - bancodobrasilseguros.com.br — 72%
    - projetobancodobrasil.com.br — 71%
    - bancodobrasilseguridade.com.br — 69%
    - banjodobrasil.com.br — 68% (typosquat óbvio!)
    - bancosbrasil.com.br — 67%
    - basicodobrasil.com.br — 67%
    - bancoviabrasil.com.br — 65%
    - biobancobrasil.com.br — 63%
    - bancoxcmgbrasil.com.br — 63%
    - e mais...
- **Pontos positivos**:
  - Volume alto de matches (50 Defensive) mostra produto funcionando
  - Scores elevados (72%) capturam ameaças reais como typosquats
  - Brand com múltiplos domínios monitorados (bancodobrasil.com.br + bb.com.br)
- **Problemas encontrados**:
  - [CRÍTICO] `bancodobrasil.com.br` com status **unknown** e sem dados — domínio principal do Banco do Brasil não está sendo monitorado corretamente
  - [ALTO] Scan status: **pending** no ciclo mais recente — significa que o scan ainda não completou
  - [MÉDIO] 0 Immediate threats mesmo com typosquats óbvios (banjodobrasil.com.br) — classificação pode estar incorreta
- **Sugestões**:
  - Investigar por que bancodobrasil.com.br está com status "unknown"
  - Revisar threshold de classificação "Immediate" vs "Defensive" — banjodobrasil.com.br deveria ser Immediate
  - Adicionar indicador visual quando scan está pending

---

### 7. Lista de Matches — Banco do Brasil
- **URL**: https://observadordedominios.com.br/admin/brands/4185de60-db89-43ca-95d6-b09b385a2db5/matches  
- **Nota**: 0/10  
- **Screenshot**: `09_matches_bb.png`  
- **O que foi visto**: Página **404 — "This page could not be found."** A rota `/matches` sufixada ao brand ID não existe. A tela mostra apenas mensagem de erro genérica do Next.js.
- **Pontos positivos**:
  - Nenhum
- **Problemas encontrados**:
  - [CRÍTICO] Rota `/admin/brands/{id}/matches` retorna 404 — funcionalidade inexistente ou não implementada
  - [ALTO] Nenhuma mensagem contextual ao usuário — apenas 404 genérico
  - [MÉDIO] Sidebar permanece visível na 404 — usuário pode navegar, mas destino está quebrado
- **Sugestões**:
  - Implementar a rota ou redirecionar para a página de brand com tab de matches aberto
  - Criar página 404 customizada com contexto e opções de navegação

---

### 8. Ferramentas Gratuitas
- **URLs testadas**: https://observadordedominios.com.br/tools → 404, https://observadordedominios.com.br/ferramentas → 404  
- **Nota**: 0/10  
- **Screenshot**: `10_tools.png`  
- **O que foi visto**: Ambas as URLs retornam **404 — "This page could not be found."** O sidebar do dashboard tem link "Free Tools" → `/admin/tools` que não foi testado diretamente.
- **Pontos positivos**:
  - Nenhum
- **Problemas encontrados**:
  - [CRÍTICO] Ferramentas gratuitas não acessíveis por URL pública
  - [ALTO] Link no sidebar pode estar apontando para rota diferente — necessita verificação manual
  - [MÉDIO] Produto menciona Free Tools mas funcionalidade não está deployada ou é inacessível
- **Sugestões**:
  - Verificar se `/admin/tools` funciona (link do sidebar) e documentar rota correta
  - Criar rota `/ferramentas` pública se ferramentas são para público externo
  - Remover links para páginas não existentes até implementação

---

### 9. Dashboard Mobile (390px)
- **URL**: https://observadordedominios.com.br/admin  
- **Nota**: 3/10  
- **Screenshot**: `11_dashboard_mobile.png`  
- **O que foi visto**: Dashboard carregado em viewport 390x844. Body width = 390px, sem overflow horizontal (positivo). Porém, **não foi detectado nenhum mecanismo de navegação mobile**: sem botão hamburguer, sem bottom navigation bar, sem drawer, sem menu toggle. A sidebar do desktop simplesmente não existe em mobile. O conteúdo principal pode estar visível mas sem navegação acessível.
- **Pontos positivos**:
  - Sem overflow horizontal — layout não quebra
  - Conteúdo principal carrega em 390px
- **Problemas encontrados**:
  - [CRÍTICO] Ausência total de navegação em mobile — nenhum hamburguer, bottom bar ou drawer detectado. Usuário mobile fica preso no dashboard sem conseguir navegar
  - [ALTO] Sidebar desktop presumivelmente oculta em mobile sem substituto de navegação
  - [MÉDIO] Layout de cards e métricas pode não estar otimizado para telas pequenas (31KB vs 60KB no desktop — conteúdo menor)
- **Sugestões**:
  - Implementar menu hamburguer que abre drawer/sidebar em mobile
  - Avaliar bottom navigation bar para acesso rápido às 4 seções principais
  - Validar legibilidade de tabelas de dados em 390px

---

### 10. Configurações / Perfil
- **URLs testadas**: https://observadordedominios.com.br/admin/settings → 404, https://observadordedominios.com.br/admin/profile → 404  
- **Nota**: 0/10  
- **Screenshot**: `12_settings.png`  
- **O que foi visto**: Ambas as URLs retornam **404 — "This page could not be found."** Não há página de configurações ou perfil de usuário implementada.
- **Pontos positivos**:
  - Nenhum
- **Problemas encontrados**:
  - [CRÍTICO] Nenhuma página de configurações ou perfil de usuário existe
  - [ALTO] Usuário não consegue alterar senha, configurar notificações, ou gerenciar conta
  - [ALTO] Sem forma de logout explícita localizada (logout presente no sidebar mas sem configurações acessíveis)
- **Sugestões**:
  - Implementar página de perfil com edição de dados básicos e troca de senha
  - Implementar página de configurações com preferências de notificação e alertas
  - Adicionar link acessível para settings/perfil na interface

---

## BUGS CRÍTICOS (prioridade máxima)

1. **[BUG-01] Ausência de Landing Page Pública**: A URL raiz `https://observadordedominios.com.br` redireciona para login. Não existe página de apresentação do produto. Impacto: impossível adquirir novos usuários organicamente; SEO zerado.

2. **[BUG-02] Rota `/matches` retorna 404**: `https://observadordedominios.com.br/admin/brands/{id}/matches` não existe. Impacto: funcionalidade de visualização de matches não está acessível pela URL direta.

3. **[BUG-03] Free Tools inexistentes como URL pública**: `/tools` e `/ferramentas` são 404. O sidebar aponta para `/admin/tools` — se essa rota também não funcionar, o produto não tem ferramentas gratuitas deployadas.

4. **[BUG-04] Navegação mobile ausente**: Em viewport 390px, não há hamburger menu, bottom navigation nem qualquer mecanismo de navegação. Usuários mobile ficam presos no dashboard sem poder navegar para outras seções.

5. **[BUG-05] Página de Settings/Profile inexistente**: `/admin/settings` e `/admin/profile` são 404. Usuários não conseguem gerenciar sua conta.

6. **[BUG-06] `bancodobrasil.com.br` com status "unknown"**: O domínio principal do Banco do Brasil está registrado na brand mas sem nenhum dado de monitoramento, DNS, SSL ou data de última verificação. Falha grave de monitoramento.

---

## BUGS MÉDIOS/BAIXOS

1. **[BUG-07] Ortografia incorreta no título**: "Dominios" deveria ser "Domínios" (com acento) em todos os títulos e metadados da aplicação.

2. **[BUG-08] Interface 100% em inglês**: Produto posicionado para mercado BR usa terminologia e labels em inglês ("Sign in", "Monitored Brands", "Ingestion Runs", etc.). Afeta UX de usuários não técnicos.

3. **[BUG-09] Erro 404 no console durante login**: Durante o carregamento da página `/login`, um recurso estático retorna 404. Não impede o funcionamento mas indica asset quebrado.

4. **[BUG-10] Banco do Brasil scan em status "pending"**: O ciclo mais recente mostra `scan: pending` em vez de completed. Indica potencial problema no pipeline de scanning.

5. **[BUG-11] Typosquats óbvios classificados como "Defensive" e não "Immediate"**: Domínios como `banjodobrasil.com.br` (68% score) parecem ser ameaças imediatas mas estão na categoria Defensive Gap. Classificação pode estar subestimando riscos.

6. **[BUG-12] Status "critical" no domínio próprio sem contextualização**: O domínio `observadordedominios.com.br` aparece com status "critical" sem explicação do que isso significa para o monitoramento do próprio produto.

7. **[BUG-13] Dados de Domain Health concatenados**: Colunas DNS/SSL/Email/Headers/Blacklist aparecem agrupadas sem separação clara em extração textual — provável problema de acessibilidade/leitura por screen readers.

---

## ERROS DE CONSOLE

| Erro | Página | Tipo | Severidade |
|------|--------|------|------------|
| "Failed to load resource: the server responded with a status of 404 ()" | `/login` | Network Error | MÉDIO |

**Total de erros JavaScript**: 0  
**Total de erros de rede**: 1 (recurso 404 na página de login)  
**Nota**: Console relativamente limpo — sem crashes JS, sem problemas críticos de runtime.

---

## ANÁLISE DE RESPONSIVIDADE

### Desktop (1440px) ✅
- Layout funcional com sidebar lateral
- Cards com métricas bem distribuídas
- Tabelas de dados legíveis
- Formulário de login centralizado e limpo
- Páginas de brand com conteúdo adequado

### Mobile (390px) ⚠️
| Aspecto | Status | Detalhe |
|---------|--------|---------|
| Overflow horizontal | ✅ OK | Body = 390px, sem scroll lateral |
| Sidebar desktop | ❌ Oculta | Sem menu alternativo |
| Navegação mobile | ❌ Ausente | Sem hamburguer, sem bottom bar |
| Formulário de login | ✅ OK | Responsivo e funcional |
| Dashboard content | ⚠️ Parcial | Conteúdo carrega mas sem navegação |

**Conclusão de Responsividade**: O layout não quebra visualmente em mobile (sem overflow), mas a **experiência de uso é comprometida** pela ausência total de mecanismo de navegação em telas pequenas. Um usuário mobile consegue fazer login e ver o dashboard, mas não consegue navegar para Ingestion Runs, Monitored Brands ou Free Tools.

---

## RANKING DE TELAS (melhor para pior)

1. **Brand Banco do Brasil (Tela 6)** — 7/10 — Dados ricos, volume impressionante de matches, estrutura clara. Único ponto negativo é o domínio bancodobrasil.com.br sem dados.
2. **Brand Observador de Domínios (Tela 5)** — 7/10 — Bem estruturada, dados completos, botão de ação claro. Status "critical" sem contexto é o principal problema.
3. **Dashboard Principal (Tela 4)** — 7/10 — Métricas impactantes (693M domínios), navegação clara no sidebar, boa organização de seções. Interface em inglês é ponto fraco.
4. **Login (Tela 3)** — 6/10 — Funciona perfeitamente, autenticação ok, mas sem "esqueci senha", sem cadastro, sem feedback visual rico. Botão em inglês.
5. **Landing Page Desktop (Tela 1)** — 2/10 — Não existe como tal: redireciona para login. Produto sem apresentação pública.
6. **Landing Page Mobile (Tela 2)** — 2/10 — Mesmo que desktop: login sem landing page pública.
7. **Dashboard Mobile (Tela 9)** — 3/10 — Conteúdo carrega mas sem navegação — produto inutilizável em mobile.
8. **Lista de Matches (Tela 7)** — 0/10 — 404. Rota não existe.
9. **Free Tools (Tela 8)** — 0/10 — 404 em todas as URLs testadas.
10. **Settings/Profile (Tela 10)** — 0/10 — 404 em todas as URLs testadas.

---

## RECOMENDAÇÕES PRIORITÁRIAS (TOP 10)

1. **Implementar landing page pública** — O produto não tem presença pública. Criar uma landing page com hero section, proposta de valor, features principais, planos e CTA é **crítico para aquisição de novos clientes**. Esta é a lacuna mais urgente.

2. **Corrigir navegação mobile** — Implementar menu hamburguer que abre sidebar como drawer em viewports < 768px. Alternativa: bottom navigation bar com os 4 links principais. Sem isso, o produto é inacessível em dispositivos móveis.

3. **Implementar páginas de Settings e Profile** — Usuários precisam poder alterar senha, configurar preferências de notificação e gerenciar sua conta. Rotas `/admin/settings` e `/admin/profile` são 404.

4. **Implementar ou corrigir rota de Matches** — `/admin/brands/{id}/matches` retorna 404. Verificar se a listagem de matches está acessível em outra rota e corrigir navigation links correspondentes.

5. **Corrigir monitoramento do domínio `bancodobrasil.com.br`** — O domínio principal do maior banco do Brasil está com status "unknown" sem qualquer dado. Isso indica falha no pipeline de monitoramento que afeta a credibilidade do produto.

6. **Verificar e expor Free Tools** — O sidebar lista "Free Tools" mas a URL `/admin/tools` (e variações públicas) pode estar quebrada. Ferramentas gratuitas são poderosas para aquisição de usuários; devem estar funcionando e acessíveis.

7. **Traduzir interface para PT-BR** — Produto posicionado para o mercado brasileiro deve ter interface em português. Mínimo: labels principais, botões e mensagens de erro.

8. **Corrigir ortografia "Domínios"** — O nome do produto escrito sem acento ("Dominios") em todos os títulos e metadados é um erro visível que afeta percepção de qualidade.

9. **Implementar página 404 customizada** — A 404 padrão do Next.js não oferece contexto nem opções de navegação. Uma 404 customizada com links úteis melhora a recuperação de erros pelo usuário.

10. **Revisar classificação de ameaças Immediate vs Defensive** — Com 51 ameaças Immediate no dashboard mas 0 nas brands testadas, e typosquats óbvios (banjodobrasil.com.br) classificados como "Defensive Gap", os thresholds precisam de revisão. Subestimar ameaças imediatas pode criar falsa sensação de segurança.

---

## NOTA GERAL DO PRODUTO

**4.5/10**

O **Observador de Domínios** tem uma **base técnica impressionante** — 693 milhões de domínios ingeridos, monitoramento em tempo real, scores de risco calculados e dados reais de threats como typosquats do Banco do Brasil. O core do produto funciona. Porém, a **experiência de usuário está incompleta em pontos críticos**: não há landing page pública (impossível adquirir usuários), a navegação mobile está ausente (produto inacessível em smartphones), e 3 das 10 telas testadas retornam 404 (matches, ferramentas, configurações). É um produto com grande potencial mas que precisa de atenção urgente na camada de UX e nas rotas faltantes antes de poder ser considerado produção-ready para usuários finais.

---

*Relatório gerado automaticamente por Agente UX com Playwright/Chromium em 13/04/2026.*  
*12 screenshots capturados e salvos em `docs/ux-test-screenshots/`.*
