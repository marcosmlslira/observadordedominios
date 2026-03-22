# Technical Reference

## Architecture defaults

### Server-first composition
- Server Components should own page structure, data fetching, and initial composition whenever possible.
- Client Components should be small, intentional islands for interactivity.
- Prefer passing serialized data down rather than moving whole data-fetching trees to the client.

### Suspense boundaries
Use `Suspense` when:
- a subtree can load independently
- the rest of the layout is already valuable without it
- you can show a structured fallback

Avoid one giant boundary around the full page if smaller boundaries improve continuity.

### `loading.tsx`
Use `loading.tsx` for route segment loading when navigation should feel immediate.
Fallback UI should resemble the shape and density of the final content.

## Loading strategy matrix

### Use skeletons when
- content structure is predictable
- card/list/table/form layout is known
- route or section load lasts long enough to be noticed
- preserving layout stability matters

### Use local spinners when
- the action is short
- layout is not predictable
- only one small control is waiting
- a global fallback would be too disruptive

### Use no visible loader when
- the state transition is near-instant
- the interaction already produces a clear immediate effect
- additional motion would create more noise than clarity

## Optimistic UI implementation notes

### Safe optimistic flow
1. capture user intent
2. update local UI immediately
3. mark pending subtly if necessary
4. send mutation
5. reconcile result
6. rollback or confirm

### Rollback guidance
Rollback should:
- restore prior state predictably
- explain what failed
- stay local to the affected component where possible
- avoid surprising disappearance without explanation

## Motion reference

### Cheap properties
Prefer:
- `transform`
- `opacity`

Use cautiously:
- `filter`
- animated `box-shadow`

Avoid for common microinteractions when possible:
- `width`
- `height`
- `top`
- `left`
- `margin`
- `padding`

### Motion duration guidance
- tiny microinteractions: ~120ms to 180ms
- overlays / drawers / reveals: ~180ms to 280ms
- avoid slow transitions that create mushy feedback

### Motion purpose categories
Only animate to:
- confirm input
- connect states
- guide attention
- soften abrupt change
- preserve continuity

## Visual system reference

### Radius system
Keep radius choices intentional and limited.
Example family:
- buttons / inputs: small-to-medium radius
- cards / popovers / drawers: medium-to-large radius
- chips / pills: full or highly rounded by type

### Elevation system
Use a small set of elevation levels.
Example:
- level 0: no shadow, subtle border
- level 1: low surface elevation
- level 2: hover or floating element
- level 3: popover / modal / overlay container

### Borders
Borders help premium UIs feel precise.
In many cases:
- subtle border + soft shadow > stronger shadow alone

## Accessibility reference
- Focus-visible must always be present and obvious.
- Interaction should not depend on color alone.
- Respect reduced motion preferences.
- Ensure touch targets are practical on mobile.
- Preserve semantic HTML whenever possible.

## Review prompts for the agent
When reviewing UI, ask:
- what does the user feel right after tapping this?
- does the UI acknowledge intent instantly?
- would this loading state reduce or increase anxiety?
- is any animation hiding poor responsiveness?
- is this component stable under long text and narrow widths?
- is the focus state obvious enough for keyboard users?
- does this surface feel premium because of consistency or just decoration?
