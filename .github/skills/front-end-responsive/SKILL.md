---
name: frontend-responsive-nextjs
description: >
  Especialista em frontend com Next.js e Tailwind CSS para criar, revisar e refatorar
  interfaces altamente responsivas, resilientes a redimensionamento e consistentes
  entre mobile, tablet e desktop. Use quando precisar implementar layouts fluidos,
  corrigir quebras visuais, melhorar microinterações, elevar percepção de qualidade,
  estruturar design system, otimizar acessibilidade e transformar requisitos de produto
  em interfaces robustas, escaláveis e visualmente premium.
compatibility: >
  Ideal para agent code em projetos web com Next.js, React, TypeScript, Tailwind CSS,
  shadcn/ui e design systems baseados em tokens. Requer acesso ao código do projeto.
metadata:
  author: Marcos Lira da Silva
  product-context: Shalem
  focus: extreme-responsiveness-and-resilient-ui
  stack: nextjs-react-tailwind-typescript
---

# Frontend Responsive Next.js

## Overview

Esta skill transforma requisitos de produto em interfaces robustas, elegantes e resilientes,
com foco em:

- responsividade extrema
- resistência a conteúdo dinâmico e redimensionamento
- clareza visual e percepção de valor
- consistência entre estados interativos
- acessibilidade e performance percebida
- implementação pragmática em Next.js + Tailwind CSS

Ela deve ser usada principalmente em contextos em que a interface precisa parecer premium,
confiável e estável mesmo diante de textos longos, números grandes, listas variáveis,
cards heterogêneos, filtros, gráficos e mudanças de viewport.

## Product Context: Shalem

Ao atuar no contexto do **Shalem**, preserve a proposta central do produto:

- O produto é uma ferramenta de **análise e leitura de gastos em cartão de crédito**.
- Ele entrega **clareza financeira**, e não execução financeira.
- Seu papel é consolidar múltiplas faturas e revelar **compromissos futuros, parcelamentos,
  recorrências e consumo digital**.
- O foco está em **entendimento, consciência e decisão**, não em automação bancária,
  aconselhamento financeiro ou controle orçamentário tradicional.

Toda decisão de interface deve reforçar estes objetivos:

1. Dar clareza total sobre o comprometimento do cartão.
2. Mostrar a evolução dos parcelamentos e da condição de custos.
3. Tornar visível o consumo recorrente e digital.

### Persona prioritária

A persona principal é o **Acumulador Invisível**:

- usa 2 ou mais cartões
- sente aperto recorrente
- paga em dia, mas não entende bem a composição da fatura
- quer clareza sem precisar virar especialista em finanças

### Regra de decisão de produto

Antes de propor qualquer solução visual, pergunte:

**Isso ajuda o Acumulador Invisível a entender melhor seu cartão?**

Se não ajudar, simplifique, remova ou reoriente a proposta.

## When to Use

Ative esta skill quando a tarefa envolver um ou mais destes cenários:

- criar telas em Next.js com Tailwind CSS
- corrigir problemas de responsividade em mobile, tablet ou desktop
- evitar overflow, quebra de layout ou desalinhamento com dados reais
- reorganizar dashboards, cards, tabelas, filtros ou navegação
- melhorar microinterações e sensação tátil da interface
- revisar UX visual para aumentar percepção de qualidade
- padronizar componentes com design system e tokens
- adaptar uma interface para diferentes densidades de conteúdo
- revisar acessibilidade, foco, contraste, estados e navegação por teclado
- transformar um briefing de produto em instruções claras para implementação frontend

## Core Principles

### 1. Mobile-first de verdade

Projete a interface primeiro para a menor largura relevante.
Não trate mobile como adaptação tardia.
Comece com a hierarquia essencial e expanda progressivamente.

### 2. Layouts fluidos, nunca rígidos

Evite depender de larguras fixas.
Prefira:

- `w-full`
- `min-w-0`
- `max-w-*`
- `flex-wrap`
- `grid` com colunas responsivas
- `clamp()` quando fizer sentido
- containers com limites explícitos

### 3. Resiliência a conteúdo real

Todo componente deve sobreviver a:

- títulos longos
- números grandes
- labels inesperados
- ausência de dados
- listas vazias
- múltiplos badges
- variação de idioma
- densidade alta de informação

### 4. Hierarquia antes de decoração

O usuário deve entender:

- o que é principal
- o que mudou
- o que exige atenção
- o que é detalhe complementar

A interface do Shalem deve comunicar leitura analítica e clareza, não poluição visual.

### 5. Estados claros e previsíveis

Cada componente precisa contemplar:

- default
- hover
- active
- focus-visible
- disabled
- loading
- empty
- error
- success quando aplicável

### 6. Percepção de performance importa

Sempre que houver carregamento, a experiência deve parecer estável e intencional.
Prefira skeletons com layout semelhante ao conteúdo final antes de spinners genéricos.

### 7. Acessibilidade é requisito, não acabamento

A interface deve funcionar com teclado, leitores de tela e contraste adequado.

## Non-Negotiable Frontend Rules

### Responsividade

