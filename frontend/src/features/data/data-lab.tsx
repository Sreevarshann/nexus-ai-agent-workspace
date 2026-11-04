"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, Calendar, Database, Download, FileText, Hash, Loader2, Play, Sigma, Sparkles, Table2, Trash2, Type, Upload } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, Switch, Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/controls";
import { EmptyState, ErrorNote, PageHeader, Skeleton } from "@/components/ui/feedback";
import { Textarea } from "@/components/ui/input";
import { Markdown } from "@/features/chat/markdown";
import { ChartView, DataTable } from "@/features/data/chart";
import { api } from "@/lib/api";
import { keys, useDatasets } from "@/lib/queries";
import type { Analysis, AnalysisResult, Column, Dataset } from "@/lib/types";
import { cn, formatNumber, timeAgo } from "@/lib/utils";

const CodeEditor = dynamic(() => import("@/components/editor/code-editor"), { ssr: false, loading: () => <Skeleton className="h-[200px]" /> });

export function DataLab() {
  const params = useSearchParams();
  const router = useRouter();
  const qc = useQueryClient();
  const { data: datasets, isPending } = useDatasets();
  const selected = datasets?.find((d) => d.id === params.get("ds")) ?? datasets?.[0];
  const fileRef = React.useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: (f: File) => {
      const form = new FormData();
      form.append("file", f);
      return api.upload<Dataset>("/datasets", form);
    },
    onSuccess: (d) => {
      toast.success(`${d.name}: ${d.row_count.toLocaleString()} rows profiled`);
      void qc.invalidateQueries({ queryKey: keys.datasets });
      router.replace(`/data?ds=${d.id}`);
    },
    onError: (e) => toast.error((e as Error).message),
  });

  return (
    <div className="mx-auto max-w-[1500px] space-y-6 px-4 py-8 md:px-8">
      <PageHeader
        icon={Database}
        title="Data Lab"
        description="Datasets are converted to Parquet and queried with DuckDB in a sandbox: no file or network access, read-only SQL, timeouts."
        actions={
          <>
            {datasets && datasets.length > 1 && (
              <Select ariaLabel="Dataset" value={selected?.id} onValueChange={(v) => router.replace(`/data?ds=${v}`)} options={datasets.map((d) => ({ value: d.id, label: d.name, hint: `${d.row_count.toLocaleString()} rows` }))} className="w-[240px]" />
            )}
            <Button onClick={() => fileRef.current?.click()} disabled={upload.isPending}>{upload.isPending ? <Loader2 className="animate-spin" /> : <Upload />} Upload CSV / XLSX</Button>
          </>
        }
      />
      <input ref={fileRef} type="file" hidden accept=".csv,.xlsx" onChange={(e) => { const f = e.target.files?.[0]; if (f) upload.mutate(f); e.target.value = ""; }} />

      {isPending ? <Skeleton className="h-96" /> : !selected ? (
        <Card><EmptyState icon={Database} title="No datasets yet" description="Upload a CSV or Excel file — or run `make seed` to load the synthetic sales dataset." action={<Button onClick={() => fileRef.current?.click()}><Upload /> Upload a dataset</Button>} /></Card>
      ) : (
        <DatasetView key={selected.id} ds={selected} />
      )}
    </div>
  );
}

