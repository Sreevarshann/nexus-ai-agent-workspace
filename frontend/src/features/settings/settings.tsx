"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Cpu, KeyRound, Loader2, Plug, Plus, RefreshCw, Server, Settings as SettingsIcon, Trash2 } from "lucide-react";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/controls";
import { PageHeader, Skeleton } from "@/components/ui/feedback";
import { Input } from "@/components/ui/input";
import { StatusDot } from "@/components/ui/status";
import { api } from "@/lib/api";
import { keys, useConfig, useHealth, useMe } from "@/lib/queries";
import { cn, formatDateTime, formatDuration, timeAgo } from "@/lib/utils";

type ToolsInfo = {
  tools: { name: string; description: string; external: boolean; mcp_exposed: boolean; calls: number; errors?: number; last_called_at?: string }[];
  mcp: { endpoint: string; transport: string; auth: string; tokens: number; recent_calls: { tool: string; status: string; duration_ms: number; created_at: string; error: string | null }[] };
  recent_errors: { tool: string; origin: string; error: string; created_at: string }[];
};
type Metrics = {
  tools: { tool: string; calls: number; avg_ms: number; p95_ms: number; errors: number }[];
  tasks: { kind: string; status: string; count: number }[];
  generation: { assistant_messages: number; avg_latency_ms: number; completion_tokens: number; errors: number };
  sources: Record<string, number>;
};

export function SettingsPage() {
  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-8 md:px-8">
      <PageHeader icon={SettingsIcon} title="Settings" description="Model provider, service health, MCP connectors, API tokens and observability." />
      <Tabs defaultValue="model">
        <TabsList className="flex-wrap">
          <TabsTrigger value="model"><Cpu /> Model & services</TabsTrigger>
          <TabsTrigger value="mcp"><Plug /> MCP connectors</TabsTrigger>
          <TabsTrigger value="tokens"><KeyRound /> API tokens</TabsTrigger>
          <TabsTrigger value="metrics"><Server /> Observability</TabsTrigger>
        </TabsList>
        <TabsContent value="model" className="mt-4"><ModelPanel /></TabsContent>
        <TabsContent value="mcp" className="mt-4"><McpPanel /></TabsContent>
        <TabsContent value="tokens" className="mt-4"><TokensPanel /></TabsContent>
        <TabsContent value="metrics" className="mt-4"><MetricsPanel /></TabsContent>
      </Tabs>
    </div>
  );
}

