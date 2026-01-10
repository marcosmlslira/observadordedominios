import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl border border-transparent text-sm font-medium transition-colors focus-visible:outline-none focus-visible:border-(--color-action) focus-visible:ring-2 focus-visible:ring-(--color-ring) focus-visible:ring-offset-2 focus-visible:ring-offset-(--color-background) disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-(--color-muted) disabled:text-(--color-muted-foreground) disabled:border-(--color-border-subtle) [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "bg-(--color-action) text-(--color-action-foreground) hover:opacity-90",
        destructive:
          "bg-(--color-action-inverse) text-(--color-action-inverse-foreground) border-(--color-border-strong) hover:opacity-90",
        outline:
          "bg-transparent border-(--color-border-strong) text-(--color-foreground) hover:bg-(--color-muted)",
        secondary:
          "bg-(--color-muted) text-(--color-foreground) hover:bg-(--color-popover)",
        ghost:
          "bg-transparent text-(--color-foreground) hover:bg-(--color-muted)",
        link: "bg-transparent text-(--color-foreground) underline-offset-4 hover:underline",
      },
      size: {
        default: "h-11 px-5",
        sm: "h-10 px-4 text-xs",
        lg: "h-12 px-8",
        icon: "h-11 w-11",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
