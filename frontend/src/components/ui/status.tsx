import { CheckCircle2, CircleDashed, Clock3, Hand, Loader2, OctagonX, PauseCircle, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export const STATUS_META: Record<string, { label: string; tone: "neutral" | "blue" | "green" | "amber" | "red" | "violet"; Icon: typeof Loader2 }> = {
  pending: { label: "Pending", tone: "neutral", Icon: CircleDashed },
  queued: { label: "Queued", tone: "neutral", Icon: Clock3 },
  running: { label: "Running", tone: "blue", Icon: Loader2 },
  streaming: { label: "Streaming", tone: "blue", Icon: Loader2 },
  processing: { label: "Processing", tone: "blue", Icon: Loader2 },
  waiting_approval: { label: "Waiting for approval", tone: "amber", Icon: Hand },
  paused: { label: "Paused", tone: "amber", Icon: PauseCircle },
  completed: { label: "Completed", tone: "green", Icon: CheckCircle2 },
  complete: { label: "Complete", tone: "green", Icon: CheckCircle2 },
  ready: { label: "Ready", tone: "green", Icon: CheckCircle2 },
  retrieved: { label: "Retrieved", tone: "green", Icon: CheckCircle2 },
  failed: { label: "Failed", tone: "red", Icon: XCircle },
  error: { label: "Error", tone: "red", Icon: XCircle },
  blocked: { label: "Blocked", tone: "red", Icon: OctagonX },
  cancelled: { label: "Cancelled", tone: "neutral", Icon: OctagonX },
  skipped: { label: "Skipped", tone: "neutral", Icon: CircleDashed },
};

export function StatusBadge({ status, className }: { status: string; className?: string }) {
  const m = STATUS_META[status] ?? { label: status, tone: "neutral" as const, Icon: CircleDashed };
  const spin = ["running", "streaming", "processing"].includes(status);
  return (
    <Badge tone={m.tone} className={className}>
      <m.Icon className={cn(spin && "animate-spin")} />
      {m.label}
    </Badge>
  );
}

export function StatusDot({ ok, pulse, className }: { ok: boolean | null; pulse?: boolean; className?: string }) {
  return (
    <span
      className={cn(
        "inline-block size-2 rounded-full",
        ok === null ? "bg-faint" : ok ? "bg-success" : "bg-danger",
        pulse && ok && "animate-pulse-ring",
        className,
      )}
    />
  );
}
