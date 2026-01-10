# Checklist de Implementação - Componentes

Guia passo-a-passo para atualizar componentes e aproveitar os novos tokens.

## ✅ Prioridade 1 - Essencial

### [ ] Inputs (Frontend Critical Path)
**Arquivo:** `components/ui/input.tsx`

**Atualização:**
```tsx
// Antes
<input className="border border-input focus:ring-1 focus:ring-ring" />

// Depois
<input className="border border-border focus:ring-2 focus:ring-brandYellow-500 focus:ring-offset-2 transition-all" />
```

**Checklist:**
- [ ] Ring color = brandYellow-500 (light) / brandYellow-500 (dark)
- [ ] Border = border (não border-input)
- [ ] Ring offset = 2px
- [ ] Adicionar transition
- [ ] Testar em light mode
- [ ] Testar em dark mode

---

### [ ] Buttons - Outline Variant
**Arquivo:** `components/ui/button.tsx`

**Atualização:**
```tsx
// Variante outline (novo)
const outlineVariant = {
  className: "border-2 border-border-strong bg-transparent hover:bg-gray-50 dark:hover:bg-gray-900"
}

// Focus
className: "focus:ring-2 focus:ring-brandYellow-500 focus:ring-offset-2"
```

**Checklist:**
- [ ] Outline usa border-strong
- [ ] Primary outline tem border-primary
- [ ] Focus ring aplicado
- [ ] Hover backgrounds refinados
- [ ] Testar accessibility

---

### [ ] Cards (Common Component)
**Arquivo:** `components/ui/card.tsx`

**Atualização:**
```tsx
// Antes
<div className="bg-card text-card-foreground rounded-lg shadow-md">

// Depois
<div className="bg-card text-card-foreground rounded-lg shadow-sm border border-border">
```

**Checklist:**
- [ ] Adicionar border explícita
- [ ] Usar shadow-sm (não md)
- [ ] Testar em ambos temas
- [ ] Verificar contraste

---

## ✅ Prioridade 2 - UI Importante

### [ ] Select/Dropdown
**Arquivo:** `components/ui/select.tsx` ou `dropdown-menu.tsx`

```tsx
// Dropdown content
className="border border-border shadow-lg rounded-md"

// Focus: herdado do input
```

**Checklist:**
- [ ] Borda visível
- [ ] Shadow apropriado
- [ ] Items com hover state refinado
- [ ] Seta/ícone com cor apropriada

---

### [ ] Dialog/Modal
**Arquivo:** `components/ui/dialog.tsx`

```tsx
// Overlay
className="bg-black/50 dark:bg-black/60"

// Content
className="border border-border shadow-xl rounded-lg"

// Buttons dentro
className="focus:ring-2 focus:ring-brandYellow-500"
```

**Checklist:**
- [ ] Borda no modal
- [ ] Shadow bem marcado
- [ ] Overlay opacity
- [ ] Buttons com focus ring

---

### [ ] Tabs
**Arquivo:** `components/ui/tabs.tsx`

```tsx
// Active tab indicator
className="bg-brandBrown-700 dark:bg-brandBrown-500"
// OU
className="border-b-2 border-brandBrown-700"

// Inactive tabs
className="text-gray-600 dark:text-gray-400"
```

**Checklist:**
- [ ] Active indicator visível (marrom ou amarelo?)
- [ ] Texto inactive em gray apropriado
- [ ] Hover state refinado
- [ ] Border smooth transition

---

### [ ] Badge/Tags
**Arquivo:** `components/ui/badge.tsx`

```tsx
// Success badge
className="bg-success text-success-foreground"

// Warning badge
className="bg-warning text-warning-foreground" // Agora amarelo-âmbar

// Error badge
className="bg-error text-error-foreground" // Agora vermelho escuro

// Info badge
className="bg-info text-info-foreground"
```

**Checklist:**
- [ ] Usar cores de estado refinadas
- [ ] Foreground colors contrastam
- [ ] Dark mode backgrounds apropriados
- [ ] Bordas opcionais em outline variants

---

## ✅ Prioridade 3 - Complementos

### [ ] Alert Component
**Arquivo:** `components/ui/alert.tsx`

```tsx
// Success alert
className="bg-success/10 border-l-4 border-success text-success-foreground"

// Warning alert
className="bg-warning/10 border-l-4 border-warning text-warning-foreground"

// Error alert
className="bg-error/10 border-l-4 border-error text-error-foreground"

// Info alert
className="bg-info/10 border-l-4 border-info text-info-foreground"
```

**Checklist:**
- [ ] Background com opacity reduzida
- [ ] Borda esquerda marcada
- [ ] Ícone apropriado
- [ ] Contraste validado

---

### [ ] Checkbox/Radio
**Arquivo:** `components/ui/checkbox.tsx`, `radio-group.tsx`

```tsx
// Focus
className="focus:ring-2 focus:ring-brandYellow-500 focus:ring-offset-2"

// Border
className="border border-border"

// Checked
className="bg-primary border-primary"
```

**Checklist:**
- [ ] Focus ring visível
- [ ] Border não-checked visível
- [ ] Checked background
- [ ] Dark mode colors

---

### [ ] Breadcrumb
**Arquivo:** `components/ui/breadcrumb.tsx`

```tsx
// Separator
className="text-gray-400 dark:text-gray-600 mx-2"

// Link
className="text-primary hover:text-primary-foreground"

// Active
className="text-gray-900 dark:text-gray-50 font-semibold"
```

