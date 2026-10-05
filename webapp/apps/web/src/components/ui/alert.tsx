import { cva, type VariantProps } from "class-variance-authority";
import type * as React from "react";
import { cn } from "@/lib/utils";

const alertVariants = cva(
  "relative w-full rounded-lg border px-4 py-3 text-sm grid has-[>svg]:grid-cols-[1rem_1fr] gap-x-3 gap-y-0.5 items-start [&>svg]:size-4 [&>svg]:translate-y-0.5",
  {
    variants: {
      variant: {
        default: "bg-card text-card-foreground [&>svg]:text-muted-foreground",
        destructive: "text-destructive bg-card [&>svg]:text-current",
        warning: "bg-warning/10 border-warning/40 [&>svg]:text-warning",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Alert({ className, variant, ...props }: React.ComponentProps<"div"> & VariantProps<typeof alertVariants>) {
  return <div role="alert" className={cn(alertVariants({ variant }), className)} {...props} />;
}

export function AlertDescription({ className, ...props }: React.ComponentProps<"div">) {
  return <div className={cn("col-start-2 text-sm [&_p]:leading-relaxed", className)} {...props} />;
}
