import { cn } from "@/lib/utils"

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse rounded-none bg-muted border border-border/40", className)}
      {...props}
    />
  )
}

export { Skeleton }
