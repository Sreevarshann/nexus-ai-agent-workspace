"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Loader2, Plus, Workflow as WorkflowIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/feedback";
import { NODE_ICONS } from "@/features/missions/canvas";
import { api } from "@/lib/api";
import { keys, useWorkflows } from "@/lib/queries";
import type { Workflow, WorkflowGraph } from "@/lib/types";
import { timeAgo } from "@/lib/utils";

type Template = { key: string; name: string; description: string; graph: WorkflowGraph };

export function WorkflowList() {
  const qc = useQueryClient();
  const router = useRouter();
  const { data: workflows, isPending } = useWorkflows();
  const { data: templates } = useQuery({ queryKey: ["wf-templates"], queryFn: () => api.get<Template[]>("/workflows/templates") });
  const create = useMutation({
    mutationFn: (body: { name: string; template?: string; graph?: WorkflowGraph }) => api.post<Workflow>("/workflows", body),
    onSuccess: (w) => { void qc.invalidateQueries({ queryKey: keys.workflows }); router.push(`/workflows/${w.id}`); },
    onError: (e) => toast.error((e as Error).message),
  });

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-8 md:px-8">
      <PageHeader icon={WorkflowIcon} title="Workflow Builder" description="Compose typed pipelines from web search, retrieval, LLM reasoning, analysis, verification and approval nodes. Each run executes on the same LangGraph runtime as missions."
        actions={<Button onClick={() => create.mutate({ name: "Untitled workflow", graph: { nodes: [{ id: "n1", type: "input", position: { x: 80, y: 160 }, data: { label: "Input", config: {} } }, { id: "n2", type: "output", position: { x: 420, y: 160 }, data: { label: "Output", config: {} } }], edges: [] } })} disabled={create.isPending}>{create.isPending ? <Loader2 className="animate-spin" /> : <Plus />} Blank workflow</Button>} />

      <section>
        <h2 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-faint">Templates</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {templates?.map((t) => (
            <button key={t.key} onClick={() => create.mutate({ name: t.name, template: t.key })} className="group rounded-2xl border border-line bg-surface p-4 text-left shadow-card transition hover:border-[#c7d6fb] hover:shadow-pop">
              <div className="text-[14px] font-semibold text-ink">{t.name}</div>
              <p className="mt-1 text-[12.5px] text-muted">{t.description}</p>
              <div className="mt-3 flex flex-wrap items-center gap-1">
                {t.graph.nodes.map((n, i) => {
                  const Icon = NODE_ICONS[n.type] ?? WorkflowIcon;
                  return (
                    <span key={n.id} className="flex items-center gap-1">
                      {i > 0 && <ArrowRight className="size-3 text-faint" />}
                      <span className="inline-flex items-center gap-1 rounded-md bg-primary-soft px-1.5 py-0.5 text-[11px] text-primary-deep"><Icon className="size-3" />{n.data.label}</span>
                    </span>
                  );
                })}
              </div>
            </button>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-faint">Your workflows</h2>
        {isPending ? <Skeleton className="h-40" /> : !workflows?.length ? (
          <Card><EmptyState icon={WorkflowIcon} title="No saved workflows" description="Start from a template above or a blank canvas." /></Card>
        ) : (
          <Card className="divide-y divide-line overflow-hidden">
            {workflows.map((w) => (
              <Link key={w.id} href={`/workflows/${w.id}`} className="group flex items-center gap-4 px-5 py-3.5 hover:bg-bg-subtle/60">
                <div className="flex size-9 items-center justify-center rounded-xl bg-primary-soft text-primary"><WorkflowIcon className="size-4" /></div>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13.5px] font-medium text-ink">{w.name}</div>
                  <div className="text-[12px] text-muted">{w.graph.nodes.length} nodes · updated {timeAgo(w.updated_at)}</div>
                </div>
                <ArrowRight className="size-4 text-faint group-hover:text-primary" />
              </Link>
            ))}
          </Card>
        )}
      </section>
    </div>
  );
}
