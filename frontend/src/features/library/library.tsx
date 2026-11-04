"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpenText, FileText, Loader2, RefreshCw, Search, Trash2, Upload } from "lucide-react";
import dynamic from "next/dynamic";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/controls";
import { EmptyState, PageHeader, Skeleton } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status";
import { api } from "@/lib/api";
import { keys, useDocuments } from "@/lib/queries";
import type { DocumentItem, SearchHit } from "@/lib/types";
import { cn, formatBytes, timeAgo } from "@/lib/utils";

const PdfViewer = dynamic(() => import("@/features/library/pdf-viewer"), { ssr: false, loading: () => <Skeleton className="m-4 h-96" /> });

export function KnowledgeLibrary() {
  const params = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const { data: docs, isPending } = useDocuments();
  const selectedId = params.get("doc") ?? docs?.[0]?.id ?? null;
  const page = Number(params.get("page") ?? 1);
  const selected = docs?.find((d) => d.id === selectedId);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = React.useState(false);
  const [uploading, setUploading] = React.useState(0);

  React.useEffect(() => {
    if (params.get("upload")) fileRef.current?.click();
  }, [params]);

  const upload = async (files: FileList | File[]) => {
    for (const f of Array.from(files)) {
      setUploading((n) => n + 1);
      const form = new FormData();
      form.append("file", f);
      try {
        const d = await api.upload<DocumentItem>("/documents", form);
        toast.success(`${d.filename} uploaded`, { description: "Extracting, chunking and embedding locally…" });
      } catch (e) {
        toast.error(`Could not upload ${f.name}`, { description: (e as Error).message });
      } finally {
        setUploading((n) => n - 1);
        void qc.invalidateQueries({ queryKey: keys.documents });
      }
    }
  };

  const select = (id: string, p?: number) => router.replace(`/library?doc=${id}${p ? `&page=${p}` : ""}`, { scroll: false });

  return (
    <div className="mx-auto flex h-full max-w-[1500px] flex-col gap-6 px-4 py-8 md:px-8">
      <PageHeader
        icon={BookOpenText}
        title="Knowledge Library"
        description="Documents are validated, chunked page-by-page, embedded locally and indexed for hybrid vector + keyword retrieval."
        actions={
          <Button onClick={() => fileRef.current?.click()} disabled={uploading > 0}>
            {uploading ? <Loader2 className="animate-spin" /> : <Upload />} Upload documents
          </Button>
        }
      />
      <input ref={fileRef} type="file" multiple hidden accept=".pdf,.txt,.md,.markdown,.csv,.xlsx,.docx" onChange={(e) => { if (e.target.files) void upload(e.target.files); e.target.value = ""; }} />

      <div className="grid min-h-0 flex-1 gap-5 lg:grid-cols-[340px_1fr]">
        <div className="space-y-3">
          <div
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => { e.preventDefault(); setDragging(false); void upload(e.dataTransfer.files); }}
            onClick={() => fileRef.current?.click()}
            className={cn("cursor-pointer rounded-2xl border-2 border-dashed px-4 py-6 text-center transition", dragging ? "border-primary bg-primary-soft" : "border-line bg-surface hover:border-[#b9cdfc]")}
          >
            <Upload className="mx-auto size-5 text-primary" />
            <div className="mt-2 text-[13px] font-medium text-ink">Drop files here</div>
            <div className="text-[11.5px] text-muted">PDF, TXT, Markdown, DOCX, CSV, XLSX · up to 25 MB</div>
          </div>
          <Card className="overflow-hidden">
            {isPending ? <div className="space-y-2 p-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14" />)}</div> : !docs?.length ? (
              <EmptyState icon={FileText} title="Your library is empty" description="Upload documents to ground answers in your own sources." />
            ) : (
              <ul className="divide-y divide-line">
                {docs.map((d) => (
                  <li key={d.id}>
                    <button onClick={() => select(d.id)} className={cn("flex w-full items-start gap-3 px-4 py-3 text-left transition", d.id === selectedId ? "bg-primary-soft/60" : "hover:bg-bg-subtle/70")}>
                      <FileText className={cn("mt-0.5 size-4 shrink-0", d.mime === "application/pdf" ? "text-[#dc2626]" : "text-cyan")} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-[13px] font-medium text-ink">{d.filename}</div>
                        <div className="mt-0.5 text-[11.5px] text-faint">{formatBytes(d.size)} · {d.chunk_count} chunks{d.page_count ? ` · ${d.page_count} pages` : ""} · {timeAgo(d.created_at)}</div>
                        {d.error && <div className="mt-1 line-clamp-2 text-[11.5px] text-danger">{d.error}</div>}
                      </div>
                      <StatusBadge status={d.status} />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>

        <Card className="flex min-h-[640px] flex-col overflow-hidden">
          <Tabs defaultValue="preview" className="flex min-h-0 flex-1 flex-col">
            <div className="flex flex-wrap items-center gap-3 border-b border-line px-4 py-2.5">
              <TabsList>
                <TabsTrigger value="preview"><FileText /> Preview</TabsTrigger>
                <TabsTrigger value="chunks">Chunks</TabsTrigger>
                <TabsTrigger value="search"><Search /> Retrieval</TabsTrigger>
              </TabsList>
              {selected && (
                <div className="ml-auto flex items-center gap-1">
                  <span className="mr-2 hidden max-w-[260px] truncate text-[12.5px] text-muted md:inline">{selected.filename}</span>
                  <DocActions doc={selected} />
                </div>
              )}
            </div>
            <TabsContent value="preview" className="min-h-0 flex-1">
              {!selected ? <EmptyState icon={FileText} title="Select a document" /> : selected.mime === "application/pdf" ? (
                <PdfViewer url={`/api/documents/${selected.id}/file`} page={page} highlight={params.get("q") ?? undefined} />
              ) : (
                <ChunkList doc={selected} />
              )}
            </TabsContent>
            <TabsContent value="chunks" className="min-h-0 flex-1 overflow-y-auto">{selected && <ChunkList doc={selected} />}</TabsContent>
            <TabsContent value="search" className="min-h-0 flex-1 overflow-y-auto"><RetrievalLab onOpen={(h) => select(h.document_id, h.page ?? undefined)} /></TabsContent>
          </Tabs>
        </Card>
      </div>
    </div>
  );
}

function DocActions({ doc }: { doc: DocumentItem }) {
  const qc = useQueryClient();
  const router = useRouter();
  const reindex = useMutation({ mutationFn: () => api.post(`/documents/${doc.id}/reindex`), onSuccess: () => qc.invalidateQueries({ queryKey: keys.documents }) });
  const remove = useMutation({
    mutationFn: () => api.del(`/documents/${doc.id}`),
    onSuccess: () => {
      toast.success(`${doc.filename} deleted with its index entries`);
      void qc.invalidateQueries({ queryKey: keys.documents });
      router.replace("/library");
    },
  });
  return (
    <>
      <Button variant="ghost" size="sm" onClick={() => reindex.mutate()} disabled={reindex.isPending}><RefreshCw /> Re-index</Button>
      <Button variant="danger-ghost" size="sm" onClick={() => { if (window.confirm(`Delete ${doc.filename}? Its chunks and citations are removed too.`)) remove.mutate(); }}><Trash2 /> Delete</Button>
    </>
  );
}

function ChunkList({ doc }: { doc: DocumentItem }) {
  const { data, isPending } = useQuery({
    queryKey: ["chunks", doc.id, doc.chunk_count],
    queryFn: () => api.get<{ id: string; ord: number; page: number | null; text: string }[]>(`/documents/${doc.id}/chunks?limit=200`),
    enabled: doc.status === "ready",
  });
  if (doc.status !== "ready") return <div className="p-6"><StatusBadge status={doc.status} /> <span className="ml-2 text-[13px] text-muted">{doc.error ?? "Indexing in progress…"}</span></div>;
  if (isPending) return <div className="p-4"><Skeleton className="h-40" /></div>;
  return (
    <div className="space-y-2.5 p-4">
      {data?.map((c) => (
        <div key={c.id} className="rounded-xl border border-line p-3">
          <div className="mb-1.5 flex gap-2 text-[11px] text-faint"><span className="font-mono">chunk {c.ord}</span>{c.page && <Badge>page {c.page}</Badge>}</div>
          <p className="whitespace-pre-wrap text-[12.5px] leading-relaxed text-ink-2">{c.text}</p>
        </div>
      ))}
    </div>
  );
}

function RetrievalLab({ onOpen }: { onOpen: (h: SearchHit) => void }) {
  const [q, setQ] = React.useState("");
  const search = useMutation({ mutationFn: () => api.post<SearchHit[]>("/documents/search", { query: q, k: 8 }) });
  return (
    <div className="space-y-4 p-4">
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); search.mutate(); }}>
        <Input placeholder="Test hybrid retrieval across your library…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Retrieval query" />
        <Button type="submit" disabled={q.trim().length < 2 || search.isPending}>{search.isPending ? <Loader2 className="animate-spin" /> : <Search />} Retrieve</Button>
      </form>
      <p className="text-[12px] text-muted">Scores use reciprocal rank fusion of pgvector cosine similarity (nomic-embed-text) and Postgres full-text ranking.</p>
      {search.data?.length === 0 && <EmptyState icon={Search} title="No matching passages" />}
      <div className="space-y-2.5">
        {search.data?.map((h, i) => (
          <button key={h.chunk_id} onClick={() => onOpen(h)} className="block w-full rounded-xl border border-line p-3 text-left transition hover:border-primary/40">
            <div className="flex flex-wrap items-center gap-2 text-[11.5px]">
              <span className="font-semibold text-ink">#{i + 1}</span>
              <span className="text-ink-2">{h.filename}{h.page ? ` · p.${h.page}` : ""}</span>
              <Badge tone="blue">RRF {h.score.toFixed(4)}</Badge>
              {h.vector_rank && <Badge tone="cyan">vector #{h.vector_rank} · cos {h.similarity?.toFixed(3)}</Badge>}
              {h.keyword_rank && <Badge tone="violet">keyword #{h.keyword_rank}</Badge>}
            </div>
            <p className="mt-1.5 line-clamp-3 text-[12.5px] text-ink-2">{h.text}</p>
          </button>
        ))}
      </div>
    </div>
  );
}
