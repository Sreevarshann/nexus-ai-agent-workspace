import { cva, type VariantProps } from "class-variance-authority";
import * as React from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11.5px] font-medium leading-4 [&_svg]:size-3",
  {
    variants: {
      tone: {
        neutral: "border-line bg-surface-2 text-ink-2",
        blue: "border-[#d6e2ff] bg-primary-soft text-primary-deep",
        cyan: "border-[#bdeef7] bg-[#ecfeff] text-[#0e7490]",
        green: "border-[#c6f1df] bg-success-soft text-[#047857]",
        amber: "border-[#fde7b0] bg-warning-soft text-[#b45309]",
        red: "border-[#fecaca] bg-danger-soft text-[#b91c1c]",
        violet: "border-[#e4d9fd] bg-[#f5f3ff] text-violet",
      },
    },
    defaultVariants: { tone: "neutral" },
  },
);

export function Badge({ className, tone, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ tone }), className)} {...props} />;
}

export function Kbd({ className, ...props }: React.HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        "inline-flex h-5 min-w-5 items-center justify-center rounded-md border border-line bg-surface px-1 font-mono text-[10.5px] font-medium text-muted shadow-[0_1px_0_var(--line)]",
        className,
      )}
      {...props}
    />
  );
}
