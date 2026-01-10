import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:border-(--color-action) focus-visible:ring-2 focus-visible:ring-(--color-ring) focus-visible:ring-offset-2 focus-visible:ring-offset-(--color-background)",
  {
    variants: {
      variant: {
        default:
          "border-(--color-border-subtle) bg-(--color-muted) text-(--color-foreground) hover:bg-(--color-popover)",
        secondary:
          "border-(--color-border-subtle) bg-transparent text-(--color-muted-foreground) hover:bg-(--color-muted)",
        destructive:
          "border-(--color-border-strong) bg-(--color-action-inverse) text-(--color-action-inverse-foreground) hover:opacity-90",
        outline: "border-(--color-border-strong) text-(--color-foreground)",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }
