# Technical Reference

## Mobile-first architecture

### Baseline rule
- Start with the smallest practical viewport.
- Base CSS must fully support narrow screens first.
- Add complexity only as available space increases.

### Breakpoint philosophy
Use media queries primarily for:
- page shell changes
- navigation mode changes
- macro layout shifts
- large viewport-specific density changes

Do not use media queries as the default way to make components reusable.

## Fluid sizing reference

### Prefer fluid functions
Use:
- `clamp(min, preferred, max)` for type, spacing, gaps, heights, widths
- `min()` to cap runaway values
- `max()` to enforce usable minimums

### Good candidates for fluid scaling
- headings
- body size in content-heavy views
- section spacing
- card padding
- button height
- grid gaps
- wrapper widths

### Avoid rigid jumps when
- values can scale smoothly
- breakpoint-only changes would cause obvious visual jumps
- the component needs to feel continuous across widths

## Container query reference

### Use container queries when
- a component can appear in different parent widths
- the same component may be rendered in main content, sidebars, drawers, modals, or cards
- viewport width alone is a poor predictor of available component space

### Typical setup
- assign a wrapper as a container
- use `container-type: inline-size`
- scope local adaptations with `@container`

### Use media queries when
- the entire page shell changes
- navigation behavior changes at a viewport threshold
- global density or layout rules depend on full-screen context

## Viewport unit reference

### `svh`
Small viewport height.
Use when content must fit the smallest visible viewport even when browser chrome is fully visible.

### `dvh`
Dynamic viewport height.
Use when the layout should follow browser chrome expanding and collapsing.

### `lvh`
Large viewport height.
Use when you intentionally target the largest possible viewport area after browser chrome retracts.

### Practical guidance
- avoid defaulting to `100vh` for mobile full-height surfaces
- prefer `min-height: 100dvh` for app-shell style screens
- consider combining safe-area padding with viewport units for sticky edges

## Safe-area reference

### Typical surfaces requiring safe-area awareness
- sticky top bars
- sticky bottom actions
- bottom navigation
- bottom sheets
- full-screen onboarding
- immersive drawers and overlays

### Guidance
- pad the interactive container, not just the visual background
- ensure bottom CTA groups clear the home indicator area
- validate both portrait and landscape behavior

## Touch ergonomics reference

### Target size
Use a practical target size floor of **44x44 CSS px** for touch interactions unless a strict exception applies.

### Ergonomic guidance
- repeated actions should be easy to reach
- icon buttons need padded hit regions
- adjacent controls need spacing to avoid mistaps
- destructive actions need separation and clarity

## Layout resilience reference

### Grid patterns
Useful patterns:
- `repeat(auto-fit, minmax(16rem, 1fr))`
- `repeat(auto-fill, minmax(14rem, 1fr))`

Use `auto-fit` when empty tracks should collapse.
Use `auto-fill` when track reservation is desirable.

### Flex patterns
- use `flex-wrap` when items may wrap naturally
- use `min-width: 0` on shrinking children when text should wrap instead of overflow
- avoid inflexible sibling combinations that force overflow

## Media resilience reference

### Images and video
- `max-inline-size: 100%`
- `block-size: auto`
- `aspect-ratio` for reserved frames
- `object-fit: cover` for frame-filling media
- `object-fit: contain` when the full asset must remain visible

### Avoid
- fixed media heights without aspect planning
- stretching media to arbitrary dimensions
- uncapped media inside flexible containers

## Overflow management reference

### Common fixes
- `min-width: 0` on flex/grid children
- `overflow-wrap: anywhere` for hostile text
- local scroll containers for tables and code
- avoid `100vw` in padded page wrappers
- audit absolutely positioned decoration for bleed

### Long-content strategy
Pick intentionally between:
- wrap
- truncate
- clamp
- scroll
- restructure

Do not let the browser choose a broken default.

## Review prompts for the agent
When reviewing a responsive UI, ask:
- does this component work at 320px width without emergency overrides?
- should this behavior depend on viewport width or parent width?
- does any child need `min-width: 0` to avoid overflow?
- will this full-height screen break when mobile browser chrome appears?
- does safe-area padding protect critical controls?
- can a thumb comfortably reach the main repeated action?
- what happens with a 3x longer localized string?
- does this grid degrade gracefully when one card is much taller than the others?
