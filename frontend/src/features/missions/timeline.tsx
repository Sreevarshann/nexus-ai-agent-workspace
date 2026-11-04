"use client";

import type { TaskEvent } from "@/lib/types";
import { cn } from "@/lib/utils";

const LABEL: Record<string, (e: TaskEvent) => string> = {
  task_started: () => "Mission started",
  plan_created: (e) => `Plan created — ${e.payload.plan?.web_queries?.length ?? 0} queries, agents: ${(e.payload.plan?.route ?? []).join(", ")}`,
  node_started: (e) => `${e.payload.agent} started`,
  node_completed: (e) => `${e.payload.agent} completed — ${e.payload.output ?? ""}`,
  node_failed: (e) => `${e.payload.agent} failed — ${e.payload.error}`,
  tool_call: (e) => `${e.payload.tool}${e.payload.args?.query ? ` “${e.payload.args.query}”` : ""} → ${e.payload.status}${e.payload.error ? ` (${e.payload.error})` : ""}`,
  source_retrieved: (e) => `${e.payload.status === "retrieved" ? "Retrieved" : "Could not retrieve"} ${e.payload.title || e.payload.url}`,
  evidence: (e) => `Passage ${e.payload.label} · ${e.payload.filename}${e.payload.page ? ` p.${e.payload.page}` : ""}`,
  log: (e) => String(e.payload.message ?? ""),
  approval_required: () => "Waiting for human approval",
  approval_resolved: (e) => (e.payload.approved ? "Approved by user" : "Rejected by user"),
  paused: (e) => `Paused before ${e.payload.before_node}`,
  resumed: (e) => `Resumed (${e.payload.reason})`,
  artifact_created: (e) => `Artifact created — ${e.payload.title}`,
  task_completed: () => "Mission completed",
  task_failed: (e) => `Mission failed — ${e.payload.error}`,
  task_cancelled: (e) => `Mission cancelled — ${e.payload.reason}`,
};

const DOT: Record<string, string> = {
  node_failed: "bg-danger", task_failed: "bg-danger", task_completed: "bg-success", node_completed: "bg-success",
  approval_required: "bg-warning", paused: "bg-warning", task_cancelled: "bg-faint", tool_call: "bg-cyan", source_retrieved: "bg-cyan",
};

export function Timeline({ events, onSelect }: { events: TaskEvent[]; onSelect: (node: string) => void }) {
  const start = events[0] ? new Date(events[0].created_at).getTime() : 0;
  return (
    <ol className="relative space-y-0.5 p-3">
      {events.map((e) => (
        <li key={e.id}>
          <button onClick={() => e.node && onSelect(e.node)} className="group flex w-full items-start gap-2.5 rounded-lg px-2 py-1.5 text-left hover:bg-bg-subtle">
            <span className="w-12 shrink-0 pt-px text-right font-mono text-[10.5px] tabular-nums text-faint">+{((new Date(e.created_at).getTime() - start) / 1000).toFixed(1)}s</span>
            <span className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", DOT[e.type] ?? "bg-primary")} />
            <span className="min-w-0 flex-1 text-[12px] leading-snug text-ink-2 group-hover:text-ink">{(LABEL[e.type] ?? (() => e.type))(e)}</span>
          </button>
        </li>
      ))}
    </ol>
  );
}
