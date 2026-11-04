"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileText, Globe2, Sigma } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent } from "@/components/ui/overlay";
import { Skeleton } from "@/components/ui/feedback";
import { api } from "@/lib/api";
import type { Citation, Source } from "@/lib/types";
import { formatDateTime } from "@/lib/utils";

/** Shows the exact stored passage behind a citation — fetched from the backend, never reconstructed. */
export function CitationDialog({ citation, onClose }: { citation: Citation | null; onClose: () => void }) {
  const chunk = useQuery({
    queryKey: ["chunk", citation?.chunk_id],
    queryFn: () => api.get<{ text: string; filename: string; page: number | null; document_id: string }>(`/documents/chunks/${citation!.chunk_id}`),
    enabled: !!citation?.chunk_id,
  });
  const source = useQuery({
    queryKey: ["source", citation?.source_id],
    queryFn: () => api.get<Source>(`/research/sources/${citation!.source_id}`),
    enabled: !!citation?.source_id,
  });

  return (
    <Dialog open={!!citation} onOpenChange={(o) => !o && onClose()}>
      {citation && (
        <DialogContent
          wide
          title={`[${citation.label}] ${citation.title || citation.filename || "Citation"}`}
          description={
            citation.kind === "web"
              ? `Web source · retrieved ${formatDateTime(citation.retrieved_at)}`
              : citation.kind === "doc"
                ? `Knowledge library${citation.page ? ` · page ${citation.page}` : ""}`
                : "Computed data result"
          }
        >
          <div className="mb-4 flex flex-wrap items-center gap-2">
            {citation.kind === "web" && <Badge tone="blue"><Globe2 /> {citation.domain}</Badge>}
            {citation.kind === "doc" && <Badge tone="cyan"><FileText /> {citation.filename}</Badge>}
            {citation.kind === "data" && <Badge tone="violet"><Sigma /> DuckDB result</Badge>}
            {citation.page != null && <Badge>Page {citation.page}</Badge>}
            {citation.flags?.map((f) => <Badge key={f} tone="amber">{f.slice(0, 80)}</Badge>)}
          </div>

          {citation.kind === "doc" && (
            <div>
              <div className="mb-1.5 text-[11.5px] font-medium uppercase tracking-wide text-faint">Cited passage</div>
              {chunk.isPending ? <Skeleton className="h-28" /> : (
                <blockquote className="whitespace-pre-wrap rounded-xl border border-line bg-surface-2 p-4 text-[13.5px] leading-relaxed text-ink-2">
                  {chunk.data?.text ?? citation.excerpt}
                </blockquote>
              )}
              {citation.document_id && (
                <Link href={`/library?doc=${citation.document_id}${citation.page ? `&page=${citation.page}` : ""}`} className="mt-3 inline-flex items-center gap-1.5 text-[13px] font-medium text-primary hover:underline">
                  Open document{citation.page ? ` at page ${citation.page}` : ""} <ExternalLink className="size-3.5" />
                </Link>
              )}
            </div>
          )}

          {citation.kind === "web" && (
            <div>
              <div className="mb-1.5 text-[11.5px] font-medium uppercase tracking-wide text-faint">Passage used as evidence</div>
              <blockquote className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-xl border border-line bg-surface-2 p-4 text-[13.5px] leading-relaxed text-ink-2">
                {citation.excerpt}
              </blockquote>
              {source.data && (
                <dl className="mt-4 grid grid-cols-2 gap-3 text-[12.5px]">
                  <Meta k="Retrieval status" v={source.data.status} />
                  <Meta k="HTTP status" v={source.data.http_status ?? "—"} />
                  <Meta k="Published" v={source.data.published_at ?? "Not stated by the page"} />
                  <Meta k="Stored text" v={`${(source.data.content?.length ?? 0).toLocaleString()} characters`} />
                </dl>
              )}
              {citation.url && (
                <a href={citation.url} target="_blank" rel="noopener noreferrer" className="mt-4 inline-flex items-center gap-1.5 break-all text-[13px] font-medium text-primary hover:underline">
                  {citation.url} <ExternalLink className="size-3.5 shrink-0" />
                </a>
              )}
            </div>
          )}

          {citation.kind === "data" && citation.sql && (
            <pre className="overflow-x-auto rounded-xl bg-[#0b1220] p-4 font-mono text-[12px] text-[#e2e8f0]">{citation.sql}</pre>
          )}
        </DialogContent>
      )}
    </Dialog>
  );
}

function Meta({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-line px-3 py-2">
      <dt className="text-[11px] text-faint">{k}</dt>
      <dd className="mt-0.5 font-medium text-ink-2">{v}</dd>
    </div>
  );
}
