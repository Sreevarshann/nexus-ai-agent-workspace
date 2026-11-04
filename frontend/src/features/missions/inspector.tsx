"use client";

import { ExternalLink, FileText, Wrench } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/feedback";
import { StatusBadge } from "@/components/ui/status";
import { Markdown } from "@/features/chat/markdown";
import { NODE_ICONS } from "@/features/missions/canvas";
import type { GraphNode } from "@/features/missions/model";
import { runsFor } from "@/features/missions/model";
import type { TaskDetail, TaskEvent } from "@/lib/types";
import { cn, domainOf, formatDateTime, formatDuration } from "@/lib/utils";

export function NodeInspector({ node, detail, events, draft }: { node: GraphNode | undefined; detail: TaskDetail; events: TaskEvent[]; draft: string }) {
  if (!node) {
    return <EmptyState icon={Wrench} title="Select an agent" description="Click any node on the canvas to inspect its inputs, outputs, tool calls and evidence." className="py-16" />;
  }
  const Icon = NODE_ICONS[node.kind] ?? Wrench;
  const runs = runsFor(node, detail.agent_runs);
  const runIds = new Set(runs.map((r) => r.id));
  const calls = detail.tool_calls.filter((c) => c.agent_run_id && runIds.has(c.agent_run_id));
  const nodeEvents = events.filter((e) => e.node === node.id);
  const plan = node.kind === "planner" ? events.find((e) => e.type === "plan_created")?.payload.plan : undefined;
  const verification = node.kind === "verifier" || node.kind === "verification" ? nodeEvents.find((e) => e.payload.verification)?.payload.verification : undefined;
  const sources = node.kind === "web_researcher" || node.kind === "web_search" ? nodeEvents.filter((e) => e.type === "source_retrieved") : [];
  const artifact = nodeEvents.find((e) => e.type === "artifact_created")?.payload;
  const run = runs.at(-1);

  return (
    <div className="space-y-5 p-4">
      <div className="flex items-start gap-3">
        <div className="flex size-10 items-center justify-center rounded-xl bg-primary-soft text-primary"><Icon className="size-5" /></div>
        <div className="min-w-0 flex-1">
          <div className="text-[15px] font-semibold text-ink">{node.agent}</div>
          <div className="text-[12.5px] text-muted">{node.role}</div>
        </div>
        <StatusBadge status={node.status === "skipped" ? "skipped" : node.status} />
      </div>

      <dl className="grid grid-cols-3 gap-2 text-[12px]">
        <Stat k="Started" v={node.startedAt ? formatDateTime(node.startedAt) : "—"} />
        <Stat k="Finished" v={node.finishedAt ? formatDateTime(node.finishedAt) : "—"} />
        <Stat k="Duration" v={formatDuration(node.durationMs)} />
      </dl>

      {run?.input_summary && <Block title="Input">{run.input_summary}</Block>}
      {node.error && <Block title="Error" tone="danger">{node.error}</Block>}
      {node.output && <Block title="Output">{node.output}</Block>}

      {plan && (
        <Section title="Plan">
          <ol className="space-y-1.5">
            {(plan.steps as { agent: string; description: string }[]).map((s, i) => (
              <li key={i} className="flex gap-2 text-[12.5px] text-ink-2">
                <span className="mt-px flex size-5 shrink-0 items-center justify-center rounded-full bg-primary-soft text-[10.5px] font-semibold text-primary">{i + 1}</span>
                <span><span className="font-medium text-ink">{s.agent.replace(/_/g, " ")}</span> — {s.description}</span>
              </li>
            ))}
          </ol>
          {!!plan.web_queries?.length && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {(plan.web_queries as string[]).map((q) => <Badge key={q} tone="blue">{q}</Badge>)}
            </div>
          )}
        </Section>
      )}

      {node.kind === "synthesizer" && node.status === "running" && draft && (
        <Section title="Live draft">
          <div className="max-h-80 overflow-y-auto rounded-xl border border-line bg-surface-2 p-3">
            <Markdown content={draft} streaming />
          </div>
        </Section>
      )}

      {verification && (
        <Section title="Verification">
          <div className="grid grid-cols-3 gap-2">
            <Stat k="Supported" v={verification.supported} tone="green" />
            <Stat k="Weak" v={verification.weak} tone="amber" />
            <Stat k="Unsupported" v={verification.unsupported} tone="red" />
          </div>
          {verification.fabricated_labels_removed?.length > 0 && (
            <p className="mt-2 text-[12px] text-muted">Removed invalid citation labels: {verification.fabricated_labels_removed.join(", ")}</p>
          )}
          <p className="mt-2 text-[11.5px] text-faint">{verification.method}</p>
        </Section>
      )}

      {sources.length > 0 && (
        <Section title={`Sources (${sources.filter((s) => s.payload.status === "retrieved").length}/${sources.length} retrieved)`}>
          <div className="space-y-2">
            {sources.map((s) => (
              <a key={s.id} href={s.payload.url} target="_blank" rel="noopener noreferrer" className="block rounded-xl border border-line p-2.5 transition hover:border-primary/40">
                <div className="flex items-center gap-2">
                  <StatusBadge status={s.payload.status} />
                  <span className="truncate text-[11.5px] text-muted">{domainOf(s.payload.url)}</span>
                  <ExternalLink className="ml-auto size-3 shrink-0 text-faint" />
                </div>
                <div className="mt-1 line-clamp-2 text-[12.5px] font-medium text-ink">{s.payload.title}</div>
                {s.payload.error && <div className="mt-0.5 text-[11.5px] text-[#b45309]">{s.payload.error}</div>}
              </a>
            ))}
          </div>
        </Section>
      )}

      {artifact && (
        <Link href={`/artifacts/${artifact.artifact_id}`} className="flex items-center gap-2 rounded-xl border border-[#d6e2ff] bg-primary-soft px-3 py-2.5 text-[13px] font-medium text-primary-deep hover:bg-[#e2eaff]">
          <FileText className="size-4" /> Open “{artifact.title}”
        </Link>
      )}

      <Section title={`Tool calls (${calls.length})`}>
        {calls.length === 0 ? (
          <p className="text-[12.5px] text-faint">This agent made no logged tool calls.</p>
        ) : (
          <div className="space-y-1.5">
            {calls.map((c) => (
              <details key={c.id} className="group rounded-lg border border-line">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-2.5 py-2 text-[12.5px]">
                  <span className={cn("size-1.5 rounded-full", c.status === "ok" ? "bg-success" : c.status === "denied" ? "bg-warning" : "bg-danger")} />
                  <code className="font-mono text-[11.5px] text-ink">{c.tool}</code>
                  <span className="truncate text-muted">{c.result_summary || c.error}</span>
                  <span className="ml-auto shrink-0 text-[11px] tabular-nums text-faint">{formatDuration(c.duration_ms)}</span>
                </summary>
                <pre className="overflow-x-auto border-t border-line bg-surface-2 p-2.5 font-mono text-[11px] text-ink-2">{JSON.stringify(c.args, null, 2)}</pre>
                {c.error && <div className="border-t border-line px-2.5 py-1.5 text-[11.5px] text-danger">{c.error}</div>}
              </details>
            ))}
          </div>
        )}
      </Section>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h4 className="mb-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-faint">{title}</h4>
      {children}
    </section>
  );
}

function Block({ title, children, tone }: { title: string; children: React.ReactNode; tone?: "danger" }) {
  return (
    <Section title={title}>
      <div className={cn("whitespace-pre-wrap rounded-xl border p-3 text-[12.5px] leading-relaxed", tone === "danger" ? "border-[#fecaca] bg-danger-soft text-[#991b1b]" : "border-line bg-surface-2 text-ink-2")}>{children}</div>
    </Section>
  );
}

function Stat({ k, v, tone }: { k: string; v: React.ReactNode; tone?: "green" | "amber" | "red" }) {
  return (
    <div className="rounded-lg border border-line px-2.5 py-2">
      <dt className="text-[10.5px] text-faint">{k}</dt>
      <dd className={cn("mt-0.5 truncate font-semibold tabular-nums text-ink", tone === "green" && "text-[#047857]", tone === "amber" && "text-[#b45309]", tone === "red" && "text-[#b91c1c]")}>{v}</dd>
    </div>
  );
}
