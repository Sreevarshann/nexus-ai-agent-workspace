import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={cn("size-8", className)} aria-hidden>
      <defs>
        <linearGradient id="nx-logo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3b82f6" />
          <stop offset="1" stopColor="#1d4ed8" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="16" fill="url(#nx-logo)" />
      <path d="M20 44V20l24 24V20" fill="none" stroke="#fff" strokeWidth="5.5" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="44" cy="20" r="4" fill="#67e8f9" />
    </svg>
  );
}

export function Wordmark({ collapsed }: { collapsed?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <LogoMark />
      {!collapsed && (
        <div className="leading-none">
          <div className="text-[15px] font-semibold tracking-[-0.02em] text-ink">
            NEXUS <span className="text-primary">AI</span>
          </div>
          <div className="mt-1 text-[10.5px] font-medium uppercase tracking-[0.14em] text-faint">Intelligence OS</div>
        </div>
      )}
    </div>
  );
}
