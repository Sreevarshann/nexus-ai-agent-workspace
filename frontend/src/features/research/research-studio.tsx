"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BookOpenText, ExternalLink, FlaskConical, GitCompareArrows, Globe2, Link2, Loader2, Search, Zap } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/controls";
import { EmptyState, ErrorNote, PageHeader } from "@/components/ui/feedback";
import { Input, Textarea } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status";
import { api } from "@/lib/api";
import { useDocuments, useHealth, useProjects, useTasks } from "@/lib/queries";
import type { Source, Task } from "@/lib/types";
import { cn, domainOf, formatDateTime, timeAgo } from "@/lib/utils";
import { useUI } from "@/stores/ui";

const MODES = [
  { id: "quick", label: "Quick Research", icon: Zap, desc: "One focused query, three sources, concise synthesis. No verification pass.", budget: "1 query · 3 sources" },
  { id: "deep", label: "Deep Research", icon: FlaskConical, desc: "Multi-query investigation with a deterministic citation and numeric verifier.", budget: "≤4 queries · 8 sources · verified" },
  { id: "compare", label: "Compare", icon: GitCompareArrows, desc: "Per-entity research, a cited comparison matrix and charts of verified numbers.", budget: "≤6 queries · 9 sources · matrix" },
  { id: "doc_web", label: "Document + Web", icon: BookOpenText, desc: "Combines passages from your library with current web sources, kept distinct.", budget: "library + 2 queries · 5 sources" },
] as const;

