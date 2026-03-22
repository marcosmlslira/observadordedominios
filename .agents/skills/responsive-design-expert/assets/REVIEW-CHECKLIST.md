# Responsive Review Checklist

## Architecture
- [ ] Mobile baseline exists before larger breakpoints
- [ ] Breakpoints only enhance larger layouts
- [ ] Component adaptation uses container queries when appropriate
- [ ] Responsive rules are understandable and maintainable

## Fluid sizing
- [ ] Typography scales fluidly where appropriate
- [ ] Spacing avoids abrupt breakpoint jumps where fluid scaling is better
- [ ] Widths and paddings avoid brittle fixed values

## Mobile behavior
- [ ] No accidental horizontal scroll on body
- [ ] Primary actions are reachable on mobile
- [ ] Touch targets are at least 44x44 CSS px where needed
- [ ] Safe-area handling protects sticky edges and bottom actions
- [ ] Full-height layouts use `dvh`/`svh`/`lvh` deliberately, not blindly `vh`

## Layout resilience
- [ ] Long text does not break containers
- [ ] Flex/grid children can shrink without overflow
- [ ] Grids degrade gracefully at narrow widths
- [ ] Tables have an explicit small-screen strategy
- [ ] Images and videos preserve intended ratio and fit

## Reuse
- [ ] Component works inside narrow sidebars/modals/cards
- [ ] Viewport-wide assumptions are not hard-coded into reusable components
- [ ] Layout remains correct when embedded in a smaller parent than expected
