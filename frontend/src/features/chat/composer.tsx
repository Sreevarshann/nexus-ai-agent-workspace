"use client";

import * as PopoverPrimitive from "@radix-ui/react-popover";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Bot, Database, FileText, Globe2, Loader2, MessageSquare, Paperclip, Sigma, Square, Upload, X } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Kbd } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, Switch } from "@/components/ui/controls";
import { Tooltip } from "@/components/ui/overlay";
import { api } from "@/lib/api";
import { keys, useConfig, useDatasets, useDocuments } from "@/lib/queries";
import type { ChatMode, Dataset, DocumentItem } from "@/lib/types";
import { cn } from "@/lib/utils";

export type Attachment = { kind: "document" | "dataset"; id: string; name: string };
export type ComposerSubmit = { content: string; mode: ChatMode; attachments: Attachment[]; options: Record<string, unknown> };

const MODES: { id: ChatMode; label: string; icon: typeof Globe2; hint: string }[] = [
  { id: "chat", label: "Chat", icon: MessageSquare, hint: "Converse with the local model; attached documents are used as cited evidence" },
  { id: "research", label: "Research", icon: Globe2, hint: "Search the live web, retrieve sources and answer with citations" },
  { id: "analysis", label: "Analysis", icon: Sigma, hint: "Run computed analysis on an attached dataset and chart the results" },
  { id: "agent", label: "Agent", icon: Bot, hint: "Launch a multi-agent mission you can watch in Mission Control" },
];

