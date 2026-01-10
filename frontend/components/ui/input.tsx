import * as React from "react"

import { cn } from "@/lib/utils"

const Input = React.forwardRef<HTMLInputElement, React.ComponentProps<"input">>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-11 w-full rounded-lg border border-(--color-border) bg-(--color-card) px-4 text-base text-(--color-foreground) transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium file:text-(--color-foreground) placeholder:text-(--color-muted-foreground) focus-visible:outline-none focus-visible:border-(--color-action) focus-visible:ring-2 focus-visible:ring-(--color-ring) focus-visible:ring-offset-2 focus-visible:ring-offset-(--color-background) disabled:cursor-not-allowed disabled:bg-(--color-muted) disabled:text-(--color-muted-foreground) disabled:border-(--color-border-subtle) md:text-sm",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
