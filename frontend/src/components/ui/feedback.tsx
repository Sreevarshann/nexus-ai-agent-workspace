import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("nx-skeleton rounded-lg", className)} />;
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: {
  icon: LucideIcon;
  title: string;
  description?: React.ReactNode;
  action?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-14 text-center", className)}>
      <div className="relative mb-4">
        <div className="absolute inset-0 -m-3 rounded-full bg-primary-soft blur-xl" />
        <div className="relative flex size-12 items-center justify-center rounded-2xl border border-[#dbe5ff] bg-surface text-primary shadow-card">
          <Icon className="size-5" />
        </div>
      </div>
      <h3 className="text-[15px] font-semibold text-ink">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-[13px] leading-relaxed text-muted">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorNote({ title = "Something went wrong", error, onRetry }: { title?: string; error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div role="alert" className="rounded-xl border border-[#fecaca] bg-danger-soft px-4 py-3 text-[13px] text-[#991b1b]">
      <div className="font-medium">{title}</div>
      <div className="mt-0.5 break-words opacity-90">{message}</div>
      {onRetry && (
        <button onClick={onRetry} className="mt-2 text-[12.5px] font-medium text-[#b91c1c] underline underline-offset-2">
          Try again
        </button>
      )}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  icon: Icon,
  actions,
}: {
  title: string;
  description?: string;
  icon?: LucideIcon;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="flex items-start gap-3">
        {Icon && (
          <div className="mt-0.5 hidden size-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-[#3b82f6] text-white shadow-[0_6px_16px_-6px_rgb(37_99_235/0.7)] sm:flex">
            <Icon className="size-5" />
          </div>
        )}
        <div>
          <h1 className="text-[22px] font-semibold tracking-[-0.02em] text-ink">{title}</h1>
          {description && <p className="mt-1 max-w-2xl text-[13.5px] text-muted">{description}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}
