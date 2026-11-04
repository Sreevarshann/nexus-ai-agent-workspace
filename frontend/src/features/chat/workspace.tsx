"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpenText, Bot, Globe2, PanelRightClose, PanelRightOpen, Sigma } from "lucide-react";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/feedback";
import { Tooltip } from "@/components/ui/overlay";
import { Panel, ResizableGroup, ResizeHandle } from "@/components/ui/resizable";
import { CitationDialog } from "@/features/chat/citation-dialog";
import { Composer, type ComposerSubmit } from "@/features/chat/composer";
import { EvidencePanel } from "@/features/chat/evidence-panel";
import { AssistantMessage, UserMessage } from "@/features/chat/message";
import { api } from "@/lib/api";
import { useMediaQuery } from "@/lib/use-media";
import { keys } from "@/lib/queries";
import type { Citation, Conversation, Message } from "@/lib/types";
import { useUI } from "@/stores/ui";

async function sendTo(conversationId: string, v: ComposerSubmit) {
  return api.post<Message[]>(`/conversations/${conversationId}/messages`, {
    content: v.content,
    mode: v.mode,
    attachments: v.attachments.map(({ kind, id }) => ({ kind, id })),
    options: v.options,
  });
}

export function NewConversation() {
  const router = useRouter();
  const qc = useQueryClient();
  const projectId = useUI((s) => s.activeProjectId);

  const start = async (v: ComposerSubmit) => {
    try {
      const conv = await api.post<Conversation>("/conversations", { project_id: projectId ?? undefined });
      await sendTo(conv.id, v);
      void qc.invalidateQueries({ queryKey: ["conversations"] });
      router.push(`/workspace/${conv.id}`);
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const EXAMPLES = [
    { icon: Globe2, mode: "Research", text: "What changed in the Model Context Protocol specification this year?" },
    { icon: Bot, mode: "Agent", text: "Compare LangGraph and CrewAI for production agent systems and write a cited report." },
    { icon: Sigma, mode: "Analysis", text: "Identify seasonal trends and unusual months in my sales dataset." },
    { icon: BookOpenText, mode: "Chat", text: "Summarise the warranty terms in my uploaded whitepaper." },
  ];
  const [seed, setSeed] = React.useState<{ text: string; key: number } | null>(null);

  return (
    <div className="relative flex min-h-full flex-col items-center justify-center overflow-hidden px-4 py-12">
      <div className="nx-grid pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_at_center,black_10%,transparent_65%)]" />
      <div className="pointer-events-none absolute left-1/2 top-[18%] size-[520px] -translate-x-1/2 rounded-full bg-[radial-gradient(circle,rgb(37_99_235/0.12),transparent_65%)]" />
      <div className="relative w-full max-w-[760px]">
        <div className="mb-8 text-center">
          <div className="mx-auto mb-4 inline-flex items-center gap-2 rounded-full border border-[#d6e2ff] bg-surface px-3 py-1 text-[12px] font-medium text-primary-deep shadow-sm">
            <span className="size-1.5 rounded-full bg-cyan" /> Think · Plan · Research · Analyze · Verify · Create
          </div>
          <h1 className="text-[34px] font-semibold leading-tight tracking-[-0.035em] text-ink sm:text-[40px]">
            What should we <span className="bg-gradient-to-r from-primary to-cyan bg-clip-text text-transparent">investigate</span>?
          </h1>
          <p className="mt-3 text-[15px] text-muted">Every answer shows its sources, tool calls and computed values.</p>
        </div>
        <Composer key={seed?.key} autoFocus onSubmit={start} />
        {seed && <SeedEffect text={seed.text} />}
        <div className="mt-6 grid gap-2.5 sm:grid-cols-2">
          {EXAMPLES.map((e) => (
            <button
              key={e.text}
              onClick={() => setSeed({ text: e.text, key: Date.now() })}
              className="group flex items-start gap-3 rounded-xl border border-line bg-surface/80 p-3.5 text-left shadow-sm transition hover:-translate-y-px hover:border-[#c7d6fb] hover:shadow-card"
            >
              <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary"><e.icon className="size-4" /></div>
              <div>
                <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-faint">{e.mode}</div>
                <div className="mt-0.5 text-[13px] leading-snug text-ink-2 group-hover:text-ink">{e.text}</div>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/** Fills the composer textarea with an example prompt (keeps Composer state local and simple). */
function SeedEffect({ text }: { text: string }) {
  React.useEffect(() => {
    const el = document.querySelector<HTMLTextAreaElement>('textarea[aria-label="Message"]');
    if (!el) return;
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set;
    setter?.call(el, text);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.focus();
  }, [text]);
  return null;
}

export function ConversationView({ id }: { id: string }) {
  const qc = useQueryClient();
  const inspectorOpen = useUI((s) => s.inspectorOpen);
  const desktop = useMediaQuery("(min-width: 1024px)");
  const setInspector = useUI((s) => s.setInspector);
  const { data: messages, isPending, error } = useQuery({
    queryKey: keys.messages(id),
    queryFn: () => api.get<Message[]>(`/conversations/${id}/messages`),
  });
  const [citation, setCitation] = React.useState<Citation | null>(null);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const bottom = React.useRef<HTMLDivElement>(null);
  const scroller = React.useRef<HTMLDivElement>(null);
  const streaming = messages?.find((m) => m.role === "assistant" && m.status === "streaming" && !m.meta.task_id);
  const lastAssistant = [...(messages ?? [])].reverse().find((m) => m.role === "assistant");
  const selected = messages?.find((m) => m.id === selectedId) ?? lastAssistant;

  React.useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [messages?.length]);

  // keep pinned to the bottom while tokens stream in, unless the user scrolled up
  React.useEffect(() => {
    if (!streaming) return;
    const el = scroller.current;
    const t = setInterval(() => {
      if (el && el.scrollHeight - el.scrollTop - el.clientHeight < 160) el.scrollTop = el.scrollHeight;
    }, 250);
    return () => clearInterval(t);
  }, [streaming]);

  const send = async (v: ComposerSubmit) => {
    try {
      await sendTo(id, v);
      await qc.invalidateQueries({ queryKey: keys.messages(id) });
      void qc.invalidateQueries({ queryKey: ["conversations"] });
      if (v.mode === "agent") void qc.invalidateQueries({ queryKey: ["tasks"] });
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const stop = async () => {
    if (streaming) await api.post(`/messages/${streaming.id}/cancel`);
  };

  const thread = (
    <div className="flex h-full flex-col">
      <div ref={scroller} className="nx-scroll min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto w-full max-w-[820px] space-y-7 px-4 py-8 md:px-6">
          {isPending && [0, 1].map((i) => <Skeleton key={i} className="h-24" />)}
          {error && <div className="text-[13px] text-danger">{(error as Error).message}</div>}
          {messages?.map((m, i) =>
            m.role === "user" ? (
              <UserMessage key={m.id} m={m} />
            ) : (
              <AssistantMessage
                key={m.id}
                m={m}
                conversationId={id}
                onCite={setCitation}
                onSelect={() => setSelectedId(m.id)}
                selected={selected?.id === m.id}
                onSuggestion={(q) => void send({ content: q, mode: "chat", attachments: [], options: {} })}
                isLast={i === messages.length - 1}
              />
            ),
          )}
          <div ref={bottom} />
        </div>
      </div>
      <div className="border-t border-line/70 bg-gradient-to-t from-bg via-bg to-bg/70 px-4 pb-4 pt-3 md:px-6">
        <div className="mx-auto max-w-[820px]">
          <Composer onSubmit={send} onStop={stop} busy={!!streaming} compact />
        </div>
      </div>
    </div>
  );

  return (
    <div className="relative h-full">
      <div className="absolute right-3 top-3 z-10 hidden lg:block">
        <Tooltip content={inspectorOpen ? "Hide evidence" : "Show evidence"}>
          <Button variant="secondary" size="icon-sm" onClick={() => setInspector(!inspectorOpen)} aria-label="Toggle evidence panel">
            {inspectorOpen ? <PanelRightClose /> : <PanelRightOpen />}
          </Button>
        </Tooltip>
      </div>
      {desktop ? (
        inspectorOpen ? (
          <ResizableGroup id="workspace">
            <Panel id="thread" minSize="45" defaultSize="72">{thread}</Panel>
            <ResizeHandle />
            <Panel id="evidence" minSize="20" defaultSize="28" maxSize="45">
              <EvidencePanel message={selected} onCite={setCitation} />
            </Panel>
          </ResizableGroup>
        ) : (
          thread
        )
      ) : (
        thread
      )}
      <CitationDialog citation={citation} onClose={() => setCitation(null)} />
    </div>
  );
}
