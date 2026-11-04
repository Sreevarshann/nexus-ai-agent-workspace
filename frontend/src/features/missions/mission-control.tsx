"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Activity, ArrowLeft, FileText, Hand, Pause, Play, RotateCcw, Square } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/controls";
import { ErrorNote, Skeleton } from "@/components/ui/feedback";
import { Panel, ResizableGroup, ResizeHandle } from "@/components/ui/resizable";
import { StatusBadge } from "@/components/ui/status";
import { ApprovalDialog } from "@/features/missions/approval-dialog";
import { MissionCanvas } from "@/features/missions/canvas";
import { NodeInspector } from "@/features/missions/inspector";
import { buildModel } from "@/features/missions/model";
import { Timeline } from "@/features/missions/timeline";
import { useTaskLive } from "@/features/missions/use-task";
import { api } from "@/lib/api";
import { formatDuration, timeAgo } from "@/lib/utils";

function useNow(intervalMs: number): number {
  const [now, setNow] = React.useState(() => new Date().getTime());
  React.useEffect(() => {
    const t = setInterval(() => setNow(new Date().getTime()), intervalMs);
    return () => clearInterval(t);
  }, [intervalMs]);
  return now;
}

export function MissionControl({ taskId }: { taskId: string }) {
  const qc = useQueryClient();
  const { detail, events, draft, connection } = useTaskLive(taskId);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [dismissedApproval, setDismissedApproval] = React.useState<number | null>(null);
  const now = useNow(1000);
  const data = detail.data;
  const model = React.useMemo(() => (data ? buildModel(data, events) : null), [data, events]);
  const task = data?.task;
  const pendingApproval = [...events].reverse().find((e) => e.type === "approval_required" || e.type === "approval_resolved");
  const awaiting = task?.status === "waiting_approval" && pendingApproval?.type === "approval_required";
  const running = model?.nodes.find((n) => n.status === "running" || n.status === "waiting_approval");
  const selectedNode = model?.nodes.find((n) => n.id === (selected ?? running?.id ?? null));

  // The dialog opens by itself for each new approval request until the user dismisses that request.
  const approvalOpen = !!awaiting && dismissedApproval !== pendingApproval?.id;
  const setApprovalOpen = (o: boolean) => setDismissedApproval(o ? null : (pendingApproval?.id ?? null));

  const control = async (action: "pause" | "resume" | "cancel" | "retry") => {
    try {
      await api.post(`/tasks/${taskId}/${action}`);
      toast.success({ pause: "Pausing at the next step boundary", resume: "Resuming from checkpoint", cancel: "Cancelling mission", retry: "Retrying from the last checkpoint" }[action]);
      void qc.invalidateQueries({ queryKey: ["task-detail", taskId] });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const decide = async (d: { approved: boolean; comment: string; web_queries?: string[] }) => {
    await api.post(`/tasks/${taskId}/approval`, d);
    toast.success(d.approved ? "Approved — the mission continues" : "Rejected — the mission was cancelled");
    void qc.invalidateQueries({ queryKey: ["task-detail", taskId] });
  };

  if (detail.error) return <div className="p-6"><ErrorNote error={detail.error} onRetry={() => detail.refetch()} /></div>;
  if (!data || !model || !task) return <div className="space-y-3 p-6"><Skeleton className="h-16" /><Skeleton className="h-[60vh]" /></div>;

  const elapsed = task.started_at ? (new Date(task.finished_at ?? now).getTime() - new Date(task.started_at).getTime()) : null;
  const artifact = data.artifacts[0];

  const side = (
    <Tabs defaultValue="inspector" className="flex h-full flex-col">
      <div className="border-b border-line px-3 py-2">
        <TabsList className="w-full">
          <TabsTrigger value="inspector" className="flex-1">Inspector</TabsTrigger>
          <TabsTrigger value="timeline" className="flex-1">Timeline · {events.length}</TabsTrigger>
          <TabsTrigger value="tools" className="flex-1">Tools · {data.tool_calls.length}</TabsTrigger>
        </TabsList>
      </div>
      <TabsContent value="inspector" className="nx-scroll min-h-0 flex-1 overflow-y-auto">
        <NodeInspector node={selectedNode} detail={data} events={events} draft={draft} />
      </TabsContent>
      <TabsContent value="timeline" className="nx-scroll min-h-0 flex-1 overflow-y-auto">
        <Timeline events={events} onSelect={setSelected} />
      </TabsContent>
      <TabsContent value="tools" className="nx-scroll min-h-0 flex-1 overflow-y-auto p-3">
        <table className="w-full text-[12px]">
          <thead><tr className="text-left text-[10.5px] uppercase tracking-wide text-faint"><th className="pb-2">Tool</th><th className="pb-2">Status</th><th className="pb-2 text-right">Time</th></tr></thead>
          <tbody>
            {data.tool_calls.map((c) => (
              <tr key={c.id} className="border-t border-line align-top">
                <td className="py-1.5 pr-2"><code className="font-mono text-ink">{c.tool}</code><div className="line-clamp-1 text-[11px] text-muted">{String(c.args.query ?? c.args.url ?? "")}</div></td>
                <td className="py-1.5"><StatusBadge status={c.status === "ok" ? "completed" : c.status === "denied" ? "blocked" : "failed"} /></td>
                <td className="py-1.5 text-right tabular-nums text-muted">{formatDuration(c.duration_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </TabsContent>
    </Tabs>
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-3 border-b border-line bg-surface px-4 py-3 md:px-6">
        <Button asChild variant="ghost" size="icon-sm" aria-label="Back to missions"><Link href="/missions"><ArrowLeft /></Link></Button>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h1 className="truncate text-[15px] font-semibold text-ink">{task.title}</h1>
            <StatusBadge status={task.status} />
          </div>
          <div className="mt-0.5 flex flex-wrap gap-x-3 text-[12px] text-muted">
            <span>{task.kind === "workflow" ? "Workflow run" : `${task.mode} mission`}</span>
            <span>started {timeAgo(task.started_at ?? task.created_at)}</span>
            {elapsed != null && <span>elapsed {formatDuration(elapsed)}</span>}
            <span>{data.sources.filter((s) => s.status === "retrieved").length} sources</span>
            {connection === "reconnecting" && <span className="text-[#b45309]">reconnecting…</span>}
            {task.result.verification && <span>{task.result.verification.supported}/{task.result.verification.claims_checked} claims supported</span>}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {awaiting && <Button onClick={() => setApprovalOpen(true)} className="bg-warning hover:bg-[#d97706]"><Hand /> Review approval</Button>}
          {task.status === "running" && <Button variant="secondary" onClick={() => control("pause")}><Pause /> Pause</Button>}
          {task.status === "paused" && <Button onClick={() => control("resume")}><Play /> Resume</Button>}
          {task.status === "failed" && <Button onClick={() => control("retry")}><RotateCcw /> Retry from checkpoint</Button>}
          {["queued", "running", "paused", "waiting_approval"].includes(task.status) && (
            <Button variant="danger-ghost" onClick={() => control("cancel")}><Square /> Cancel</Button>
          )}
          {artifact && <Button asChild variant="soft"><Link href={`/artifacts/${artifact.id}`}><FileText /> View report</Link></Button>}
        </div>
      </div>
      {task.error && task.status !== "completed" && (
        <div className="border-b border-[#fecaca] bg-danger-soft px-6 py-2 text-[12.5px] text-[#991b1b]"><b>Reason:</b> {task.error}</div>
      )}

      <div className="hidden min-h-0 flex-1 lg:block">
        <ResizableGroup id="mission">
          <Panel id="canvas" minSize="40" defaultSize="68">
            <div className="nx-grid h-full bg-bg" aria-label="Agent workflow canvas">
              <MissionCanvas model={model} selected={selectedNode?.id ?? null} onSelect={setSelected} />
            </div>
          </Panel>
          <ResizeHandle />
          <Panel id="side" minSize="24" defaultSize="32" maxSize="50">
            <div className="h-full bg-surface">{side}</div>
          </Panel>
        </ResizableGroup>
      </div>
      <div className="flex min-h-0 flex-1 flex-col lg:hidden">
        <div className="h-[46vh] shrink-0 border-b border-line bg-bg"><MissionCanvas model={model} selected={selectedNode?.id ?? null} onSelect={setSelected} /></div>
        <div className="min-h-0 flex-1 bg-surface">{side}</div>
      </div>

      <ApprovalDialog open={approvalOpen && awaiting} onOpenChange={setApprovalOpen} request={pendingApproval?.payload.request} onDecide={decide} />
      {!events.length && <div className="sr-only"><Activity /> Waiting for the worker to start this mission</div>}
    </div>
  );
}
