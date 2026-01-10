"use client"

import * as React from "react"
import * as SwitchPrimitives from "@radix-ui/react-switch"

import { cn } from "@/lib/utils"

const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitives.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitives.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitives.Root
    className={cn(
      "peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full border-2 border-(--color-border) bg-(--color-muted) transition-colors focus-visible:outline-none focus-visible:border-(--color-action) focus-visible:ring-2 focus-visible:ring-(--color-ring) focus-visible:ring-offset-2 focus-visible:ring-offset-(--color-background) disabled:cursor-not-allowed disabled:bg-(--color-muted) disabled:border-(--color-border-subtle) data-[state=checked]:bg-(--color-action) data-[state=checked]:border-(--color-action)",
      className
    )}
    {...props}
    ref={ref}
  >
    <SwitchPrimitives.Thumb
      className={cn(
        "pointer-events-none block h-4 w-4 rounded-full bg-(--color-card) shadow-none ring-0 transition-transform data-[state=checked]:translate-x-4 data-[state=checked]:bg-(--color-action-foreground) data-[state=unchecked]:translate-x-0"
      )}
    />
  </SwitchPrimitives.Root>
))
Switch.displayName = SwitchPrimitives.Root.displayName

export { Switch }
