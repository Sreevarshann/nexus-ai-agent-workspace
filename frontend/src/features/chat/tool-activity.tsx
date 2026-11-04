"use client";

import { CheckCircle2, ChevronRight, FileSearch, Globe2, Loader2, OctagonX, Sigma, XCircle } from "lucide-react";
import * as React from "react";

import type { ToolEvent } from "@/features/chat/use-message-stream";
import { cn, domainOf } from "@/lib/utils";

/** Compact, expandable trace of the real tool events emitted while answering. */
export function ToolActivity({ tools, live }: { tools: ToolEvent[]; live?: boolean }) {
  const [open, setOpen] = React.useState(false);
  if (!tools.length) return null;
  const searches = tools.filter((t) => t.event === "tool_call" && t.tool === "web_search");
  const fetched = tools.filter((t) => t.event === "source_retrieved");
  const ok = fetched.filter((t) => t.status === "retrieved").length;
  const docHits = tools.filter((t) => t.event === "evidence").length;
  const ops = tools.filter((t) => t.event === "tool_call" && t.tool?.startsWith("analysis."));
  const parts = [
    searches.length && `${searches.length} web search${searches.length > 1 ? "es" : ""}`,
    fetched.length && `${ok}/${fetched.length} sources retrieved`,
    docHits && `${docHits} passages`,
    ops.length && `${ops.filter((o) => o.status === "ok").length} computations`,
  ].filter(Boolean);

  return (
    <div className="mb-3 rounded-xl border border-line bg-surface-2/70">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center gap-2 px-3 py-2 text-left text-[12.5px] text-ink-2" aria-expanded={open}>
        {live ? <Loader2 className="size-3.5 animate-spin text-primary" /> : <CheckCircle2 className="size-3.5 text-success" />}
        <span className="font-medium">{parts.join(" · ") || "Tool activity"}</span>
        <ChevronRight className={cn("ml-auto size-3.5 text-muted transition", open && "rotate-90")} />
      </button>
      {open && (
        <ol className="space-y-1 border-t border-line px-3 py-2.5">
          {tools.map((t, i) => (
            <li key={i} className="flex items-start gap-2 text-[12px] text-ink-2">
              <ToolIcon t={t} />
              <span className="min-w-0 flex-1">
                {t.event === "tool_call" && t.tool === "web_search" && <>Searched <q className="text-ink">{String(t.args?.query ?? "")}</q> — {String(t.result?.count ?? 0)} results</>}
                {t.event === "tool_call" && t.tool === "search_documents" && <>Searched library for <q className="text-ink">{String(t.args?.query ?? "")}</q></>}
                {t.event === "tool_call" && t.tool?.startsWith("analysis.") && <>Ran <code className="font-mono">{t.tool.slice(9)}</code>{t.error ? ` — ${t.error}` : ""}</>}
                {t.event === "source_retrieved" && (
                  <>
                    {t.status === "retrieved" ? "Retrieved" : t.status === "blocked" ? "Blocked" : "Failed"}{" "}
                    <a href={t.url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">{t.title || domainOf(t.url ?? "")}</a>
                    {t.error && <span className="text-muted"> — {t.error}</span>}
                  </>
                )}
                {t.event === "evidence" && <>Passage {t.label} from {t.filename}{t.page ? `, p. ${t.page}` : ""}</>}
                {t.event === "log" && <>{t.message}</>}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function ToolIcon({ t }: { t: ToolEvent }) {
  const cls = "mt-0.5 size-3.5 shrink-0";
  if (t.status === "error" || t.status === "failed") return <XCircle className={cn(cls, "text-danger")} />;
  if (t.status === "blocked") return <OctagonX className={cn(cls, "text-warning")} />;
  if (t.tool?.startsWith("analysis.")) return <Sigma className={cn(cls, "text-violet")} />;
  if (t.event === "evidence" || t.tool === "search_documents") return <FileSearch className={cn(cls, "text-cyan")} />;
  return <Globe2 className={cn(cls, "text-primary")} />;
}
