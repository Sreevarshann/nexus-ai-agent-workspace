"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, AlertTriangle, ArrowUpRight, Check, Copy, Database, FileText, RefreshCw, Sparkles } from "lucide-react";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status";
import { Tooltip } from "@/components/ui/overlay";
import { Markdown } from "@/features/chat/markdown";
import { ToolActivity } from "@/features/chat/tool-activity";
import { useMessageStream, type ToolEvent } from "@/features/chat/use-message-stream";
import { ChartView } from "@/features/data/chart";
import { LogoMark } from "@/components/shell/logo";
import { api } from "@/lib/api";
import { keys } from "@/lib/queries";
import type { Citation, Message, Task } from "@/lib/types";
import { cn, formatDuration } from "@/lib/utils";

const MODE_LABEL: Record<string, string> = { chat: "Chat", research: "Research", analysis: "Analysis", agent: "Agent mission" };

export function UserMessage({ m }: { m: Message }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[min(680px,88%)]">
        {m.attachments.length > 0 && (
          <div className="mb-1.5 flex flex-wrap justify-end gap-1.5">
            {m.attachments.map((a) => (
              <Badge key={a.id} tone={a.kind === "document" ? "cyan" : "violet"}>
                {a.kind === "document" ? <FileText /> : <Database />} {a.name}
              </Badge>
            ))}
          </div>
        )}
        <div className="whitespace-pre-wrap rounded-2xl rounded-br-md bg-gradient-to-br from-primary to-[#3070f0] px-4 py-2.5 text-[14.5px] leading-relaxed text-white shadow-[0_6px_18px_-10px_rgb(37_99_235/0.8)]">
          {m.content}
        </div>
        {m.mode !== "chat" && <div className="mt-1 text-right text-[11px] text-faint">{MODE_LABEL[m.mode]} mode</div>}
      </div>
    </div>
  );
}