export function ResearchStudio() {
  const router = useRouter();
  const qc = useQueryClient();
  const projectId = useUI((s) => s.activeProjectId);
  const { data: projects } = useProjects();
  const { data: health } = useHealth();
  const { data: docs } = useDocuments();
  const { data: tasks } = useTasks("mission");
  const [mode, setMode] = React.useState<(typeof MODES)[number]["id"]>("deep");
  const [prompt, setPrompt] = React.useState("");
  const [approval, setApproval] = React.useState(true);
  const [docIds, setDocIds] = React.useState<string[]>([]);
  const ready = docs?.filter((d) => d.status === "ready") ?? [];
  const searchOk = health?.checks.search?.ok;

  const start = useMutation({
    mutationFn: () =>
      api.post<Task>("/tasks", {
        prompt,
        mode,
        require_approval: approval,
        document_ids: docIds,
        project_id: projectId ?? projects?.[0]?.id,
      }),
    onSuccess: (t) => {
      void qc.invalidateQueries({ queryKey: ["tasks"] });
      router.push(`/missions/${t.id}`);
    },
    onError: (e) => toast.error((e as Error).message),
  });

  return (
    <div className="mx-auto max-w-6xl space-y-8 px-4 py-8 md:px-8">
      <PageHeader icon={FlaskConical} title="Deep Research Studio" description="Plan a research mission, choose how thorough it should be, and watch agents gather and verify real evidence." />

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <Card className="overflow-hidden">
          <div className="border-b border-line bg-gradient-to-br from-primary-soft/60 to-transparent p-5">
            <label htmlFor="research-prompt" className="text-[13px] font-semibold text-ink">Research question</label>
            <Textarea
              id="research-prompt"
              rows={4}
              className="mt-2 text-[14.5px]"
              placeholder="e.g. Research the latest AI agent frameworks, compare LangGraph with CrewAI and AutoGen on developer adoption, and write a cited report."
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
          </div>
          <div className="grid gap-3 p-5 sm:grid-cols-2" role="radiogroup" aria-label="Research mode">
            {MODES.map((m) => (
              <button
                key={m.id}
                role="radio"
                aria-checked={mode === m.id}
                onClick={() => setMode(m.id)}
                className={cn(
                  "rounded-xl border p-4 text-left transition",
                  mode === m.id ? "border-primary bg-primary-soft/50 ring-4 ring-[var(--primary-ring)]" : "border-line hover:border-line-strong",
                )}
              >
                <div className="flex items-center gap-2">
                  <m.icon className={cn("size-4", mode === m.id ? "text-primary" : "text-muted")} />
                  <span className="text-[13.5px] font-semibold text-ink">{m.label}</span>
                </div>
                <p className="mt-1.5 text-[12.5px] leading-snug text-muted">{m.desc}</p>
                <div className="mt-2.5 font-mono text-[10.5px] text-faint">{m.budget}</div>
              </button>
            ))}
          </div>
          {(mode === "doc_web" || docIds.length > 0) && (
            <div className="border-t border-line px-5 py-4">
              <div className="mb-2 text-[12.5px] font-medium text-ink-2">Documents to include {mode === "doc_web" && !docIds.length && <span className="text-faint">(defaults to your whole library)</span>}</div>
              <div className="flex flex-wrap gap-1.5">
                {ready.map((d) => {
                  const on = docIds.includes(d.id);
                  return (
                    <button key={d.id} onClick={() => setDocIds((x) => (on ? x.filter((y) => y !== d.id) : [...x, d.id]))} className={cn("rounded-lg border px-2.5 py-1 text-[12px] transition", on ? "border-primary bg-primary-soft text-primary-deep" : "border-line text-ink-2 hover:border-line-strong")}>
                      {d.filename}
                    </button>
                  );
                })}
                {!ready.length && <span className="text-[12px] text-faint">No indexed documents — upload some in the Knowledge Library.</span>}
              </div>
            </div>
          )}
          <div className="flex flex-wrap items-center gap-4 border-t border-line px-5 py-4">
            <label className="flex items-center gap-2 text-[13px] text-ink-2">
              <Switch checked={approval} onCheckedChange={setApproval} aria-label="Require approval before web access" />
              Approve the plan before any web access
            </label>
            <Button className="ml-auto" size="lg" disabled={prompt.trim().length < 5 || start.isPending} onClick={() => start.mutate()}>
              {start.isPending ? <Loader2 className="animate-spin" /> : <FlaskConical />} Launch mission
            </Button>
          </div>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader><div><CardTitle>Research provider</CardTitle><CardDescription>Live status from the API</CardDescription></div></CardHeader>
            <CardBody className="space-y-2 text-[13px]">
              <div className="flex items-center justify-between"><span className="text-muted">Search engine</span><Badge tone={searchOk ? "green" : "red"}>{String(health?.checks.search?.provider ?? "…")} · {searchOk ? "online" : "offline"}</Badge></div>
              <div className="flex items-center justify-between"><span className="text-muted">Model</span><span className="font-medium text-ink">{String(health?.checks.llm?.model ?? "…")}</span></div>
              {!searchOk && health && <p className="text-[12px] text-[#b45309]">Search is unavailable — missions will report it. You can still research specific URLs below.</p>}
            </CardBody>
          </Card>
          <Card>
            <CardHeader><CardTitle>Recent research</CardTitle></CardHeader>
            <div className="divide-y divide-line">
              {(tasks ?? []).slice(0, 6).map((t) => (
                <Link key={t.id} href={`/missions/${t.id}`} className="flex items-center gap-3 px-5 py-2.5 hover:bg-bg-subtle/60">
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[13px] text-ink">{t.title}</div>
                    <div className="text-[11.5px] text-faint">{t.mode} · {timeAgo(t.created_at)}</div>
                  </div>
                  <StatusBadge status={t.status} />
                </Link>
              ))}
              {!tasks?.length && <div className="px-5 pb-4 text-[12.5px] text-faint">No missions yet.</div>}
            </div>
          </Card>
        </div>
      </div>

      <Tabs defaultValue="sources">
        <TabsList>
          <TabsTrigger value="sources"><Globe2 /> Source library</TabsTrigger>
          <TabsTrigger value="url"><Link2 /> Research a URL</TabsTrigger>
          <TabsTrigger value="search"><Search /> Live search</TabsTrigger>
        </TabsList>
        <TabsContent value="sources" className="mt-4"><SourceLibrary /></TabsContent>
        <TabsContent value="url" className="mt-4"><UrlResearch /></TabsContent>
        <TabsContent value="search" className="mt-4"><LiveSearch /></TabsContent>
      </Tabs>
    </div>
  );
}

