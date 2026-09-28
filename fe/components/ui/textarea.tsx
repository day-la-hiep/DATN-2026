import * as React from "react"

import { cn } from "@/lib/utils"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-16 w-full rounded-xl border border-border bg-background/60 backdrop-blur-xs px-3.5 py-2.5 text-sm shadow-xs transition-all outline-none placeholder:text-muted-foreground/60 focus-visible:border-brand focus-visible:ring-2 focus-visible:ring-brand/20 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive font-sans",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
