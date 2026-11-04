"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, History as HistoryIcon, MessageSquareText, Trash2 } from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/controls";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status";
import { api } from "@/lib/api";
import { useConversations, useTasks } from "@/lib/queries";
import { formatDateTime } from "@/lib/utils";

export function HistoryPage() {
  const [q, setQ] = React.useState("");
  const qc = useQueryClient();
  const { data: convs, isPending } = useConversations(q || undefined);
  const { data: tasks } = useTasks();
  const del = useMutation({ mutationFn: (id: string) => api.del(`/conversations/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["conversations"] }) });
  const filteredTasks = (tasks ?? []).filter((t) => !q || t.title.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-8 md:px-8">
      <PageHeader icon={HistoryIcon} title="History" description="Every conversation, mission and workflow run is persisted — reopen any of them exactly as it was." actions={<Input placeholder="Search history" value={q} onChange={(e) => setQ(e.target.value)} className="w-64" aria-label="Search history" />} />
      <Tabs defaultValue="conversations">
        <TabsList>
          <TabsTrigger value="conversations"><MessageSquareText /> Conversations · {convs?.length ?? 0}</TabsTrigger>
          <TabsTrigger value="tasks"><Activity /> Missions & runs · {filteredTasks.length}</TabsTrigger>
        </TabsList>
        <TabsContent value="conversations" className="mt-4">
          {isPending ? <Skeleton className="h-48" /> : !convs?.length ? <Card><EmptyState icon={MessageSquareText} title="Nothing here yet" /></Card> : (
            <Card className="divide-y divide-line overflow-hidden">
              {convs.map((c) => (
                <div key={c.id} className="group flex items-center gap-3 px-5 py-3 hover:bg-bg-subtle/60">
                  <MessageSquareText className="size-4 text-primary" />
                  <Link href={`/workspace/${c.id}`} className="min-w-0 flex-1">
                    <div className="truncate text-[13.5px] font-medium text-ink">{c.title}</div>
                    <div className="text-[12px] text-faint">Updated {formatDateTime(c.updated_at)}</div>
                  </Link>
                  <Button variant="danger-ghost" size="icon-sm" className="opacity-0 group-hover:opacity-100 focus:opacity-100" aria-label={`Delete ${c.title}`} onClick={() => { if (window.confirm("Delete this conversation?")) del.mutate(c.id); }}><Trash2 /></Button>
                </div>
              ))}
            </Card>
          )}
        </TabsContent>
        <TabsContent value="tasks" className="mt-4">
          <Card className="divide-y divide-line overflow-hidden">
            {filteredTasks.map((t) => (
              <Link key={t.id} href={`/missions/${t.id}`} className="flex items-center gap-3 px-5 py-3 hover:bg-bg-subtle/60">
                <Activity className="size-4 text-primary" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13.5px] font-medium text-ink">{t.title}</div>
                  <div className="text-[12px] text-faint">{t.kind === "workflow" ? "Workflow run" : `${t.mode} mission`} · {formatDateTime(t.created_at)}</div>
                </div>
                <StatusBadge status={t.status} />
              </Link>
            ))}
            {!filteredTasks.length && <EmptyState icon={Activity} title="No missions" />}
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