function DatasetView({ ds }: { ds: Dataset }) {
  const qc = useQueryClient();
  const router = useRouter();
  const remove = useMutation({
    mutationFn: () => api.del(`/datasets/${ds.id}`),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: keys.datasets }); router.replace("/data"); },
  });
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label="Rows" value={ds.row_count.toLocaleString()} />
        <Tile label="Columns" value={String(ds.columns.length)} hint={`${ds.profile.numeric.length} numeric · ${ds.profile.categorical.length} categorical · ${ds.profile.temporal.length} temporal`} />
        <Tile label="Missing cells" value={ds.profile.missing_cells.toLocaleString()} hint={ds.profile.missing_cells ? "see column profile" : "complete dataset"} />
        <Tile label="Uploaded" value={timeAgo(ds.created_at)} hint={ds.filename} action={<Button variant="danger-ghost" size="icon-sm" aria-label="Delete dataset" onClick={() => { if (window.confirm(`Delete ${ds.name}?`)) remove.mutate(); }}><Trash2 /></Button>} />
      </div>
      <Tabs defaultValue="analyst">
        <TabsList className="flex-wrap">
          <TabsTrigger value="analyst"><Sparkles /> AI Analyst</TabsTrigger>
          <TabsTrigger value="profile"><Sigma /> Profile</TabsTrigger>
          <TabsTrigger value="preview"><Table2 /> Preview</TabsTrigger>
          <TabsTrigger value="charts"><BarChart3 /> Chart builder</TabsTrigger>
          <TabsTrigger value="sql">SQL console</TabsTrigger>
        </TabsList>
        <TabsContent value="analyst" className="mt-4"><Analyst ds={ds} /></TabsContent>
        <TabsContent value="profile" className="mt-4"><Profile ds={ds} /></TabsContent>
        <TabsContent value="preview" className="mt-4"><Preview ds={ds} /></TabsContent>
        <TabsContent value="charts" className="mt-4"><ChartBuilder ds={ds} /></TabsContent>
        <TabsContent value="sql" className="mt-4"><SqlConsole ds={ds} /></TabsContent>
      </Tabs>
    </>
  );
}

function Tile({ label, value, hint, action }: { label: string; value: string; hint?: string; action?: React.ReactNode }) {
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between">
        <div className="text-[12px] font-medium text-muted">{label}</div>
        {action}
      </div>
      <div className="mt-1 text-[24px] font-semibold tracking-[-0.02em] text-ink tabular-nums">{value}</div>
      {hint && <div className="mt-0.5 truncate text-[11.5px] text-faint">{hint}</div>}
    </Card>
  );
}

const KIND_ICON = { numeric: Hash, categorical: Type, temporal: Calendar, boolean: Hash } as const;

function Profile({ ds }: { ds: Dataset }) {
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {ds.columns.map((c) => <ColumnCard key={c.name} c={c} rows={ds.row_count} />)}
    </div>
  );
}