export function AssistantMessage({
  m,
  conversationId,
  onCite,
  onSelect,
  selected,
  onSuggestion,
  isLast,
}: {
  m: Message;
  conversationId: string;
  onCite: (c: Citation) => void;
  onSelect: () => void;
  selected: boolean;
  onSuggestion: (q: string) => void;
  isLast: boolean;
}) {
  const qc = useQueryClient();
  const stream = useMessageStream(m, conversationId);
  const streaming = m.status === "streaming" && !m.meta.task_id && !stream.done;
  const text = streaming ? stream.text : m.content;
  const citations: Citation[] = streaming ? stream.sources : m.citations;
  const analysis = streaming ? stream.analysis : m.meta.analysis;
  const [copied, setCopied] = React.useState(false);
  const known = new Set([...(streaming ? stream.sources : m.citations).map((c) => c.label), ...(analysis?.results.map((r) => r.label) ?? [])]);

  const cite = (label: string) => {
    const c = citations.find((x) => x.label === label);
    if (c) return onCite(c);
    const r = analysis?.results.find((x) => x.label === label);
    if (r) onCite({ label, kind: "data", title: r.title, sql: r.sql });
  };

  const regenerate = async () => {
    try {
      await api.post(`/messages/${m.id}/regenerate`);
      await qc.invalidateQueries({ queryKey: keys.messages(conversationId) });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  if (m.meta.task_id) return <MissionMessage m={m} onCite={onCite} />;

  return (
    <div className={cn("group flex gap-3", selected && "")} onClick={onSelect}>
      <LogoMark className="mt-0.5 size-7 shrink-0 rounded-lg" />
      <div className="min-w-0 flex-1">
        <div className="mb-1.5 flex flex-wrap items-center gap-2 text-[12px] text-muted">
          <span className="font-semibold text-ink">NEXUS</span>
          {m.mode !== "chat" && <Badge tone="blue">{MODE_LABEL[m.mode]}</Badge>}
          {streaming && stream.statusText && (
            <span className="flex items-center gap-1.5 text-primary"><Sparkles className="size-3 animate-pulse" />{stream.statusText}</span>
          )}
          {streaming && stream.connection === "reconnecting" && <Badge tone="amber">Reconnecting…</Badge>}
          {!streaming && m.meta.model && (
            <span className="opacity-0 transition group-hover:opacity-100">
              {m.meta.model} · {formatDuration(m.meta.latency_ms)}
              {m.meta.tokens?.completion ? ` · ${m.meta.tokens.completion} tokens` : ""}
            </span>
          )}
        </div>

        <ToolActivity tools={streaming ? stream.tools : ((m.meta.tools as ToolEvent[] | undefined) ?? [])} live={streaming} />

        {analysis && analysis.results.length > 0 && (
          <div className="mb-4 grid gap-3 xl:grid-cols-2">
            {analysis.results.filter((r) => r.chart).map((r) => (
              <ChartView key={r.label} spec={{ ...r.chart!, title: r.title, columns: r.columns, rows: r.rows, label: r.label }} height={220} />
            ))}
          </div>
        )}

        {m.status === "error" && !streaming ? (
          <div className="flex items-start gap-2.5 rounded-xl border border-[#fecaca] bg-danger-soft px-3.5 py-3 text-[13px] text-[#991b1b]">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <div>
              <div className="font-medium">The model could not answer</div>
              <div className="mt-0.5 opacity-90">{m.meta.error}</div>
            </div>
          </div>
        ) : (
          <Markdown content={text} streaming={streaming} onCite={cite} known={known} />
        )}
        {m.status === "cancelled" && <div className="mt-2 text-[12px] text-muted">Generation stopped.</div>}
        {m.meta.removed_citations?.length ? (
          <div className="mt-2 text-[11.5px] text-muted">Removed citation labels not backed by retrieved evidence: {m.meta.removed_citations.join(", ")}</div>
        ) : null}

        {citations.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {citations.map((c) => (
              <button key={c.label} onClick={() => onCite(c)} className="flex max-w-[260px] items-center gap-1.5 rounded-lg border border-line bg-surface px-2 py-1 text-left text-[12px] text-ink-2 shadow-sm transition hover:border-primary/40 hover:text-ink">
                <span className="font-mono text-[10.5px] font-semibold text-primary">{c.label}</span>
                <span className="truncate">{c.kind === "web" ? c.domain : `${c.filename}${c.page ? ` · p.${c.page}` : ""}`}</span>
              </button>
            ))}
          </div>
        )}

        {!streaming && (
          <div className="mt-2 flex items-center gap-0.5 opacity-60 transition group-hover:opacity-100">
            <Tooltip content={copied ? "Copied" : "Copy"}>
              <Button variant="ghost" size="icon-sm" aria-label="Copy response" onClick={async () => {
                await navigator.clipboard.writeText(m.content);
                setCopied(true);
                setTimeout(() => setCopied(false), 1500);
              }}>
                {copied ? <Check /> : <Copy />}
              </Button>
            </Tooltip>
            <Tooltip content={m.status === "error" ? "Retry" : "Regenerate"}>
              <Button variant="ghost" size="icon-sm" aria-label={m.status === "error" ? "Retry response" : "Regenerate response"} onClick={regenerate}>
                <RefreshCw />
              </Button>
            </Tooltip>
          </div>
        )}

        {isLast && !streaming && !!m.meta.suggestions?.length && (
          <div className="mt-3 flex flex-wrap gap-2">
            {m.meta.suggestions.map((s) => (
              <button key={s} onClick={() => onSuggestion(s)} className="rounded-full border border-[#d6e2ff] bg-primary-soft/60 px-3 py-1.5 text-left text-[12.5px] text-primary-deep transition hover:bg-primary-soft">
                {s}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MissionMessage({ m, onCite }: { m: Message; onCite: (c: Citation) => void }) {
  const taskId = m.meta.task_id!;
  const qc = useQueryClient();
  const { data: task } = useQuery({
    queryKey: keys.task(taskId),
    queryFn: () => api.get<Task>(`/tasks/${taskId}`),
    refetchInterval: (q) => (q.state.data && ["completed", "failed", "cancelled"].includes(q.state.data.status) ? false : 2000),
    refetchIntervalInBackground: true,
  });
  React.useEffect(() => {
    if (task && ["completed", "failed", "cancelled"].includes(task.status)) {
      void qc.invalidateQueries({ queryKey: keys.messages(m.conversation_id) });
    }
  }, [task, qc, m.conversation_id]);

  const done = task?.status === "completed";
  return (
    <div className="flex gap-3">
      <LogoMark className="mt-0.5 size-7 shrink-0 rounded-lg" />
      <div className="min-w-0 flex-1">
        <div className="overflow-hidden rounded-2xl border border-line bg-surface shadow-card">
          <div className="flex flex-wrap items-center gap-3 border-b border-line bg-gradient-to-r from-primary-soft/70 to-transparent px-4 py-3">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-white"><Activity className="size-4" /></div>
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-semibold text-ink">Agent mission · {task?.mode ?? "…"} mode</div>
              <div className="truncate text-[12px] text-muted">{task?.title}</div>
            </div>
            {task && <StatusBadge status={task.status} />}
            <Button asChild variant="secondary" size="sm">
              <Link href={`/missions/${taskId}`}>Mission Control <ArrowUpRight /></Link>
            </Button>
          </div>
          <div className="px-4 py-3.5">
            {m.content && m.status !== "streaming" ? (
              <Markdown content={m.content} onCite={(l) => { const c = m.citations.find((x) => x.label === l); if (c) onCite(c); }} known={new Set(m.citations.map((c) => c.label))} />
            ) : (
              <p className="text-[13px] text-muted">
                {task?.status === "waiting_approval" ? "Waiting for your approval in Mission Control before searching the web." :
                 task?.status === "paused" ? "Paused. Resume it from Mission Control." :
                 "Agents are working — follow each step live in Mission Control."}
              </p>
            )}
            {done && m.meta.artifact_id && (
              <Link href={`/artifacts/${m.meta.artifact_id}`} className="mt-3 inline-flex items-center gap-1.5 text-[13px] font-medium text-primary hover:underline">
                <FileText className="size-4" /> Open report artifact
              </Link>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