function SourceLibrary() {
  const { data, isPending, error } = useQuery({ queryKey: ["sources"], queryFn: () => api.get<Source[]>("/research/sources?limit=200") });
  const [filter, setFilter] = React.useState<"all" | "retrieved" | "failed">("all");
  const [q, setQ] = React.useState("");
  const rows = (data ?? []).filter((s) => (filter === "all" || (filter === "retrieved" ? s.status === "retrieved" : s.status !== "retrieved")) && (!q || `${s.title} ${s.domain}`.toLowerCase().includes(q.toLowerCase())));
  if (error) return <ErrorNote error={error} />;
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
        <Input placeholder="Filter by title or domain" value={q} onChange={(e) => setQ(e.target.value)} className="h-8 max-w-xs" />
        {(["all", "retrieved", "failed"] as const).map((f) => (
          <Button key={f} size="sm" variant={filter === f ? "soft" : "ghost"} onClick={() => setFilter(f)}>{f === "failed" ? "Failed / blocked" : f[0].toUpperCase() + f.slice(1)}</Button>
        ))}
        <span className="ml-auto text-[12px] text-faint">{rows.length} of {data?.length ?? 0} sources</span>
      </div>
      {isPending ? <div className="p-6 text-[13px] text-muted">Loading…</div> : !rows.length ? (
        <EmptyState icon={Globe2} title="No sources yet" description="Every page a mission or research chat retrieves is stored here with its status and retrieval time." />
      ) : (
        <div className="divide-y divide-line">
          {rows.map((s) => (
            <div key={s.id} className="flex items-start gap-3 px-4 py-3">
              <Globe2 className="mt-0.5 size-4 shrink-0 text-primary" />
              <div className="min-w-0 flex-1">
                <a href={s.final_url ?? s.url} target="_blank" rel="noopener noreferrer" className="line-clamp-1 text-[13px] font-medium text-ink hover:text-primary">{s.title || s.url}<ExternalLink className="ml-1 inline size-3 text-faint" /></a>
                <div className="mt-0.5 text-[11.5px] text-faint">{domainOf(s.url)} · retrieved {formatDateTime(s.retrieved_at)}{s.published_at ? ` · published ${s.published_at}` : ""}{s.search_query ? ` · query “${s.search_query}”` : ""}</div>
                {s.excerpt && <p className="mt-1 line-clamp-2 text-[12.5px] text-ink-2">{s.excerpt}</p>}
                {s.error && <p className="mt-1 text-[12px] text-[#b45309]">{s.error}</p>}
              </div>
              <StatusBadge status={s.status} />
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function UrlResearch() {
  const qc = useQueryClient();
  const [url, setUrl] = React.useState("");
  const fetchUrl = useMutation({
    mutationFn: () => api.post<{ status: string; title: string; excerpt: string; error: string | null; chars: number; final_url: string | null; domain: string; published_at: string | null }>("/research/fetch", { url }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["sources"] }),
  });
  const r = fetchUrl.data;
  return (
    <Card>
      <CardHeader><div><CardTitle>Direct URL research</CardTitle><CardDescription>Retrieve a specific public page or PDF through the SSRF-hardened fetcher (robots.txt respected, private networks blocked).</CardDescription></div></CardHeader>
      <CardBody className="space-y-4">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); fetchUrl.mutate(); }}>
          <Input placeholder="https://example.com/article" value={url} onChange={(e) => setUrl(e.target.value)} aria-label="URL" />
          <Button type="submit" disabled={!url.startsWith("http") || fetchUrl.isPending}>{fetchUrl.isPending ? <Loader2 className="animate-spin" /> : <ArrowRight />} Retrieve</Button>
        </form>
        {fetchUrl.error && <ErrorNote error={fetchUrl.error} title="Retrieval refused" />}
        {r && (
          <div className="rounded-xl border border-line p-4">
            <div className="flex items-center gap-2"><StatusBadge status={r.status} /><span className="text-[12px] text-muted">{r.domain} · {r.chars.toLocaleString()} characters extracted</span></div>
            <div className="mt-2 text-[14px] font-medium text-ink">{r.title}</div>
            {r.excerpt && <p className="mt-1.5 text-[13px] text-ink-2">{r.excerpt}</p>}
            {r.error && <p className="mt-1.5 text-[12.5px] text-[#b45309]">{r.error}</p>}
          </div>
        )}
      </CardBody>
    </Card>
  );
}

function LiveSearch() {
  const [q, setQ] = React.useState("");
  const search = useMutation({ mutationFn: () => api.post<{ results: { title: string; url: string; snippet: string; engine: string; domain: string }[] }>("/research/search", { query: q }) });
  return (
    <Card>
      <CardHeader><div><CardTitle>Live search</CardTitle><CardDescription>Results come straight from the configured search engine; nothing is generated.</CardDescription></div></CardHeader>
      <CardBody className="space-y-3">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); search.mutate(); }}>
          <Input placeholder="Search the web…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search query" />
          <Button type="submit" disabled={q.trim().length < 2 || search.isPending}>{search.isPending ? <Loader2 className="animate-spin" /> : <Search />} Search</Button>
        </form>
        {search.error && <ErrorNote error={search.error} title="Search unavailable" />}
        <div className="space-y-2.5">
          {search.data?.results.map((r) => (
            <a key={r.url} href={r.url} target="_blank" rel="noopener noreferrer" className="block rounded-xl border border-line p-3 hover:border-primary/40">
              <div className="text-[11.5px] text-faint">{r.domain} · via {r.engine}</div>
              <div className="text-[13.5px] font-medium text-primary-deep">{r.title}</div>
              <p className="mt-0.5 line-clamp-2 text-[12.5px] text-ink-2">{r.snippet}</p>
            </a>
          ))}
        </div>
      </CardBody>
    </Card>
  );
}
