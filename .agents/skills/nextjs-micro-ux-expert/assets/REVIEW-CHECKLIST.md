# Front-end Micro-UX Review Checklist

Use this checklist when reviewing a screen or component.

## Architecture
- Is this a Server Component by default?
- Is client interactivity isolated to the smallest useful boundary?
- Is data fetched in the right place?

## States
- Are default, hover, active, focus-visible, disabled, loading, empty, error, and success states defined?
- Is there a pending state for mutations?
- Is optimistic behavior used only where safe?

## Perceived performance
- Does the UI react immediately to user intent?
- Is a skeleton used instead of a generic spinner where structure is known?
- Does loading preserve layout shape?

## Motion
- Are animations subtle and useful?
- Are `transform` and `opacity` preferred?
- Is reduced motion respected?

## Premium feel
- Are shadows restrained and consistent?
- Are borders, radius, spacing, and contrast coherent?
- Does the UI feel precise rather than busy?

## Resilience
- Does the layout survive long text, empty data, narrow screens, and slow responses?
- Are touch targets workable on mobile?
- Is keyboard focus obvious?
