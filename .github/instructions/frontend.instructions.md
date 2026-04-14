# AGENTS_FRONTEND.md
## Frontend Governance Instructions — OBS Domínios

> This file defines **mandatory frontend rules** for any Agent Code, LLM, Copilot, or automated system that generates, edits, or reviews frontend code in this repository.
>
> **These rules are non-optional.**
> If a change violates this document, it must be rejected or corrected.

## Mandatory Skill Reference

Before writing or reviewing any frontend code, **read and apply**:

- `.github/skills/web-interface-guidelines/SKILL.md` — Vercel Labs Web Interface Guidelines (interactions, animation, layout, a11y, performance, hydration, design)
- `.github/skills/nextjs-micro-ux-expert/SKILL.md` — Micro-UX patterns for Next.js
- `.github/skills/next-best-practices/SKILL.md` — Next.js App Router best practices
- `.github/skills/responsive-design-expert/SKILL.md` — Responsive layout rules

The Web Interface Guidelines skill (`web-interface-guidelines`) is the **baseline standard** for all UI work. It defines MUST/SHOULD/NEVER rules that complement and extend the project-specific governance below.

---

## 1. Core Principles

### 1.1 Mobile-First is Mandatory
- All UI components must be designed **mobile-first**
- Desktop layouts are progressive enhancements
- If a component does not work properly on mobile, it must NOT be introduced

---

### 1.2 Design System is the Single Source of Truth
- The Design System defines all visual and interaction rules
- Components not present in the Design System are considered **non-existent**
- Visual changes must be applied at the Design System level, never inside features

---

## 2. Design Tokens (STRICT RULES)

### 2.1 Token Usage
All UI styles MUST be derived from design tokens defined in:
- `globals.css`
- `tailwind.config.ts`

Forbidden:
- Hardcoded colors (e.g. `#fff`, `bg-blue-500`)
- Arbitrary spacing (e.g. `mt-[13px]`)
- Inline shadows or custom gradients

---

### 2.2 Colors
- Only semantic or contextual tokens may be used:
  - `primary`, `secondary`, `danger`, `success`, `warning`, `muted`
  - `dns`, `uptime`, `ssl`, `blacklist`, `billing`
- Hover, active, disabled states must be derived from the base token

---

### 2.3 Spacing & Layout
- Only spacing values from the official scale are allowed
- Layouts must collapse naturally on small screens
- No fixed widths unless explicitly defined by the Design System

---
## 2.4 Action & Emphasis Tokens

- High-contrast colors (pure black or pure white) are RESERVED for:
  - Primary actions (CTA)
  - Focus states
  - Selected items
  - Critical confirmations

- Neutral surfaces must NEVER use action-level contrast.

- Buttons, toggles and interactive states must use:
  - --color-action
  - --color-action-foreground

## 2.5 Border Radius Rules

- Primary interactive elements (Button, Input, Select):
  - rounded-lg or rounded-xl (default)

- Secondary UI elements (Badge, Tag):
  - rounded-md or rounded-full

- Layout containers (Card, Section):
  - rounded-xl

Mixing arbitrary radius values is forbidden.

## 2.6 Elevation & Surfaces

- Elevation must be expressed through surface color and border contrast.
- Heavy shadows are forbidden.

Defined levels:
- Surface: card + subtle border
- Elevated: popover + default border
- Overlay: background + optional blur


## 3. Components Rules

### 3.1 Mandatory States
Every interactive component MUST implement:
- Default
- Loading
- Error
- Disabled
- Empty (when applicable)

A component without these states is considered **incomplete**.

---

### 3.2 Reuse Before Creation
Before creating a new component, the agent must:
1. Check the Design System catalog
2. Attempt composition using existing components

New components are allowed ONLY if:
- No equivalent exists
- The requirement cannot be solved by composition

---

### 3.3 Visual Duplication is Forbidden
- Components with similar appearance must be the same component
- Variations must be explicit via `variant`, `size`, or `state` props
- Boolean styling props such as `isBlue`, `isBig` are forbidden

---

## 4. Responsiveness & Mobile Behavior

### 4.1 Breakpoints
Components must be validated for:
- Mobile
- Tablet
- Desktop

Responsive behavior must be explicit and predictable.

---

### 4.2 Touch & Ergonomics
- Minimum touch target: **44x44px**; visual elements <24px must expand hit area
- Mobile `<input>` font-size ≥16px to prevent iOS zoom
- NEVER disable browser zoom (`user-scalable=no`, `maximum-scale=1`)
- Use `touch-action: manipulation` to prevent double-tap zoom
- Hover-only interactions are forbidden
- Destructive actions must be visually separated
- `overscroll-behavior: contain` in modals/drawers

---

## 5. Navigation Rules

### Mobile
- Sidebar must become a drawer
- Tabs must support horizontal scroll
- Modals should become full-screen or bottom sheets

### Desktop
- Sidebar may be persistent
- Navigation must remain accessible at all times

---

## 6. Performance & UX

### 6.1 Loading Strategy
- Skeletons must be shown during loading and must **mirror final content** to avoid layout shift
- Blank screens without context are forbidden

---

### 6.2 Rendering
- Lazy loading is required for:
  - Large tables
  - Charts
  - Heavy modals
- Virtualize large lists (>50 items)
- Preload above-fold images; lazy-load the rest
- Prevent CLS (explicit image dimensions)
- Track and minimize re-renders (React DevTools / React Scan)
- Mutations (`POST`/`PATCH`/`DELETE`) should resolve in <500ms

