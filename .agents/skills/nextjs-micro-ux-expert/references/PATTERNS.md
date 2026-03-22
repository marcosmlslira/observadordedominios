# Interaction Patterns

## Buttons

### Recommended states
- default
- hover
- active / pressed
- focus-visible
- disabled
- pending

### Behavior notes
- Hover: slight surface lift or contrast increase
- Pressed: tiny `scale()` reduction and/or reduced shadow
- Pending: lock repeat submissions, keep label readable when possible
- Focus-visible: stronger than hover, clearly separated from default

## Forms

### Principles
- Validate as close to user intent as possible
- Distinguish helper text from error text
- Keep error recovery local and obvious
- Preserve input values across recoverable failures

### Submission behavior
- Disable or protect duplicate submissions when needed
- Prefer inline pending feedback over blocking the whole form
- Confirm success near the action origin unless a route change naturally confirms it

## Lists and tables

### Loading
- Use row or card skeletons matching final density
- Avoid collapsing containers while fetching

### Mutations
- For low-risk edits, consider optimistic item-level updates
- Show item-local failure states instead of only global notifications

## Drawers and modals
- Open with short fade + translate or scale
- Background dim should be subtle, not theatrical
- Initial focus and keyboard escape behavior must be handled
- Avoid long entry animations that delay interaction

## Navigation
- Route transitions should preserve shell continuity
- Use segment-level loading where possible
- Avoid blank flashes between pages

## Empty states
- Explain what is missing
- Offer next action if relevant
- Keep visual weight lower than full-content states

## Error states
- Be specific
- Keep errors contextual
- Provide recovery path when possible
- Avoid turning transient local failures into unnecessarily dramatic global alerts
