"use client";

import { BookOpenText, ExternalLink, FileText, Globe2, Layers } from "lucide-react";

import { EmptyState } from "@/components/ui/feedback";
import type { Citation, Message } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

/** Right-hand inspector: every piece of evidence the selected answer actually cited. */
export function EvidencePanel({ message, onCite }: { message: Message | undefined; onCite: (c: Citation) => void }) {
  const cites = message?.citations ?? [];
  const analysis = message?.meta.analysis;
  return (
    <div className="flex h-full flex-col bg-surface/60">
      <div className="flex h-12 items-center gap-2 border-b border-line pl-4 pr-14">
        <Layers className="size-4 text-primary" />
        <span className="text-[13px] font-semibold text-ink">Evidence</span>
        {message && <span className="ml-auto text-[11.5px] text-faint">{cites.length} cited</span>}
      </div>
      <div className="nx-scroll flex-1 space-y-2.5 overflow-y-auto p-3">
        {!message || (!cites.length && !analysis) ? (
          <EmptyState icon={BookOpenText} title="No evidence selected" description="Select an answer to inspect the sources, passages and computed results behind it." className="py-10" />
        ) : (
          <>
            {cites.map((c) => (
              <button key={c.label} onClick={() => onCite(c)} className="block w-full rounded-xl border border-line bg-surface p-3 text-left shadow-sm transition hover:border-primary/40 hover:shadow-card">
                <div className="flex items-center gap-2">
                  <span className="rounded-md bg-primary-soft px-1.5 py-0.5 font-mono text-[10.5px] font-semibold text-primary-deep">{c.label}</span>
                  {c.kind === "web" ? <Globe2 className="size-3.5 text-primary" /> : <FileText className="size-3.5 text-cyan" />}
                  <span className="truncate text-[12px] text-muted">{c.kind === "web" ? c.domain : c.filename}</span>
                  {c.page != null && <span className="ml-auto shrink-0 text-[11px] text-faint">p. {c.page}</span>}
                </div>
                <div className="mt-1.5 line-clamp-2 text-[13px] font-medium text-ink">{c.title || c.filename}</div>
                <p className="mt-1 line-clamp-4 text-[12.5px] leading-relaxed text-ink-2">{c.excerpt}</p>
                {c.kind === "web" && (
                  <div className="mt-2 flex items-center justify-between text-[11px] text-faint">
                    <span>Retrieved {formatDateTime(c.retrieved_at)}</span>
                    <ExternalLink className="size-3" />
                  </div>
                )}
              </button>
            ))}
            {analysis?.results.map((r) => (
              <button key={r.label} onClick={() => onCite({ label: r.label, kind: "data", title: r.title, sql: r.sql })} className="block w-full rounded-xl border border-line bg-surface p-3 text-left shadow-sm hover:border-violet/40">
                <div className="flex items-center gap-2">
                  <span className="rounded-md bg-[#f5f3ff] px-1.5 py-0.5 font-mono text-[10.5px] font-semibold text-violet">{r.label}</span>
                  <span className="truncate text-[13px] font-medium text-ink">{r.title}</span>
                </div>
                <div className="mt-1 text-[11.5px] text-muted">{r.rows.length} rows · {r.op}{r.checks.length ? ` · ${r.checks.every((c) => c.passed) ? "checks passed" : "check failed"}` : ""}</div>
                <code className="mt-1.5 line-clamp-2 block font-mono text-[11px] text-faint">{r.sql}</code>
              </button>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
