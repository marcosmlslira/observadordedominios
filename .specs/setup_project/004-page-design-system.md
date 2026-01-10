
---

## 4. Estrutura da Página (OBRIGATÓRIA)

A página deve ser **scrollável**, organizada por **seções bem delimitadas**.

---

### 4.1 Foundations (Tokens)

#### Typography
- Fonte principal
- Fonte mono
- H1, H2, H3
- Body (normal / small)
- Caption
- Code

Cada item deve exibir:
- Texto de exemplo
- Nome do token
- Classe Tailwind correspondente

---

#### Colors
- Background
- Foreground
- Primary
- Secondary
- Accent
- Muted
- Border
- Ring / Focus

Estados:
- Success
- Warning
- Danger
- Info

Contextuais (OBS):
- DNS
- Uptime
- SSL
- Blacklist
- Billing

Cada cor deve exibir:
- Swatch
- Nome do token
- Uso recomendado

---

#### Spacing
- Escala completa de espaçamento
- Exemplos visuais de padding e gap

---

#### Border Radius
- XS
- SM
- MD
- LG
- XL

---

#### Elevation
- Shadow XS
- Shadow SM
- Shadow MD
- Shadow LG

---

#### Motion
- Transition fast
- Transition base
- Transition slow
- Easing

---

## 5. Componentes (CATÁLOGO COMPLETO)

Todos os componentes devem ser implementados usando:
- shadcn/ui
- Tailwind
- Tokens definidos no projeto

❌ Nenhum estilo hardcoded é permitido.

---

### 5.1 Buttons
- Primary
- Secondary
- Outline
- Ghost
- Destructive
- Link

Estados:
- Default
- Hover
- Focus
- Active
- Disabled
- Loading

Tamanhos:
- Small
- Medium
- Large

---

### 5.2 Inputs
- Text
- Email
- Password
- Search
- URL
- Number
- Read-only

Estados:
- Default
- Focus
- Error
- Success
- Disabled

---

### 5.3 Selectors
- Checkbox
- Radio
- Switch
- Toggle Group
- Select
- Multi-select

---

### 5.4 Navigation
- Topbar
- Sidebar (desktop)
- Sidebar collapsed
- Drawer (mobile)
- Tabs
- Breadcrumb
- Pagination

---

### 5.5 Cards
- Base Card
- Metric Card
- Status Card
- Alert Card
- Billing Card

---

### 5.6 Tables
- Default
- Dense
- Sortable
- Selectable
- Filterable

Estados:
- Loading
- Empty
- Error

Versão mobile:
- Card list ou accordion

---

### 5.7 Feedback
- Alert (success, warning, error, info)
- Toast
- Banner
- Inline validation

---

### 5.8 Overlays
- Modal
- Dialog
- Drawer
- Sheet
- Popover
- Tooltip
- Dropdown Menu

---

### 5.9 Data Visualization
- Line chart
- Area chart
- Bar chart
- Donut chart
- Timeline

Regras:
- Usar apenas tokens de cor
- Estados críticos destacados semanticamente
- Legenda colapsável no mobile

---

### 5.10 States
- Skeleton (text, card, table)
- Empty state
- Error state
- No permission
- First-use state

---

### 5.11 User & Access
- Avatar
- User menu
- Role badge
- Invitation card

---

## 6. Responsividade (OBRIGATÓRIO)

Cada componente exibido deve:
- Ser validado em mobile
- Ser validado em desktop
- Colapsar corretamente

Regras:
- Mobile-first
- Alvos de toque ≥ 44x44px
- Hover nunca obrigatório

---

## 7. Governança

### 7.1 Regras obrigatórias
- Todos os componentes usam tokens
- Nenhuma cor hardcoded
- Nenhum spacing fora da escala
- Todo componente tem loading
- Todo componente tem error
- Nenhuma feature cria estilo próprio

---

### 7.2 Regra de ouro
> Se um componente não aparece na página `/design-system`, ele não existe.

---

## 8. Uso Esperado

A página `/design-system` deve ser usada para:
- Validar impacto visual de tokens
- Revisar PRs
- Criar novos componentes
- Auditar consistência
- Guiar Agent Code e LLMs

---

## 9. Não Objetivos

Esta página:
- Não deve conter lógica de negócio
- Não deve depender de backend
- Não deve ser acessível em produção

---

## 10. Critério de Aceitação

A implementação é considerada correta quando:
- Todos os tokens estão visíveis
- Todos os componentes e variações estão renderizados
- Nenhuma exceção visual é criada fora do Design System
- A página não existe fora de `localhost`

---

## Final Note

> Esta página é uma ferramenta de engenharia.
> Ela existe para evitar dívida técnica invisível no frontend.