**Checklist:**
- [ ] Separadores visíveis
- [ ] Links com hover
- [ ] Current item em destaque
- [ ] Acessibilidade (aria-current)

---

### [ ] Popover/Tooltip
**Arquivo:** `components/ui/popover.tsx`, `tooltip.tsx`

```tsx
// Content
className="border border-border shadow-lg rounded-md bg-popover text-popover-foreground"

// Arrow (opcional)
className="border-t-popover border-l-transparent border-r-transparent"
```

**Checklist:**
- [ ] Borda visível
- [ ] Background apropriado
- [ ] Seta apontando corretamente
- [ ] Z-index suficiente

---

### [ ] Separator/Divider
**Arquivo:** `components/ui/separator.tsx`

```tsx
// Padrão
className="bg-border"

// Subtle (novo)
className="bg-border-subtle"

// Strong (novo)
className="bg-border-strong"
```

**Checklist:**
- [ ] Usar border colors
- [ ] Orientações horizontal/vertical
- [ ] Spacing apropriado
- [ ] Contraste em ambos temas

---

## 🎯 Prioridade 4 - Branding

### [ ] Sidebar (OBS Específico)
**Arquivo:** `components/Sidebar.tsx` (customizado)

```tsx
// Header
className="bg-brandBrown-900 text-white px-6 py-4"

// Logo/Title
className="font-bold text-xl"

// Nav items
className="hover:bg-brandBrown-700 dark:hover:bg-brandBrown-500"

// Divider
className="h-px bg-brandBrown-700 my-2"

// Sidebar background
className="bg-sidebar dark:bg-gray-900"

// Border direita
className="border-r border-border"
```

**Checklist:**
- [ ] Header com marrom
- [ ] Items com hover marrom
- [ ] Dividers marrom
- [ ] Texto legível
- [ ] Dark mode integrado

---

### [ ] OBS Context Colors
**Arquivo:** Qualquer lugar que use DNS, Uptime, SSL, etc.

```tsx
// DNS status
className="bg-dns text-dns-foreground"

// Uptime status
className="bg-uptime text-uptime-foreground"

// SSL status
className="bg-ssl text-ssl-foreground"

// Blacklist status
className="bg-blacklist text-blacklist-foreground"

// Billing status
className="bg-billing text-billing-foreground" // Agora amarelo
```

**Checklist:**
- [ ] Cores contextuais aplicadas
- [ ] Contraste em ambos temas
- [ ] Ícones com cores apropriadas
- [ ] Status badges claros

---

## 📋 Validação Final

### [ ] Contraste de Acessibilidade
- [ ] Texto em backgrounds passa WCAG AA/AAA
- [ ] Focus indicators visíveis
- [ ] Cores não são único diferenciador

### [ ] Compatibilidade Dark Mode
- [ ] Todos componentes têm dark:* classes
- [ ] Bordas visíveis em dark
- [ ] Texto legível em dark

### [ ] shadcn/ui Compatibility
- [ ] Nenhum componente shadcn foi quebrado
- [ ] Estyles sobrescrevem corretamente
- [ ] Variantes funcionam como esperado

### [ ] Performance
- [ ] Nenhuma classe CSS extra desnecessária
- [ ] Variables CSS sem valores hardcoded
- [ ] Tailwind purge otimizado

---

## 🔧 Utilitários Tailwind Novos

### Classes Disponíveis para Usar

```tsx
// Border utilities
className="border-subtle"        // border-color: rgb(var(--border-subtle))
className="border-strong"        // border-color: rgb(var(--border-strong))

// Focus utilities
className="focus-ring"           // ring-2 ring-offset-2 ring-yellow-500
className="focus-ring-strong"    // ring-2 ring-offset-2 ring-brand-yellow-500

// Color tokens
className="bg-brandBrown-900"
className="bg-brandYellow-500"
className="bg-gray-200"
className="text-gray-700 dark:text-gray-300"
className="border-border"
className="border-border-subtle"
className="border-border-strong"
```

---

## 📝 Template para PR

Ao enviar atualizações de componentes:

```markdown
## Descrição
Atualiza [COMPONENTE] para usar novos tokens de design system v2.

## Mudanças
- [ ] Focusring ajustado para brandYellow
- [ ] Bordas refinadas (subtle/default/strong)
- [ ] Dark mode melhorado
- [ ] Gray scale aplicada

## Testes
- [ ] Visual em light mode
- [ ] Visual em dark mode
- [ ] Contraste WCAG verificado
- [ ] shadcn/ui compatível
- [ ] Responsive testado

## Tokens Utilizados
- [ ] border-border
- [ ] brandYellow-500
- [ ] gray-{50..800}
```

---

## 🎬 Roadmap Sugerido

### Sprint 1 (Semana 1)
- [x] Design System v2 implementado
- [ ] Inputs atualizados
- [ ] Buttons outline adicionados
- [ ] Cards com borda

### Sprint 2 (Semana 2)
- [ ] Dialogs/Modals
- [ ] Selects/Dropdowns
- [ ] Sidebar branding
- [ ] Alert components

### Sprint 3 (Semana 3)
- [ ] Complementos (Badges, Tabs, etc)
- [ ] OBS Context colors
- [ ] Documentação de componentes
- [ ] QA e testes

### Sprint 4 (Semana 4)
- [ ] Otimizações finais
- [ ] Dark mode polish
- [ ] Accessibility audit
- [ ] Deploy

---

**Use este checklist como guia vivo - atualize conforme implementar!** 📝

---

*Última atualização: Janeiro 2026*
*Design System v2.0 - Implementação em Progresso*
