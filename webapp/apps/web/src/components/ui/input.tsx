import type * as React from "react";
import { cn } from "@/lib/utils";

const field =
  "border-input bg-transparent dark:bg-input/30 placeholder:text-muted-foreground w-full min-w-0 rounded-md border px-3 " +
  "text-sm shadow-xs transition-[color,box-shadow] outline-none disabled:cursor-not-allowed disabled:opacity-50 " +
  "focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] " +
  "aria-invalid:border-destructive aria-invalid:ring-destructive/20";

export function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return <input type={type} data-slot="input" className={cn(field, "h-9 py-1", className)} {...props} />;
}

export function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return <textarea data-slot="textarea" className={cn(field, "min-h-16 py-2", className)} {...props} />;
}

/** Native select styled like the inputs — enough for short option lists. */
export function NativeSelect({ className, ...props }: React.ComponentProps<"select">) {
  return <select data-slot="select" className={cn(field, "h-9 py-1 pr-8 dark:[&>option]:bg-popover", className)} {...props} />;
}