function ModelPanel() {
  const { data: cfg } = useConfig();
  const { data: health, refetch, isFetching } = useHealth();
  const { data: me } = useMe();
  const llm = health?.checks.llm;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div><CardTitle>Language model</CardTitle><CardDescription>Configured through environment variables (see .env.example). Changes require an API restart.</CardDescription></div>
          <Button variant="secondary" size="sm" onClick={() => refetch()}>{isFetching ? <Loader2 className="animate-spin" /> : <RefreshCw />} Re-check</Button>
        </CardHeader>
        <CardBody>
          {!cfg ? <Skeleton className="h-24" /> : (
            <dl className="grid gap-3 sm:grid-cols-3">
              <Row k="Provider" v={<span className="flex items-center gap-2">{cfg.llm.provider}{cfg.llm.external && <Badge tone="amber">external</Badge>}</span>} />
              <Row k="Chat model" v={cfg.llm.model} />
              <Row k="Embedding model" v={cfg.llm.embed_model} />
              <Row k="Temperature" v={cfg.llm.temperature} />
              <Row k="Context window" v={`${cfg.llm.num_ctx.toLocaleString()} tokens`} />
              <Row k="Request timeout" v={`${cfg.llm.timeout_s}s`} />
              <Row k="Connection" v={<span className="flex items-center gap-2"><StatusDot ok={llm ? llm.ok : null} />{llm ? (llm.ok ? "healthy" : "unavailable") : "…"} {llm && <span className="text-faint">· {llm.latency_ms} ms</span>}</span>} />
              <Row k="Installed models" v={(llm?.installed_models as string[] | undefined)?.join(", ") || "—"} />
              <Row k="Loaded in memory" v={(llm?.loaded_models as string[] | undefined)?.join(", ") || "none (loads on first request)"} />
            </dl>
          )}
          {llm?.error ? <p className="mt-3 rounded-lg bg-danger-soft px-3 py-2 text-[12.5px] text-[#991b1b]">{String(llm.error)}</p> : null}
          {cfg?.llm.external && <p className="mt-3 rounded-lg bg-warning-soft px-3 py-2 text-[12.5px] text-[#92400e]">An external OpenAI-compatible endpoint is active: prompts, including document excerpts, are sent to it. Embeddings stay on local Ollama.</p>}
        </CardBody>
      </Card>
      <Card>
        <CardHeader><div><CardTitle>Services</CardTitle><CardDescription>Live health checks from <code className="font-mono">/api/health</code></CardDescription></div></CardHeader>
        <CardBody className="grid gap-3 sm:grid-cols-2">
          {health && Object.entries(health.checks).map(([name, c]) => (
            <div key={name} className="flex items-center gap-3 rounded-xl border border-line px-3.5 py-3">
              <StatusDot ok={c.ok} />
              <div className="min-w-0 flex-1">
                <div className="text-[13px] font-medium capitalize text-ink">{name}</div>
                <div className="truncate text-[11.5px] text-faint">{c.error ? String(c.error) : `${String(c.provider ?? "ok")} · ${c.latency_ms} ms`}</div>
              </div>
            </div>
          ))}
          {cfg && <div className="text-[12px] text-muted sm:col-span-2">Limits: {cfg.limits.max_upload_mb} MB uploads · {cfg.limits.max_dataset_rows.toLocaleString()} dataset rows · {cfg.limits.query_timeout_s}s SQL timeout · {cfg.limits.mission_max_steps} graph steps · {cfg.limits.mission_max_tool_calls} tool calls per mission</div>}
        </CardBody>
      </Card>
      <Card><CardHeader><div><CardTitle>Account</CardTitle><CardDescription>{me?.name} · {me?.email}</CardDescription></div></CardHeader></Card>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="rounded-xl border border-line px-3.5 py-2.5"><dt className="text-[11.5px] text-faint">{k}</dt><dd className="mt-0.5 break-words text-[13px] font-medium text-ink">{v}</dd></div>;
}

