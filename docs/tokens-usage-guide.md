# Guia de Uso - Novos Tokens OBS Domínios

## Exemplos Práticos de Uso

### Brand Brown - Sidebar Header
```tsx
// Sidebar com marca da coruja
<div className="bg-brandBrown-900 text-white p-6">
  <h1 className="font-bold text-lg">OBS Domínios</h1>
</div>

// Divisor com marrom
<div className="h-px bg-brandBrown-700" />

// Ícone com marrom
<Icon className="text-brandBrown-500" />
```

### Brand Yellow - Focus & Alerts
```tsx
// Input com focus ring customizado
<input 
  className="border-2 border-gray-200 focus:ring-2 focus:ring-brandYellow-500 focus:ring-offset-2"
/>

// Alert/Warning com amarelo
<div className="bg-yellow-50 border-l-4 border-brandYellow-600 p-4">
  <p className="text-brandYellow-700 font-medium">Atenção necessária</p>
</div>

// Badge de alerta
<span className="bg-brandYellow-100 text-brandYellow-700 px-3 py-1 rounded">
  Aviso
</span>
```

### Gray Scale - Hierarchy
```tsx
// Hierarchy de cards
<div className="bg-white border border-gray-200">       {/* Padrão */}
  <div className="bg-gray-50 border-b border-gray-200"> {/* Subtle */}
    Header
  </div>
  <div className="p-4">Content</div>
</div>

// Texto hierarchy
<h1 className="text-gray-900 font-bold">Título Principal</h1>
<p className="text-gray-700 font-semibold">Título Secundário</p>
<p className="text-gray-600">Texto Normal</p>
<span className="text-gray-500">Texto Muted</span>

// Dark mode (automático)
<div className="dark:bg-gray-900 dark:text-gray-50">Adaptive</div>
```

### Border Levels
```tsx
// Subtle - para dividers internos
<div className="border-b border-gray-100">Seção A</div>
<div className="border-b border-gray-100">Seção B</div>

// Default - padrão para cards
<div className="border border-gray-200 rounded-lg p-4">
  Card padrão
</div>

// Strong - para outline buttons ou destaques
<button className="border-2 border-gray-400 px-4 py-2">
  Outline Button
</button>

// Com Tailwind extend (border-subtle, border-strong)
<div className="border border-subtle">Subtle</div>
<div className="border border-strong">Strong</div>
```

### States - Sober Colors
```tsx
// Success - verde escuro confiável
<div className="bg-success text-success-foreground p-3 rounded">
  ✓ Operação concluída
</div>

// Warning - amarelo-âmbar (alinha com brand-yellow)
<div className="bg-warning text-warning-foreground p-3 rounded">
  ⚠ Aviso
</div>

// Error - vermelho escuro sério
<div className="bg-error text-error-foreground p-3 rounded">
  ✗ Erro crítico
</div>

// Info - azul padrão
<div className="bg-info text-info-foreground p-3 rounded">
  ℹ Informação
</div>
```

### Focus Ring - Alta Visibilidade
```tsx
// Classe utility personalizada
<input className="focus-ring" /> {/* ring-yellow-500 */}

// Ou manual com brand-yellow
<button className="focus:ring-2 focus:ring-brandYellow-500 focus:ring-offset-2" />

// Strong variant
<input className="focus-ring-strong" /> {/* ring-brand-yellow-500 */}
```

## Dark Mode - Exemplos

```tsx
// Componente que muda com dark mode
<div className="bg-white dark:bg-gray-900 p-4">
  <h2 className="text-gray-900 dark:text-gray-50">Título</h2>
  <p className="text-gray-600 dark:text-gray-400">Descrição</p>
  <div className="border border-gray-200 dark:border-gray-300">
    Content
  </div>
</div>

// Sidebar adaptativo
<aside className="bg-sidebar text-sidebar-foreground">
  Light: branco → Dark: azul-escuro
</aside>
```

## CSS Variables - Acesso Direto

Se precisar acessar tokens diretamente em CSS:

```css
.custom-element {
  background-color: rgb(var(--brand-brown-900));
  border-color: rgb(var(--border-strong));
  color: rgb(var(--foreground));
}

/* Dark mode */
.dark .custom-element {
  background-color: rgb(var(--gray-900));
  border-color: rgb(var(--gray-300));
}
```

## Migração de Componentes Existentes

### Antes
```tsx
<button className="bg-gray-200 border border-gray-300 focus:ring-blue-500">
  Clique
</button>
```

### Depois
```tsx
<button className="bg-gray-100 border border-gray-300 focus:ring-2 focus:ring-brandYellow-500 focus:ring-offset-2 transition-all">
  Clique
</button>
```

## Verificação de Contraste

| Combinação | Light | Dark | WCAG |
|-----------|-------|------|------|
| Foreground em Background | 15,23,42 em 255,255,255 | 241,245,249 em 15,23,42 | AAA ✓ |
| Text em Card | 15,23,42 em 255,255,255 | 241,245,249 em 15,23,42 | AAA ✓ |
| Brand Brown em White | 62,39,35 em 255,255,255 | - | AA ✓ |
| Brand Yellow Focus | 245,158,11 em 255,255,255 | 250,204,21 em 15,23,42 | AAA ✓ |

## Referência Rápida - Classes Tailwind

```
Cores:
  brandBrown-{900|700|500}
  brandYellow-{700|600|500}
  gray-{50|100|200|300|400|500|600|700|800}
  border-{subtle|strong} (+ DEFAULT)
  success|warning|error|info

Utilidades:
  focus-ring
  focus-ring-strong
  border-subtle
  border-strong
```

---

**Dúvidas ou sugestões?** Consulte `design-system-update.md` para detalhes técnicos completos.