---

### 6.3 Animations
- Animations must be subtle and fast
- Animations must not block interaction
- `prefers-reduced-motion` MUST be honored (provide reduced variant or disable)
- Reduced motion should be respected on mobile

---
## 6.4 Motion Rules

- Default transition duration: 150–200ms
- Only `opacity`, `color` and `transform` transitions allowed — NEVER animate layout props (`top`, `left`, `width`, `height`)
- NEVER use `transition: all` — list properties explicitly
- Motion must never block interaction
- Animations must be interruptible and input-driven (no autoplay)
- Use correct `transform-origin` so motion starts where it "physically" should


## 7. Accessibility (A11y)

- WCAG AA contrast minimum (prefer APCA over WCAG 2 for precision)
- Focus indicators must be visible (`:focus-visible`; never `outline: none` without replacement)
- Inputs must have visible labels; accessible names must exist even when visuals omit them
- All interactions must be keyboard accessible — full WAI-ARIA APG keyboard support
- Tooltips cannot be the only source of information
- Icon-only buttons MUST have a descriptive `aria-label`
- Decorative elements must be `aria-hidden`
- Prefer native semantics (`button`, `a`, `label`, `table`) before ARIA roles
- `aria-live="polite"` for toasts, inline validation messages
- `scroll-margin-top` on headings; include "Skip to content" link; use hierarchical `<h1>`–`<h6>`
- Redundant status cues: NEVER rely on color alone; icons must have text labels
- `font-variant-numeric: tabular-nums` for numeric comparisons
- Locale-aware dates/times/numbers via `Intl.DateTimeFormat` / `Intl.NumberFormat`
- Use `translate="no"` on brand names, code tokens, and identifiers
- Use `…` character (not `...`); non-breaking spaces where needed (`10&nbsp;MB`)
- Charts must use color-blind-friendly palettes

---

## 8. Naming & Code Organization

### 8.1 Components
- One responsibility per component
- Clear and semantic naming

---

### 8.2 Props
- Explicit props: `variant`, `size`, `state`
- Avoid ambiguous or stylistic booleans

---

## 9. Data Visualization

- Charts must use design tokens
- Critical states must use semantic colors
- Legends must be collapsible on mobile
- Important data must never be hidden

---

## 10. Error Handling

- Errors must explain what happened
- Errors must suggest a next action
- Generic messages like “Something went wrong” are forbidden

---

## 11. Feature Development Rules

### 11.1 Golden Rule
Features MUST NOT introduce new styles.
Features ONLY consume existing components.

---

### 11.2 Feature Validation Checklist
Before finalizing any change:
- Uses existing components
- Works correctly on mobile
- Uses only tokens
- Handles loading and error states
- Does not duplicate visual patterns
- Keyboard navigable (WAI-ARIA APG patterns)
- `prefers-reduced-motion` respected
- No broken layout on long/empty content
- URL reflects UI state (filters, tabs, pagination)
- All interactive elements have accessible names

---

## 12. Pull Request Governance

Every PR must explicitly answer:
1. Which existing components were reused?
2. Were new tokens introduced? Why?
3. Was mobile behavior validated?
4. Which states were handled?
5. Were any governance rules violated?

---

## 13. Design System Evolution

- Design System changes must be versioned
- Breaking changes must be documented
- No silent visual changes are allowed

---

## 16. Forms & Inputs

- Hydration-safe inputs: no lost focus/value on hydration
- NEVER block paste in `<input>`/`<textarea>`
- Loading buttons: show spinner and keep original label
- Enter submits focused input; in `<textarea>`, ⌘/Ctrl+Enter submits
- Keep submit enabled until request starts, then disable with spinner
- Accept free text and validate after — never block typing
- Errors inline next to fields; on submit, focus first error
- Set `autocomplete` + meaningful `name`; correct `type` and `inputmode`
- Disable spellcheck for emails, codes, usernames
- Warn on unsaved changes before navigation
- Compatible with password managers & 2FA; allow pasting codes
- Trim values to handle trailing spaces
- No dead zones on checkboxes/radios; label + control share one hit target
- Inputs with `value` need `onChange` (or use `defaultValue`)
- Guard date/time rendering against hydration mismatch

---

## 17. State & Navigation

- URL MUST reflect state (deep-link filters, tabs, pagination, expanded panels)
- Back/Forward must restore scroll position
- Links MUST use `<a>`/`<Link>` for navigation (support Cmd/Ctrl/middle-click)
- NEVER use `<div onClick>` for navigation

---

## 18. Content Handling

- Text containers must handle long content (`truncate`, `line-clamp-*`, `break-words`)
- Flex children need `min-w-0` to allow truncation
- Handle empty states — no broken UI for empty strings or arrays
- Design empty, sparse, dense, and error states for every list/table



> **Frontend without governance becomes invisible technical debt.**
>
> If a rule is unclear, the safest option is to NOT introduce the change.

---

## Enforcement

If any instruction in this file conflicts with generated code:
- The code must be corrected
- The instruction always takes precedence

## 15  Pagina  system-design 

deve conter todos os componentes disponiveis no design system utilizado no frontend, incluindo exemplos de uso, propriedades e variações de cada componente.

## Decision Rule for Agents

If multiple valid implementations exist:
- Choose the one with LESS visual impact
- Choose reuse over customization
- Choose consistency over novelty
