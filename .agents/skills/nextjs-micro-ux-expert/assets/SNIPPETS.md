# Implementation Snippets

These are reference snippets and patterns to adapt inside the codebase.

## Pending button pattern
- Keep label visible when possible
- Add inline spinner only if needed
- Prevent duplicate action while pending
- Preserve width to avoid layout shift

## Skeleton pattern
- Match the final card or row geometry
- Use a calm shimmer or pulse only if subtle
- Preserve spacing and container height

## Optimistic list item pattern
- Insert local item immediately
- Mark item as pending if server confirmation matters
- Reconcile id/state on success
- Roll back item or field on error and explain locally

## Pressed-state pattern
- Use slight `scale-[0.98]` to `scale-[0.995]`
- Optionally reduce shadow on pressed
- Never use margin or padding changes to simulate press

## Focus-visible pattern
- Clear ring or outline with sufficient contrast
- Stronger than hover
- Present only for keyboard-relevant focus behavior when appropriate