function McpPanel() {
  const { data, isPending } = useQuery({ queryKey: keys.tools, queryFn: () => api.get<ToolsInfo>("/system/tools"), refetchInterval: 10_000 });
  const origin = typeof window === "undefined" ? "" : window.location.origin.replace(/:\d+$/, ":8010");
  const snippet = JSON.stringify({ mcpServers: { "nexus-ai": { type: "http", url: `${origin}/mcp/`, headers: { Authorization: "Bearer <your nxs_ token>" } } } }, null, 2);
  if (isPending || !data) return <Skeleton className="h-64" />;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div><CardTitle>NEXUS MCP server</CardTitle><CardDescription>Exposes read-only workspace tools to external MCP clients. Each call is authorized per user and logged.</CardDescription></div>
          <Badge tone={data.mcp.tokens ? "green" : "amber"}>{data.mcp.tokens ? `${data.mcp.tokens} token${data.mcp.tokens > 1 ? "s" : ""} issued` : "no tokens yet"}</Badge>
        </CardHeader>
        <CardBody className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <Row k="Endpoint" v={<code className="font-mono text-[12px]">{data.mcp.endpoint}</code>} />
            <Row k="Transport" v={data.mcp.transport} />
            <Row k="Authentication" v={data.mcp.auth} />
          </div>
          <div>
            <div className="mb-1 text-[12px] font-medium text-ink-2">Client configuration</div>
            <pre className="overflow-x-auto rounded-xl bg-[#0b1220] p-3 font-mono text-[11.5px] text-[#e2e8f0]">{snippet}</pre>
          </div>
        </CardBody>
      </Card>
      <Card className="overflow-hidden">
        <CardHeader><div><CardTitle>Tools</CardTitle><CardDescription>The same typed registry powers agents, workflows and MCP. External (network) tools are never exposed over MCP.</CardDescription></div></CardHeader>
        <div className="overflow-x-auto">
          <table className="w-full text-[12.5px]">
            <thead><tr className="border-y border-line bg-surface-2 text-left text-[11px] uppercase tracking-wide text-faint"><th className="px-5 py-2">Tool</th><th className="px-3 py-2">Availability</th><th className="px-3 py-2 text-right">Calls</th><th className="px-3 py-2 text-right">Errors</th><th className="px-5 py-2">Last execution</th></tr></thead>
            <tbody>
              {data.tools.map((t) => (
                <tr key={t.name} className="border-b border-line/70 align-top">
                  <td className="px-5 py-2.5"><code className="font-mono font-medium text-ink">{t.name}</code><div className="mt-0.5 text-[11.5px] text-muted">{t.description}</div></td>
                  <td className="px-3 py-2.5"><div className="flex flex-wrap gap-1"><Badge tone="blue">agents</Badge>{t.mcp_exposed && <Badge tone="green">MCP</Badge>}{t.external && <Badge tone="amber">network</Badge>}</div></td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{t.calls}</td>
                  <td className={cn("px-3 py-2.5 text-right tabular-nums", t.errors ? "text-danger" : "text-faint")}>{t.errors ?? 0}</td>
                  <td className="px-5 py-2.5 text-muted">{t.last_called_at ? timeAgo(t.last_called_at) : "never"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader><CardTitle>Recent MCP calls</CardTitle></CardHeader>
          <CardBody className="space-y-1.5">
            {data.mcp.recent_calls.map((c, i) => <div key={i} className="flex items-center gap-2 text-[12px]"><StatusDot ok={c.status === "ok"} /><code className="font-mono">{c.tool}</code><span className="ml-auto text-faint">{formatDuration(c.duration_ms)} · {timeAgo(c.created_at)}</span></div>)}
            {!data.mcp.recent_calls.length && <p className="text-[12.5px] text-faint">No MCP client has called NEXUS yet.</p>}
          </CardBody>
        </Card>
        <Card>
          <CardHeader><CardTitle>Recent tool errors</CardTitle></CardHeader>
          <CardBody className="space-y-2">
            {data.recent_errors.map((e, i) => <div key={i} className="text-[12px]"><code className="font-mono text-ink">{e.tool}</code> <span className="text-faint">({e.origin}, {timeAgo(e.created_at)})</span><div className="line-clamp-2 text-danger">{e.error}</div></div>)}
            {!data.recent_errors.length && <p className="text-[12.5px] text-faint">No errors recorded.</p>}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function TokensPanel() {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["tokens"], queryFn: () => api.get<{ id: string; name: string; prefix: string; created_at: string; last_used_at: string | null }[]>("/auth/tokens") });
  const [name, setName] = React.useState("");
  const [created, setCreated] = React.useState<string | null>(null);
  const [copied, setCopied] = React.useState(false);
  const create = useMutation({
    mutationFn: () => api.post<{ token: string }>("/auth/tokens", { name }),
    onSuccess: (r) => { setCreated(r.token); setName(""); void qc.invalidateQueries({ queryKey: ["tokens"] }); void qc.invalidateQueries({ queryKey: keys.tools }); },
    onError: (e) => toast.error((e as Error).message),
  });
  const revoke = useMutation({ mutationFn: (id: string) => api.del(`/auth/tokens/${id}`), onSuccess: () => qc.invalidateQueries({ queryKey: ["tokens"] }) });
  return (
    <Card>
      <CardHeader><div><CardTitle>API tokens</CardTitle><CardDescription>Bearer tokens for MCP clients. Tokens are stored only as SHA-256 hashes and shown once.</CardDescription></div></CardHeader>
      <CardBody className="space-y-4">
        <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <Input placeholder="Token name, e.g. Claude Desktop" value={name} onChange={(e) => setName(e.target.value)} aria-label="Token name" />
          <Button type="submit" disabled={!name.trim() || create.isPending}><Plus /> Create token</Button>
        </form>
        {created && (
          <div className="rounded-xl border border-[#c6f1df] bg-success-soft p-3">
            <div className="text-[12.5px] font-medium text-[#047857]">Copy this token now — it will not be shown again.</div>
            <div className="mt-2 flex items-center gap-2">
              <code className="flex-1 break-all rounded-md bg-surface px-2 py-1.5 font-mono text-[12px]">{created}</code>
              <Button size="sm" variant="secondary" onClick={async () => { await navigator.clipboard.writeText(created); setCopied(true); }}>{copied ? <Check /> : <Copy />}</Button>
            </div>
          </div>
        )}
        <div className="divide-y divide-line rounded-xl border border-line">
          {data?.map((t) => (
            <div key={t.id} className="flex items-center gap-3 px-4 py-2.5 text-[13px]">
              <KeyRound className="size-4 text-primary" />
              <div className="min-w-0 flex-1"><div className="font-medium text-ink">{t.name}</div><div className="text-[11.5px] text-faint"><code className="font-mono">{t.prefix}…</code> · created {formatDateTime(t.created_at)} · {t.last_used_at ? `last used ${timeAgo(t.last_used_at)}` : "never used"}</div></div>
              <Button variant="danger-ghost" size="sm" onClick={() => revoke.mutate(t.id)}><Trash2 /> Revoke</Button>
            </div>
          ))}
          {!data?.length && <div className="px-4 py-3 text-[12.5px] text-faint">No tokens.</div>}
        </div>
      </CardBody>
    </Card>
  );
}

function MetricsPanel() {
  const { data } = useQuery({ queryKey: keys.metrics, queryFn: () => api.get<Metrics>("/system/metrics"), refetchInterval: 15_000 });
  if (!data) return <Skeleton className="h-64" />;
  const tasksBy = data.tasks.reduce<Record<string, number>>((a, t) => ({ ...a, [t.status]: (a[t.status] ?? 0) + t.count }), {});
  return (
    <div className="space-y-4">
      <p className="text-[12.5px] text-muted">All figures are aggregated from persisted records in your database — nothing is estimated.</p>
      <div className="grid gap-3 sm:grid-cols-4">
        <Tile k="Assistant replies" v={data.generation.assistant_messages.toLocaleString()} />
        <Tile k="Avg generation latency" v={formatDuration(data.generation.avg_latency_ms)} />
        <Tile k="Completion tokens" v={data.generation.completion_tokens.toLocaleString()} />
        <Tile k="Generation errors" v={String(data.generation.errors)} />
        <Tile k="Missions completed" v={String(tasksBy.completed ?? 0)} />
        <Tile k="Missions failed" v={String(tasksBy.failed ?? 0)} />
        <Tile k="Sources retrieved" v={String(data.sources.retrieved ?? 0)} />
        <Tile k="Retrieval failures" v={String((data.sources.failed ?? 0) + (data.sources.blocked ?? 0))} />
      </div>
      <Card className="overflow-hidden">
        <CardHeader><CardTitle>Tool latency</CardTitle></CardHeader>
        <table className="w-full text-[12.5px]">
          <thead><tr className="border-y border-line bg-surface-2 text-left text-[11px] uppercase tracking-wide text-faint"><th className="px-5 py-2">Tool</th><th className="px-3 py-2 text-right">Calls</th><th className="px-3 py-2 text-right">Avg</th><th className="px-3 py-2 text-right">p95</th><th className="px-5 py-2 text-right">Errors</th></tr></thead>
          <tbody>
            {data.tools.map((t) => (
              <tr key={t.tool} className="border-b border-line/70"><td className="px-5 py-2"><code className="font-mono">{t.tool}</code></td><td className="px-3 py-2 text-right tabular-nums">{t.calls}</td><td className="px-3 py-2 text-right tabular-nums">{formatDuration(t.avg_ms)}</td><td className="px-3 py-2 text-right tabular-nums">{formatDuration(t.p95_ms)}</td><td className={cn("px-5 py-2 text-right tabular-nums", t.errors ? "text-danger" : "text-faint")}>{t.errors}</td></tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}

function Tile({ k, v }: { k: string; v: string }) {
  return <Card className="p-4"><div className="text-[12px] text-muted">{k}</div><div className="mt-1 text-[22px] font-semibold tabular-nums tracking-[-0.02em] text-ink">{v}</div></Card>;
}