export function Composer({
  onSubmit,
  onStop,
  busy,
  autoFocus,
  initialMode = "chat",
  compact,
}: {
  onSubmit: (v: ComposerSubmit) => Promise<void> | void;
  onStop?: () => void;
  busy?: boolean;
  autoFocus?: boolean;
  initialMode?: ChatMode;
  compact?: boolean;
}) {
  const [text, setText] = React.useState("");
  const [mode, setMode] = React.useState<ChatMode>(initialMode);
  const [attachments, setAttachments] = React.useState<Attachment[]>([]);
  const [missionMode, setMissionMode] = React.useState("deep");
  const [approval, setApproval] = React.useState(false);
  const [useLibrary, setUseLibrary] = React.useState(false);
  const [dragging, setDragging] = React.useState(false);
  const [uploading, setUploading] = React.useState(0);
  const ref = React.useRef<HTMLTextAreaElement>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const qc = useQueryClient();
  const { data: config } = useConfig();

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 260)}px`;
  }, [text]);

  const upload = async (files: FileList | File[]) => {
    for (const file of Array.from(files)) {
      setUploading((n) => n + 1);
      const isData = /\.(csv|xlsx)$/i.test(file.name) && (mode === "analysis" || mode === "agent");
      const form = new FormData();
      form.append("file", file);
      try {
        if (isData) {
          const ds = await api.upload<Dataset>("/datasets", form);
          setAttachments((a) => [...a, { kind: "dataset", id: ds.id, name: ds.name }]);
          void qc.invalidateQueries({ queryKey: keys.datasets });
        } else {
          const doc = await api.upload<DocumentItem>("/documents", form);
          setAttachments((a) => [...a, { kind: "document", id: doc.id, name: doc.filename }]);
          void qc.invalidateQueries({ queryKey: keys.documents });
          toast.success(`${doc.filename} added to your library`, { description: "Indexing runs in the background." });
        }
      } catch (e) {
        toast.error(`Could not upload ${file.name}`, { description: (e as Error).message });
      } finally {
        setUploading((n) => n - 1);
      }
    }
  };

  const submit = async () => {
    const content = text.trim();
    if (!content || busy) return;
    const options: Record<string, unknown> = {};
    if (mode === "agent") Object.assign(options, { mission_mode: missionMode, require_approval: approval });
    if (mode === "chat" && useLibrary) options.use_library = true;
    setText("");
    await onSubmit({ content, mode, attachments, options });
    setAttachments([]);
  };

  const current = MODES.find((m) => m.id === mode)!;
  return (
    <div
      className={cn(
        "relative rounded-2xl border bg-surface shadow-[0_1px_2px_rgb(15_23_42/0.04),0_12px_32px_-16px_rgb(30_58_138/0.25)] transition",
        dragging ? "border-primary ring-4 ring-[var(--primary-ring)]" : "border-line focus-within:border-[#b9cdfc]",
      )}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => { e.preventDefault(); setDragging(false); if (e.dataTransfer.files.length) void upload(e.dataTransfer.files); }}
    >
      {dragging && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-2xl bg-primary-soft/90 text-[13px] font-medium text-primary-deep">
          <Upload className="mr-2 size-4" /> Drop files to attach — PDF, TXT, MD, DOCX, CSV, XLSX
        </div>
      )}

      {(attachments.length > 0 || uploading > 0) && (
        <div className="flex flex-wrap gap-1.5 px-3 pt-3">
          {attachments.map((a) => (
            <span key={a.id} className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-surface-2 py-1 pl-2 pr-1 text-[12px] text-ink-2">
              {a.kind === "document" ? <FileText className="size-3.5 text-cyan" /> : <Database className="size-3.5 text-violet" />}
              <span className="max-w-[180px] truncate">{a.name}</span>
              <button onClick={() => setAttachments((x) => x.filter((y) => y.id !== a.id))} className="rounded p-0.5 text-muted hover:bg-line hover:text-ink" aria-label={`Remove ${a.name}`}>
                <X className="size-3" />
              </button>
            </span>
          ))}
          {uploading > 0 && <span className="inline-flex items-center gap-1.5 px-2 text-[12px] text-muted"><Loader2 className="size-3.5 animate-spin" /> Uploading…</span>}
        </div>
      )}

      <textarea
        ref={ref}
        value={text}
        autoFocus={autoFocus}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
            e.preventDefault();
            void submit();
          } else if (e.key === "Escape" && busy) onStop?.();
        }}
        rows={1}
        placeholder={
          mode === "research" ? "Ask a question to research on the live web…" :
          mode === "analysis" ? "Ask about your dataset — trends, comparisons, anomalies…" :
          mode === "agent" ? "Describe a multi-step mission for the agents…" :
          "Ask NEXUS anything…"
        }
        aria-label="Message"
        className={cn("block w-full resize-none bg-transparent px-4 text-[15px] leading-relaxed text-ink outline-none placeholder:text-faint", compact ? "pt-3 pb-2" : "pt-4 pb-3")}
      />

      <div className="flex flex-wrap items-center gap-2 px-3 pb-3">
        <div className="flex items-center rounded-xl border border-line bg-surface-2 p-0.5" role="radiogroup" aria-label="Mode">
          {MODES.map((m) => (
            <Tooltip key={m.id} content={m.hint}>
              <button
                role="radio"
                aria-checked={mode === m.id}
                onClick={() => setMode(m.id)}
                className={cn(
                  "flex h-7 items-center gap-1.5 rounded-[9px] px-2.5 text-[12.5px] font-medium transition",
                  mode === m.id ? "bg-surface text-primary-deep shadow-sm" : "text-muted hover:text-ink",
                )}
              >
                <m.icon className="size-3.5" />
                <span className="hidden sm:inline">{m.label}</span>
              </button>
            </Tooltip>
          ))}
        </div>

        <AttachMenu mode={mode} attachments={attachments} onAdd={(a) => setAttachments((x) => (x.some((y) => y.id === a.id) ? x : [...x, a]))} onUpload={() => fileRef.current?.click()} />
        <input ref={fileRef} type="file" multiple hidden accept=".pdf,.txt,.md,.markdown,.csv,.xlsx,.docx" onChange={(e) => { if (e.target.files) void upload(e.target.files); e.target.value = ""; }} />

        {mode === "agent" && (
          <>
            <Select
              ariaLabel="Mission mode"
              value={missionMode}
              onValueChange={setMissionMode}
              className="h-8 w-[130px]"
              options={[
                { value: "quick", label: "Quick research", hint: "1 query, 3 sources" },
                { value: "deep", label: "Deep research", hint: "Multi-query + verification" },
                { value: "compare", label: "Compare", hint: "Per-entity research + matrix" },
                { value: "doc_web", label: "Documents + Web", hint: "Library and live sources" },
              ]}
            />
            <label className="flex items-center gap-1.5 text-[12px] text-muted">
              <Switch checked={approval} onCheckedChange={setApproval} aria-label="Require approval before web research" />
              Approve plan
            </label>
          </>
        )}
        {mode === "chat" && (
          <label className="flex items-center gap-1.5 text-[12px] text-muted">
            <Switch checked={useLibrary} onCheckedChange={setUseLibrary} aria-label="Search my whole library" />
            Use library
          </label>
        )}

        <div className="ml-auto flex items-center gap-2">
          {!compact && config && (
            <span className="hidden text-[11.5px] text-faint lg:inline">{config.llm.model} · <Kbd>↵</Kbd> send</span>
          )}
          {busy ? (
            <Tooltip content="Stop generating (Esc)">
              <Button size="icon" variant="secondary" onClick={onStop} aria-label="Stop generation">
                <Square className="fill-current" />
              </Button>
            </Tooltip>
          ) : (
            <Tooltip content={`Send · ${current.label} mode`}>
              <Button size="icon" onClick={submit} disabled={!text.trim()} aria-label="Send message">
                <ArrowUp />
              </Button>
            </Tooltip>
          )}
        </div>
      </div>
    </div>
  );
}

function AttachMenu({ mode, attachments, onAdd, onUpload }: { mode: ChatMode; attachments: Attachment[]; onAdd: (a: Attachment) => void; onUpload: () => void }) {
  const { data: docs } = useDocuments();
  const { data: datasets } = useDatasets();
  const showData = mode === "analysis" || mode === "agent";
  const ids = new Set(attachments.map((a) => a.id));
  return (
    <PopoverPrimitive.Root>
      <Tooltip content="Attach files or library items">
        <PopoverPrimitive.Trigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label="Attach">
            <Paperclip />
          </Button>
        </PopoverPrimitive.Trigger>
      </Tooltip>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content side="top" align="start" sideOffset={8} className="z-50 w-80 rounded-xl border border-line bg-surface p-2 shadow-pop">
          <button onClick={onUpload} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-[13px] font-medium text-primary hover:bg-primary-soft">
            <Upload className="size-4" /> Upload from computer…
          </button>
          {showData && !!datasets?.length && (
            <Group title="Datasets">
              {datasets.map((d) => (
                <Row key={d.id} disabled={ids.has(d.id)} onClick={() => onAdd({ kind: "dataset", id: d.id, name: d.name })} icon={<Database className="size-3.5 text-violet" />} label={d.name} hint={`${d.row_count.toLocaleString()} rows`} />
              ))}
            </Group>
          )}
          <Group title="Documents">
            {docs?.filter((d) => d.status === "ready").map((d) => (
              <Row key={d.id} disabled={ids.has(d.id)} onClick={() => onAdd({ kind: "document", id: d.id, name: d.filename })} icon={<FileText className="size-3.5 text-cyan" />} label={d.filename} hint={`${d.chunk_count} chunks`} />
            ))}
            {!docs?.some((d) => d.status === "ready") && <div className="px-2.5 py-2 text-[12px] text-faint">No indexed documents yet.</div>}
          </Group>
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mt-1.5 border-t border-line pt-1.5">
      <div className="px-2.5 pb-1 text-[10.5px] font-semibold uppercase tracking-[0.08em] text-faint">{title}</div>
      <div className="nx-scroll max-h-44 overflow-y-auto">{children}</div>
    </div>
  );
}

function Row({ icon, label, hint, onClick, disabled }: { icon: React.ReactNode; label: string; hint: string; onClick: () => void; disabled?: boolean }) {
  return (
    <PopoverPrimitive.Close asChild>
      <button disabled={disabled} onClick={onClick} className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[12.5px] text-ink-2 hover:bg-bg-subtle disabled:opacity-40">
        {icon}
        <span className="min-w-0 flex-1 truncate">{label}</span>
        <span className="shrink-0 text-[11px] text-faint">{hint}</span>
      </button>
    </PopoverPrimitive.Close>
  );
}
