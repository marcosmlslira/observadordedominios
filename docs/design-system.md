# Design System - OBS Domínios

> Catálogo completo de componentes, tokens e padrões visuais

## 📍 Localização

**URL:** `http://localhost:3000/design-system`

⚠️ **Esta página está disponível apenas em ambiente de desenvolvimento**

---

## 🎯 Objetivo

A página de Design System serve como fonte única de verdade para todos os componentes visuais e tokens de design utilizados no frontend do OBS Domínios.

### Casos de Uso

1. **Desenvolvimento de Features**: Consultar componentes disponíveis antes de criar novos
2. **Revisão de PRs**: Validar que apenas componentes existentes foram utilizados
3. **Auditorias de Consistência**: Verificar se todas as features seguem o Design System
4. **Guia para Agents/LLMs**: Definir o que existe e o que pode ser usado

---

## 📐 Estrutura

### 1. Foundations (Tokens)

#### Typography
- Hierarquia completa (H1 a Caption)
- Fonte principal: Inter
- Fonte mono para código
- Classes Tailwind correspondentes

#### Colors
- **Semânticas**: Primary, Secondary, Muted
- **Estados**: Success, Warning, Error, Info
- **Contextuais (OBS Domínios)**:
  - `dns`: Monitoramento de DNS
  - `uptime`: Status de disponibilidade
  - `ssl`: Certificados SSL/TLS
  - `blacklist`: Status de blacklist
  - `billing`: Faturamento e pagamentos

#### Spacing
Escala oficial de espaçamento (2px a 64px)

#### Border Radius
De `none` a `full` (9999px)

#### Elevation (Shadows)
4 níveis: sm, md, lg, xl

#### Motion
3 velocidades: fast (75ms), base (150ms), slow (300ms)

---

### 2. Components

Catálogo completo de componentes reutilizáveis com todas as variações e estados.

#### Buttons
- **Variants**: default, secondary, outline, ghost, destructive, link
- **Sizes**: sm, default, lg, icon
- **States**: default, disabled, loading

#### Inputs
- Text, Email, Password, Search, URL, Number
- **States**: default, focus, error, success, disabled, read-only

#### Selectors
- Checkbox, Radio, Switch, Toggle Group, Select, Multi-select

#### Navigation
- Topbar, Sidebar, Tabs, Breadcrumb, Pagination

#### Cards
- Base, Metric, Status, Alert, Billing

#### Tables
- Default, Dense, Sortable, Selectable, Filterable
- **States**: loading, empty, error
- Versão mobile: Card list/accordion

#### Feedback
- Alert (success, warning, error, info)
- Toast, Banner, Inline validation

#### Overlays
- Modal, Dialog, Drawer, Sheet, Popover, Tooltip, Dropdown Menu

#### Data Visualization
- Line chart, Area chart, Bar chart, Donut chart, Timeline

#### States
- Skeleton (text, card, table)
- Empty state
- Error state
- No permission
- First-use state

#### User & Access
- Avatar, User menu, Role badge, Invitation card

---

## ✅ Regras de Governança

### Regra de Ouro
> **Se um componente não aparece na página `/design-system`, ele não existe.**

### Obrigatórias

1. ✅ Todos os componentes usam tokens
2. ❌ Nenhuma cor hardcoded
3. ❌ Nenhum spacing fora da escala
4. ✅ Todo componente tem estado de loading
5. ✅ Todo componente tem estado de error
6. ❌ Nenhuma feature cria estilo próprio

### Mobile-First

- Todos os componentes são mobile-first
- Alvos de toque ≥ 44x44px
- Hover nunca obrigatório
- Componentes colapsam naturalmente

---

## 🚀 Como Usar

### Para Desenvolvedores

1. Acesse `http://localhost:3000/design-system`
2. Navegue pelas seções de Foundations e Components
3. Copie os exemplos de código
4. Use apenas os componentes documentados

### Para Agents/LLMs

Antes de criar ou modificar código frontend:
1. Consulte esta página para verificar componentes existentes
2. Use apenas tokens e componentes documentados
3. Não crie componentes duplicados
4. Não introduza estilos hardcoded

---

## 📦 Componentes Shadcn/ui

Os seguintes componentes shadcn/ui estão disponíveis:

- `@/components/ui/button`
- `@/components/ui/input`
- `@/components/ui/checkbox`
- `@/components/ui/switch`
- `@/components/ui/badge`
- `@/components/ui/card`
- `@/components/ui/alert`
- `@/components/ui/skeleton`
- `@/components/ui/tabs`

---

## 🎨 Design Tokens

### Acessando Tokens

```tsx
// Colors
className="bg-primary text-primary-foreground"
className="bg-dns text-dns-foreground"

// Spacing
className="p-4 gap-6"

// Typography
className="text-2xl font-semibold"

// Border Radius
className="rounded-lg"

// Shadows
className="shadow-md"

// Transitions
className="transition-all duration-150"
```

---

## 🔍 Validação

### Checklist para PRs

Antes de abrir um PR:

- [ ] Usei apenas componentes existentes
- [ ] Usei apenas tokens de cores
- [ ] Usei apenas espaçamentos da escala
- [ ] Validei comportamento mobile
- [ ] Implementei estados de loading e error
- [ ] Não dupliquei padrões visuais

---

## 📝 Contribuindo

Para adicionar um novo componente ao Design System:

1. Implemente o componente em `/components/ui/`
2. Adicione o componente à página `/design-system`
3. Documente todas as variações e estados
4. Valide comportamento mobile
5. Atualize este README

---

## ⚠️ Notas Importantes

- Esta página não deve conter lógica de negócio
- Esta página não deve depender do backend
- Esta página não deve ser acessível em produção
- Alterações no Design System devem ser versionadas

---

## 📚 Referências

- [Shadcn/ui Documentation](https://ui.shadcn.com/)
- [Tailwind CSS](https://tailwindcss.com/)
- [Radix UI](https://www.radix-ui.com/)
- [Frontend Governance Instructions](../.github/instructions/frontend.instructions.md)
