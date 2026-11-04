"use client";

import { Activity, ArrowRight, Bot, FlaskConical, Workflow } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/feedback";
import { StatusBadge } from "@/components/ui/status";
import { useTasks } from "@/lib/queries";
import type { Task } from "@/lib/types";
import { formatDuration, timeAgo } from "@/lib/utils";

export function MissionList() {
  const { data: tasks, isPending } = useTasks();
  const active = tasks?.filter((t) => ["queued", "running", "paused", "waiting_approval"].includes(t.status)) ?? [];
  const past = tasks?.filter((t) => !active.includes(t)) ?? [];
  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-8 md:px-8">
      <PageHeader icon={Activity} title="Mission Control" description="Every multi-agent mission and workflow run, with its live execution graph, tool calls and evidence." actions={<Button asChild><Link href="/research"><FlaskConical /> New research mission</Link></Button>} />
      {isPending ? <Skeleton className="h-64" /> : !tasks?.length ? (
        <Card><EmptyState icon={Bot} title="No missions yet" description="Start a research mission, launch an agent from the workspace, or run a workflow." action={<Button asChild><Link href="/research">Start a mission</Link></Button>} /></Card>
      ) : (
        <>
          {active.length > 0 && <Group title="Active" tasks={active} />}
          <Group title="Recent" tasks={past} />
        </>
      )}
    </div>
  );
}

function Group({ title, tasks }: { title: string; tasks: Task[] }) {
  return (
    <section>
      <h2 className="mb-3 text-[12px] font-semibold uppercase tracking-[0.08em] text-faint">{title}</h2>
      <Card className="divide-y divide-line overflow-hidden">
        {tasks.map((t) => (
          <Link key={t.id} href={`/missions/${t.id}`} className="group flex items-center gap-4 px-5 py-3.5 transition hover:bg-bg-subtle/60">
            <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">
              {t.kind === "workflow" ? <Workflow className="size-4" /> : <Bot className="size-4" />}
            </div>
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13.5px] font-medium text-ink">{t.title}</div>
              <div className="mt-0.5 text-[12px] text-muted">
                {t.kind === "workflow" ? "Workflow" : `${t.mode} mission`} · {timeAgo(t.created_at)}
                {t.started_at && t.finished_at && ` · ${formatDuration(new Date(t.finished_at).getTime() - new Date(t.started_at).getTime())}`}
                {t.result.sources != null && ` · ${t.result.sources} sources`}
              </div>
            </div>
            <StatusBadge status={t.status} />
            <ArrowRight className="size-4 text-faint transition group-hover:translate-x-0.5 group-hover:text-primary" />
          </Link>
        ))}
      </Card>
    </section>
  );
}