- Nunca entregue um layout sem comportamento definido para mobile, tablet e desktop.
- Nunca suponha que um card ficará bonito com dados curtos se ele quebra com dados reais.
- Nunca use texto como elemento puramente decorativo quando ele pode crescer.
- Nunca deixe ações essenciais inacessíveis em telas pequenas.
- Nunca dependa apenas de hover para revelar informação importante.

### Estrutura

- Use grid para organização macro e flex para alinhamento micro.
- Use `min-w-0` em filhos de flex/grid que contêm texto truncável.
- Em dashboards, prefira blocos com alinhamento consistente, alturas previsíveis e boa distribuição de peso visual.
- Em listas e tabelas, trate overflow horizontal explicitamente.

### Tailwind

- Use tokens semânticos do projeto sempre que existirem.
- Evite classes arbitrárias em excesso quando um padrão reutilizável pode virar componente.
- Prefira composições legíveis a longas cadeias desorganizadas.
- Extraia variantes com `cva`, utilitários internos ou componentes quando houver repetição.

### Next.js

- Use Server Components por padrão quando apropriado.
- Só use Client Components quando houver interatividade real.
- Preserve separação entre UI, lógica de dados e estado local.
- Evite inflar a camada cliente sem necessidade.

## Workflow

### Step 1: Understand the real UX goal

Antes de codar, identifique:

- qual decisão o usuário precisa tomar na tela
- qual informação é primária
- qual informação é secundária
- qual é a ação principal
- o que muda entre mobile e desktop
- qual é o pior caso de conteúdo

No contexto do Shalem, priorize leitura de comprometimento, evolução e consumo recorrente.

### Step 2: Model the content stress cases

Teste mentalmente ou na implementação:

- números monetários longos
- percentuais com sinal
- cards com 1, 2 ou 8 itens relacionados
- labels extensos
- ausência de imagem/ícone
- filtros demais na mesma linha
- gráficos com pouco ou muito dado
- conteúdo truncado em telas estreitas

### Step 3: Define responsive behavior explicitly

Para cada bloco, determine:

- o que empilha no mobile
- o que vira 2 colunas no tablet
- o que expande no desktop
- o que deve truncar
- o que deve quebrar linha
- o que pode virar accordion, drawer ou sheet
- o que precisa de scroll horizontal controlado

### Step 4: Implement with durable primitives

Prefira padrões como:

- `grid-cols-1 md:grid-cols-2 xl:grid-cols-4`
- `flex flex-col gap-*`
- `flex flex-wrap items-center`
- `overflow-hidden`
- `truncate`
- `line-clamp-*`
- `aspect-*` quando útil
- `sticky` para filtros ou resumos importantes

### Step 5: Add interaction polish

Toda interface deve ter feedback visual sutil e confiável:

- hover com mudança pequena e elegante
- active com sensação de pressão/resposta
- focus-visible bem marcado
- transições curtas, discretas e consistentes
- loading coerente com o shape do conteúdo

### Step 6: Validate before concluding

Revise:

- mobile pequeno
- laptop comum
- widescreen
- zoom do navegador
- conteúdo realista
- navegação por teclado
- contraste visual

## Design Decisions for Shalem

### Linguagem visual desejada

A interface deve transmitir:

- clareza
- confiança
- leitura analítica
- leve sofisticação
- calma visual

Evite:

- excesso de ornamento
- cards visualmente pesados sem hierarquia
- grids muito densos sem respiro
- múltiplas cores competindo entre si
- elementos chamativos sem função

### Como apresentar informação financeira

Ao lidar com métricas, cards e gráficos:

- o valor principal deve ter protagonismo imediato
- comparações temporais devem ser visíveis, mas secundárias ao valor principal
- texto de apoio deve explicar o contexto sem repetir o óbvio
- agrupamentos devem reduzir carga cognitiva
- mudanças de status devem ser claras e discretas

### Parcelamentos e recorrências

Ao representar parcelamentos, assinaturas e gastos recorrentes:

- destaque começo, duração, status e impacto futuro
- use segmentação visual clara entre ativo, sugestão e encerrado
- evidencie tendência sem depender apenas de cor
- preserve leitura rápida do total e leitura progressiva do detalhe

## Component Guidance

### Cards

Um bom card deve:

- funcionar bem com pouco ou muito conteúdo
- ter padding consistente
- ter alinhamento interno previsível
- ter contraste suficiente entre título, valor, apoio e detalhe
- evitar concentração de peso visual em apenas um lado

Use padrões como:

- cabeçalho curto
- valor principal
- metadados ou contexto
- visual auxiliar opcional, como sparkline ou badge

### Tables

- Não presuma largura infinita.
- Em mobile, considere transformação para cards ou linhas expansíveis.
- Preserve cabeçalhos compreensíveis.
- Defina truncamento e tooltips apenas quando necessário.

### Filters and controls

- Em mobile, prefira sheet, drawer, scroll horizontal ou quebra em múltiplas linhas.
- Ação principal deve continuar acessível sem poluir a área superior.
- Sempre prever estado selecionado, hover, focus e disabled.

### Dialogs / drawers / sheets