function ColumnCard({ c, rows }: { c: Column; rows: number }) {
  const Icon = KIND_ICON[c.kind];
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2">
        <div className="flex size-7 items-center justify-center rounded-lg bg-primary-soft text-primary"><Icon className="size-3.5" /></div>
        <div className="min-w-0 flex-1 truncate font-mono text-[13px] font-medium text-ink">{c.name}</div>
        <Badge>{c.type}</Badge>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-2 text-[11.5px]">
        <Mini k="distinct" v={c.distinct.toLocaleString()} />
        <Mini k="nulls" v={`${c.nulls.toLocaleString()} (${c.null_pct}%)`} />
        <Mini k="kind" v={c.kind} />
        {c.kind === "numeric" && (
          <>
            <Mini k="min" v={formatNumber(c.min)} />
            <Mini k="mean" v={formatNumber(c.mean)} />
            <Mini k="max" v={formatNumber(c.max)} />
          </>
        )}
        {c.kind === "temporal" && (
          <>
            <Mini k="from" v={String(c.min).slice(0, 10)} />
            <Mini k="to" v={String(c.max).slice(0, 10)} />
          </>
        )}
      </div>
      {c.top && (
        <div className="mt-3 space-y-1">
          {c.top.map((t) => (
            <div key={String(t.value)} className="flex items-center gap-2 text-[11.5px]">
              <span className="w-28 truncate text-ink-2">{String(t.value)}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-bg-subtle"><div className="h-full rounded-full bg-primary/70" style={{ width: `${(100 * t.count) / rows}%` }} /></div>
              <span className="w-12 text-right tabular-nums text-faint">{t.count.toLocaleString()}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function Mini({ k, v }: { k: string; v: string }) {
  return <div className="rounded-md bg-surface-2 px-2 py-1.5"><div className="text-faint">{k}</div><div className="truncate font-medium text-ink-2">{v}</div></div>;
}

function Preview({ ds }: { ds: Dataset }) {
  const [offset, setOffset] = React.useState(0);
  const { data, isPending } = useQuery({ queryKey: ["preview", ds.id, offset], queryFn: () => api.get<{ columns: string[]; rows: unknown[][] }>(`/datasets/${ds.id}/preview?limit=100&offset=${offset}`) });
  return (
    <Card className="overflow-hidden">
      {isPending ? <Skeleton className="m-4 h-64" /> : <DataTable columns={data!.columns} rows={data!.rows} maxHeight={520} />}
      <div className="flex items-center justify-between border-t border-line px-4 py-2.5 text-[12.5px] text-muted">
        <span>Rows {offset + 1}–{Math.min(offset + 100, ds.row_count)} of {ds.row_count.toLocaleString()}</span>
        <div className="flex gap-2">
          <Button size="sm" variant="secondary" disabled={offset === 0} onClick={() => setOffset((o) => Math.max(0, o - 100))}>Previous</Button>
          <Button size="sm" variant="secondary" disabled={offset + 100 >= ds.row_count} onClick={() => setOffset((o) => o + 100)}>Next</Button>
        </div>
      </div>
    </Card>
  );
}

function Analyst({ ds }: { ds: Dataset }) {
  const [q, setQ] = React.useState("Analyze this sales dataset, identify seasonal trends, compare regions, and detect unusual changes.");
  const [save, setSave] = React.useState(true);
  const run = useMutation({ mutationFn: () => api.post<Analysis & { narrative: string; artifact_id?: string }>(`/datasets/${ds.id}/analyze`, { question: q, save_artifact: save }) });
  const r = run.data;
  return (
    <div className="space-y-4">
      <Card className="p-4">
        <Textarea rows={2} value={q} onChange={(e) => setQ(e.target.value)} aria-label="Analysis question" />
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-[12.5px] text-ink-2"><Switch checked={save} onCheckedChange={setSave} aria-label="Save as artifact" /> Save as artifact</label>
          <span className="text-[12px] text-faint">The model only selects operations; every number is computed by DuckDB.</span>
          <Button className="ml-auto" onClick={() => run.mutate()} disabled={run.isPending || q.trim().length < 3}>{run.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />} {run.isPending ? "Analysing…" : "Run analysis"}</Button>
        </div>
      </Card>
      {run.error && <ErrorNote error={run.error} />}
      {run.isPending && <div className="grid gap-3 md:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-64" />)}</div>}
      {r && (
        <>
          <Card className="p-4">
            <div className="mb-2 flex flex-wrap items-center gap-2 text-[12.5px]">
              <span className="font-semibold text-ink">Plan</span>
              <span className="text-muted">{r.plan.objective}</span>
              {r.fallback_plan && <Badge tone="amber">Model selection unusable — keyword heuristic used</Badge>}
              {r.artifact_id && <Link href={`/artifacts/${r.artifact_id}`} className="ml-auto inline-flex items-center gap-1 font-medium text-primary hover:underline"><FileText className="size-3.5" /> Open artifact</Link>}
            </div>
            {r.narrative ? <Markdown content={r.narrative} known={new Set(r.results.map((x) => x.label))} /> : <p className="text-[13px] text-muted">No narrative generated.</p>}
            {r.errors.length > 0 && <div className="mt-3 text-[12px] text-[#b45309]">{r.errors.join(" · ")}</div>}
          </Card>
          <div className="grid gap-4 lg:grid-cols-2">{r.results.map((x) => <ResultCard key={x.label} r={x} />)}</div>
        </>
      )}
    </div>
  );
}

function ResultCard({ r }: { r: AnalysisResult }) {
  return (
    <div className="space-y-2">
      {r.chart ? <ChartView spec={{ ...r.chart, title: r.title, columns: r.columns, rows: r.rows, label: r.label }} height={260} /> : (
        <Card><div className="border-b border-line px-3.5 py-2 text-[13px] font-medium text-ink">{r.label} {r.title}</div><DataTable columns={r.columns} rows={r.rows} maxHeight={260} /></Card>
      )}
      <details className="rounded-lg border border-line bg-surface px-3 py-2 text-[12px]">
        <summary className="cursor-pointer text-muted">SQL, checks and insights</summary>
        <pre className="mt-2 overflow-x-auto rounded-md bg-[#0b1220] p-2.5 font-mono text-[11px] text-[#e2e8f0]">{r.sql}</pre>
        {r.checks.map((c) => <div key={c.check} className={cn("mt-1.5", c.passed ? "text-[#047857]" : "text-danger")}>{c.passed ? "✓" : "✗"} {c.check}</div>)}
        {Object.keys(r.insights).length > 0 && <pre className="mt-1.5 whitespace-pre-wrap font-mono text-[11px] text-ink-2">{JSON.stringify(r.insights, null, 2)}</pre>}
      </details>
    </div>
  );
}

function ChartBuilder({ ds }: { ds: Dataset }) {
  const nums = ds.columns.filter((c) => c.kind === "numeric").map((c) => c.name);
  const cats = ds.columns.filter((c) => c.kind === "categorical" || c.kind === "boolean").map((c) => c.name);
  const dates = ds.columns.filter((c) => c.kind === "temporal").map((c) => c.name);
  const [op, setOp] = React.useState(dates.length ? "timeseries" : "aggregate");
  const [dim, setDim] = React.useState(cats[0] ?? "");
  const [date, setDate] = React.useState(dates[0] ?? "");
  const [metric, setMetric] = React.useState(nums[0] ?? "*");
  const [agg, setAgg] = React.useState(nums.length ? "sum" : "count");
  const [split, setSplit] = React.useState("none");
  const [gran, setGran] = React.useState("month");
  const [y2, setY2] = React.useState(nums[1] ?? nums[0] ?? "");

  const build = () => {
    const m = { column: agg === "count" ? "*" : metric, agg };
    if (op === "timeseries") return { op, date_column: date, granularity: gran, metric: m, split_by: split === "none" ? null : split, title: `${agg} of ${metric} by ${gran}` };
    if (op === "aggregate") return { op, group_by: [dim], metrics: [m], title: `${agg} of ${metric} by ${dim}` };
    if (op === "top_n") return { op, column: dim, metric: m, n: 10, title: `Top ${dim} by ${agg} ${metric}` };
    if (op === "correlation") return { op, x: metric, y: y2, title: `${metric} vs ${y2}` };
    if (op === "anomalies") return { op, date_column: date, granularity: gran, metric: m, title: `Anomalies in ${agg} ${metric}` };
    return { op: "distribution", column: metric, title: `Distribution of ${metric}` };
  };
  const run = useMutation({ mutationFn: () => api.post<AnalysisResult>(`/datasets/${ds.id}/operation`, { operation: build() }) });
  const opt = (xs: string[]) => xs.map((x) => ({ value: x, label: x }));

  return (
    <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
      <Card className="space-y-3 p-4">
        <Field label="Analysis">
          <Select ariaLabel="Operation" value={op} onValueChange={setOp} className="w-full" options={[
            ...(dates.length ? [{ value: "timeseries", label: "Trend over time" }, { value: "anomalies", label: "Anomaly detection" }] : []),
            ...(cats.length ? [{ value: "aggregate", label: "Compare categories" }, { value: "top_n", label: "Top N" }] : []),
            ...(nums.length >= 2 ? [{ value: "correlation", label: "Correlation" }] : []),
            ...(nums.length ? [{ value: "distribution", label: "Distribution" }] : []),
          ]} />
        </Field>
        {["timeseries", "anomalies"].includes(op) && (
          <>
            <Field label="Date column"><Select ariaLabel="Date column" value={date} onValueChange={setDate} className="w-full" options={opt(dates)} /></Field>
            <Field label="Granularity"><Select ariaLabel="Granularity" value={gran} onValueChange={setGran} className="w-full" options={opt(["day", "week", "month", "quarter", "year"])} /></Field>
          </>
        )}
        {["aggregate", "top_n"].includes(op) && <Field label="Group by"><Select ariaLabel="Group by" value={dim} onValueChange={setDim} className="w-full" options={opt(cats)} /></Field>}
        {op !== "distribution" && op !== "correlation" && (
          <Field label="Aggregation"><Select ariaLabel="Aggregation" value={agg} onValueChange={setAgg} className="w-full" options={opt(nums.length ? ["sum", "avg", "min", "max", "median", "count"] : ["count"])} /></Field>
        )}
        {(agg !== "count" || op === "distribution" || op === "correlation") && nums.length > 0 && (
          <Field label={op === "correlation" ? "X" : "Measure"}><Select ariaLabel="Measure" value={metric} onValueChange={setMetric} className="w-full" options={opt(nums)} /></Field>
        )}
        {op === "correlation" && <Field label="Y"><Select ariaLabel="Y measure" value={y2} onValueChange={setY2} className="w-full" options={opt(nums)} /></Field>}
        {op === "timeseries" && cats.length > 0 && (
          <Field label="Split by"><Select ariaLabel="Split by" value={split} onValueChange={setSplit} className="w-full" options={[{ value: "none", label: "No split" }, ...opt(cats)]} /></Field>
        )}
        <Button className="w-full" onClick={() => run.mutate()} disabled={run.isPending}>{run.isPending ? <Loader2 className="animate-spin" /> : <Play />} Compute chart</Button>
      </Card>
      <div>
        {run.error && <ErrorNote error={run.error} />}
        {run.data ? <ResultCard r={{ ...run.data, label: "" }} /> : <Card><EmptyState icon={BarChart3} title="Build a chart" description="Pick an analysis and columns. Values are computed server-side with DuckDB." /></Card>}
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1"><div className="text-[12px] font-medium text-ink-2">{label}</div>{children}</div>;
}

function SqlConsole({ ds }: { ds: Dataset }) {
  const first = ds.columns.find((c) => c.kind === "categorical")?.name;
  const num = ds.columns.find((c) => c.kind === "numeric")?.name;
  const [sql, setSql] = React.useState(first && num ? `SELECT "${first}", sum("${num}") AS total\nFROM dataset\nGROUP BY 1\nORDER BY total DESC` : "SELECT * FROM dataset LIMIT 50");
  const run = useMutation({ mutationFn: () => api.post<{ sql: string; columns: string[]; rows: unknown[][]; row_count: number }>(`/datasets/${ds.id}/query`, { sql }) });
  return (
    <div className="space-y-4">
      <Card className="overflow-hidden">
        <CardHeader className="pb-2">
          <div><CardTitle>Read-only SQL</CardTitle><CardDescription>One SELECT over the table <code className="font-mono">dataset</code>. Writes, file and network functions are rejected; results are capped at 5,000 rows.</CardDescription></div>
        </CardHeader>
        <div className="border-y border-line"><CodeEditor language="sql" value={sql} onChange={setSql} height={180} onRun={() => run.mutate()} /></div>
        <CardBody className="flex flex-wrap items-center gap-2 pt-3">
          <span className="text-[12px] text-faint">⌘↵ to run</span>
          <Button variant="secondary" className="ml-auto" onClick={exportCsvWith(sql, ds)}><Download /> Export CSV</Button>
          <Button onClick={() => run.mutate()} disabled={run.isPending}>{run.isPending ? <Loader2 className="animate-spin" /> : <Play />} Run query</Button>
        </CardBody>
      </Card>
      {run.error && <ErrorNote error={run.error} title="Query rejected" />}
      {run.data && (
        <Card className="overflow-hidden">
          <div className="border-b border-line px-4 py-2 text-[12px] text-muted">{run.data.row_count.toLocaleString()} rows · executed <code className="font-mono">{run.data.sql}</code></div>
          <DataTable columns={run.data.columns} rows={run.data.rows} maxHeight={420} />
        </Card>
      )}
    </div>
  );
}

/** Export the result of the current (guarded) query as CSV. */
function exportCsvWith(sql: string, ds: Dataset) {
  return async () => {
    const res = await fetch(`/api/datasets/${ds.id}/export`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sql }) });
    if (!res.ok) {
      toast.error((await res.json()).detail ?? "Export failed");
      return;
    }
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = `${ds.name}-export.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("CSV exported");
  };
}
