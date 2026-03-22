# Responsive Patterns

## Pattern: Fluid type and spacing
Use fluid sizing for values that should scale continuously.

### Example
```css
:root {
  --step-0: clamp(0.95rem, 0.9rem + 0.25vw, 1.05rem);
  --step-1: clamp(1.125rem, 1rem + 0.8vw, 1.5rem);
  --space-3: clamp(0.75rem, 0.6rem + 0.5vw, 1rem);
  --space-6: clamp(1.25rem, 1rem + 1vw, 2rem);
}
```

## Pattern: Container-aware card layout
Use a container query when the card may live in multiple parent widths.

### Example
```css
.card-grid {
  container-type: inline-size;
}

.card {
  display: grid;
  gap: 0.75rem;
}

@container (min-width: 32rem) {
  .card {
    grid-template-columns: 6rem 1fr;
    align-items: start;
  }
}
```

## Pattern: Resilient auto-fit grid
```css
.collection {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 16rem), 1fr));
  gap: clamp(0.75rem, 0.5rem + 0.8vw, 1.25rem);
}
```

## Pattern: Mobile full-height shell
```css
.app-shell {
  min-height: 100dvh;
  padding-bottom: calc(1rem + env(safe-area-inset-bottom));
}
```

Use `100svh` instead when content must remain safe even with browser chrome fully visible.

## Pattern: Sticky bottom CTA with safe area
```css
.mobile-cta {
  position: sticky;
  bottom: 0;
  padding: 0.75rem 1rem calc(0.75rem + env(safe-area-inset-bottom));
  background: var(--surface);
  border-top: 1px solid var(--border);
}
```

## Pattern: Touch-safe icon button
```css
.icon-button {
  inline-size: 44px;
  block-size: 44px;
  display: inline-grid;
  place-items: center;
}
```

## Pattern: Flex child that must wrap instead of overflow
```css
.row {
  display: flex;
  gap: 0.75rem;
}

.row__content {
  min-width: 0;
}

.row__title {
  overflow-wrap: anywhere;
}
```

## Pattern: Media frame with stable ratio
```css
.media-frame {
  aspect-ratio: 16 / 9;
  overflow: clip;
}

.media-frame > img,
.media-frame > video {
  inline-size: 100%;
  block-size: 100%;
  object-fit: cover;
}
```

## Pattern: Horizontal data overflow contained locally
```css
.table-scroll {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
```

Use this when preserving tabular structure is better than collapsing into cards.