- Use dialog para tarefas focadas.
- Use drawer ou sheet em mobile quando a interação precisar preservar contexto.
- Não esconda conteúdo essencial atrás de interações complexas.

### Charts

- O gráfico nunca deve existir sozinho: precisa de contexto textual.
- Valores principais devem existir fora do gráfico também.
- Legendas e eixos só entram quando ajudam de verdade.
- Em telas pequenas, reduza ruído e preserve insight principal.

## Microinteractions and Feedback

### Hover

Hover deve indicar possibilidade de ação, não criar distração.
Use mudanças sutis de:

- elevação
- borda
- fundo
- opacidade
- escala mínima

### Active / pressed

Ao clicar ou tocar, a interface deve responder de forma imediata.
Use sensação de compressão leve, sem exagero.

### Focus-visible

Todo elemento interativo navegável por teclado deve ter foco altamente visível,
consistente e acessível.

### Loading

Prefira:

- skeleton estrutural quando o layout é conhecido
- spinner apenas para ações pontuais e curtas
- estados parciais quando só parte da tela depende do carregamento

### Empty states

Estados vazios devem:

- explicar o que está acontecendo
- manter a dignidade visual da tela
- orientar próxima ação quando houver
- não parecer erro ou quebra

## Accessibility Checklist

- [ ] Contraste suficiente entre texto e fundo
- [ ] Navegação por teclado funcional
- [ ] `focus-visible` claro
- [ ] Elementos clicáveis com área adequada
- [ ] Ícones com rótulo quando necessário
- [ ] Estrutura semântica correta
- [ ] Feedback não dependente apenas de cor
- [ ] Estados de erro com mensagem compreensível
- [ ] Tabelas e gráficos com apoio textual quando necessário

## Implementation Rules for Agent Code

Quando receber uma tarefa, siga esta ordem:

1. Entenda o objetivo de negócio e o objetivo da tela.
2. Identifique a persona e a decisão principal do usuário.
3. Desenhe a hierarquia de informação.
4. Defina explicitamente o comportamento responsivo.
5. Escolha a estrutura correta entre grid, flex, stack, accordion, tabs, drawer ou sheet.
6. Implemente com componentes reutilizáveis e tokens consistentes.
7. Trate loading, empty, error e overflow.
8. Revise acessibilidade e microinterações.
9. Entregue explicando brevemente as decisões tomadas.

## Expected Output Format

Sempre que possível, entregue a resposta nesta estrutura:

### 1. Objective

Explique em 1 a 3 frases qual problema da interface está sendo resolvido.

### 2. UX Rationale

Explique:

- o que foi priorizado
- como a responsividade foi tratada
- como a solução evita quebra com conteúdo real

### 3. Implementation

Forneça o código ou instruções de alteração com contexto suficiente para aplicação.

### 4. Validation Notes

Inclua uma checagem final breve sobre:

- mobile
- tablet
- desktop
- estados vazios/loading
- acessibilidade

## Preferred Technical Patterns

### Good patterns

- componentes pequenos e compostos
- variantes semânticas
- tokens de spacing, radius, shadow e color
- `container` + `max-w-*` com respiro lateral adequado
- grids autoajustáveis
- uso criterioso de `sticky`, `overflow-x-auto`, `line-clamp`, `truncate`
- skeletons com shape realista
- separação de componentes de visualização e composição de tela

### Avoid by default

- larguras fixas frágeis
- heights rígidos sem necessidade
- textos absolutos em posições frágeis
- dependência excessiva de `absolute`
- excesso de `!important` ou arbitrariedade visual
- animações longas ou chamativas demais
- tabs em excesso em mobile quando accordion ou seções empilhadas resolvem melhor

## Example Triggers

### Example 1

**Input:**
"Preciso melhorar a responsividade dessa dashboard em Next.js porque os cards quebram no tablet."

**Expected behavior:**
- revisar hierarquia dos cards
- redistribuir grid por breakpoint
- garantir `min-w-0`, wrap e alinhamento interno
- ajustar conteúdo para números longos
- validar loading e empty state

### Example 2

**Input:**
"Crie uma tela premium para mostrar gastos recorrentes com Tailwind CSS."

**Expected behavior:**
- propor layout com leitura clara de total, tendência e agrupamentos
- priorizar clareza sobre ornamentação
- prever mobile-first
- criar estados interativos elegantes
- reforçar comparação temporal e entendimento rápido

### Example 3

**Input:**
"Esse componente parece bonito, mas quebra quando o título vem grande."

**Expected behavior:**
- tratar resiliência a conteúdo real
- revisar truncamento, wrap, line clamp ou reorganização estrutural
- remover dependência de alturas frágeis
- validar com cenários extremos

## Notes

- Em caso de conflito, priorize clareza, legibilidade e robustez.
- Em caso de dúvida entre duas soluções, escolha a que degrada melhor em telas menores.
- Em interfaces do Shalem, evite decisões que façam o produto parecer banco, planilha ou app genérico de orçamento.
- A melhor solução não é a mais chamativa; é a que continua clara mesmo sob estresse real de conteúdo.
