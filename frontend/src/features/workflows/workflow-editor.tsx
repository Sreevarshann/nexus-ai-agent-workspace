"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addEdge,
  Background,
  BackgroundVariant,
  type Connection,
  Controls,
  type Edge,
  Handle,
  MarkerType,
  type Node,
  type NodeProps,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import { AlertTriangle, ArrowLeft, CheckCircle2, Loader2, Play, Plus, Save, Trash2, Workflow as WorkflowIcon } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as React from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, Switch } from "@/components/ui/controls";
import { ErrorNote, Skeleton } from "@/components/ui/feedback";
import { Input, Textarea } from "@/components/ui/input";
import { Dialog, DialogContent } from "@/components/ui/overlay";
import { StatusBadge } from "@/components/ui/status";
import { NODE_ICONS } from "@/features/missions/canvas";
import { api } from "@/lib/api";
import { keys, useDatasets, useDocuments } from "@/lib/queries";
import type { NodeTypeSpec, Workflow, WorkflowGraph } from "@/lib/types";
import { cn, timeAgo } from "@/lib/utils";

type NodeData = { label: string; type: string; config: Record<string, unknown>; invalid?: boolean };
type FlowNode = Node<NodeData>;

function EditorNode({ data, selected }: NodeProps<FlowNode>) {
  const Icon = NODE_ICONS[data.type] ?? WorkflowIcon;
  return (
    <div className={cn("w-[200px] rounded-xl border bg-surface shadow-card", selected ? "border-primary ring-4 ring-[var(--primary-ring)]" : data.invalid ? "border-[#fca5a5]" : "border-line")} data-testid={`wf-node-${data.type}`}>
      {data.type !== "input" && <Handle type="target" position={Position.Left} className="!size-2.5 !border-2 !border-surface !bg-primary" />}
      <div className="flex items-center gap-2.5 p-3">
        <div className="flex size-8 items-center justify-center rounded-lg bg-primary-soft text-primary"><Icon className="size-4" /></div>
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold text-ink">{data.label}</div>
          <div className="truncate text-[11px] text-muted">{data.type.replace(/_/g, " ")}</div>
        </div>
      </div>
      {data.type !== "output" && <Handle type="source" position={Position.Right} className="!size-2.5 !border-2 !border-surface !bg-primary" />}
    </div>
  );
}
const nodeTypes = { wf: EditorNode };

const toFlow = (g: WorkflowGraph): { nodes: FlowNode[]; edges: Edge[] } => ({
  nodes: g.nodes.map((n) => ({ id: n.id, type: "wf", position: n.position, data: { label: n.data.label ?? n.type, type: n.type, config: n.data.config ?? {} } })),
  edges: g.edges.map((e) => ({ id: e.id ?? `e${e.source}-${e.target}`, source: e.source, target: e.target, markerEnd: { type: MarkerType.ArrowClosed } })),
});

const fromFlow = (nodes: FlowNode[], edges: Edge[]): WorkflowGraph => ({
  nodes: nodes.map((n) => ({ id: n.id, type: n.data.type, position: { x: Math.round(n.position.x), y: Math.round(n.position.y) }, data: { label: n.data.label, config: n.data.config } })),
  edges: edges.map((e) => ({ id: e.id, source: e.source, target: e.target })),
});

export function WorkflowEditor({ id }: { id: string }) {
  const { data: wf, error } = useQuery({ queryKey: ["workflow", id], queryFn: () => api.get<Workflow>(`/workflows/${id}`) });
  const { data: specs } = useQuery({ queryKey: ["node-types"], queryFn: () => api.get<NodeTypeSpec[]>("/workflows/node-types"), staleTime: Infinity });
  if (error) return <div className="p-6"><ErrorNote error={error} /></div>;
  if (!wf || !specs) return <div className="p-6"><Skeleton className="h-[70vh]" /></div>;
  return (
    <ReactFlowProvider>
      <Editor wf={wf} specs={specs} />
    </ReactFlowProvider>
  );
}

function Editor({ wf, specs }: { wf: Workflow; specs: NodeTypeSpec[] }) {
  const qc = useQueryClient();
  const router = useRouter();
  const initial = React.useMemo(() => toFlow(wf.graph), [wf.graph]);
  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(initial.edges);
  const [name, setName] = React.useState(wf.name);
  const [selected, setSelected] = React.useState<string | null>(null);
  const [problems, setProblems] = React.useState<string[] | null>(null);
  const [runOpen, setRunOpen] = React.useState(false);
  const [runInput, setRunInput] = React.useState("");
  const specMap = React.useMemo(() => new Map(specs.map((s) => [s.type, s])), [specs]);
  const sel = nodes.find((n) => n.id === selected);
  const runs = useQuery({ queryKey: ["wf-runs", wf.id], queryFn: () => api.get<{ run_id: string; task_id: string; status: string; input: string; created_at: string; error: string | null }[]>(`/workflows/${wf.id}/runs`), refetchInterval: 5000 });

  const onConnect = React.useCallback((c: Connection) => {
    if (c.source === c.target) return;
    setEdges((es) => addEdge({ ...c, id: `e${c.source}-${c.target}`, markerEnd: { type: MarkerType.ArrowClosed } }, es));
    setProblems(null);
  }, [setEdges]);

  const addNode = (type: string) => {
    const spec = specMap.get(type)!;
    const n = nodes.length;
    const newId = `n${crypto.randomUUID().slice(0, 8)}`;
    setNodes((ns) => [...ns, { id: newId, type: "wf", position: { x: 120 + (n % 4) * 240, y: 340 + Math.floor(n / 4) * 120 }, data: { label: spec.label, type, config: {} } }]);
    setSelected(newId);
    setProblems(null);
  };

  const graph = () => fromFlow(nodes, edges);
  const validate = async () => {
    const r = await api.post<{ valid: boolean; problems: string[] }>("/workflows/validate", graph());
    setProblems(r.problems);
    return r.valid;
  };
  const save = useMutation({
    mutationFn: () => api.put<Workflow>(`/workflows/${wf.id}`, { name, description: wf.description, graph: graph() }),
    onSuccess: () => { toast.success("Workflow saved"); void qc.invalidateQueries({ queryKey: keys.workflows }); void qc.invalidateQueries({ queryKey: ["workflow", wf.id] }); },
    onError: (e) => toast.error((e as Error).message),
  });
  const run = useMutation({
    mutationFn: async () => {
      await save.mutateAsync();
      return api.post<{ task_id: string }>(`/workflows/${wf.id}/runs`, { input: runInput });
    },
    onSuccess: (r) => router.push(`/missions/${r.task_id}`),
    onError: (e) => toast.error((e as Error).message),
  });

  const updateConfig = (key: string, value: unknown) =>
    setNodes((ns) => ns.map((n) => (n.id === selected ? { ...n, data: { ...n.data, config: { ...n.data.config, [key]: value } } } : n)));

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-2 border-b border-line bg-surface px-4 py-2.5">
        <Button asChild variant="ghost" size="icon-sm" aria-label="Back"><Link href="/workflows"><ArrowLeft /></Link></Button>
        <Input value={name} onChange={(e) => setName(e.target.value)} className="h-9 w-64 font-medium" aria-label="Workflow name" />
        <div className="ml-auto flex items-center gap-2">
          <Button variant="secondary" onClick={() => void validate()}><CheckCircle2 /> Validate</Button>
          <Button variant="secondary" onClick={() => save.mutate()} disabled={save.isPending}>{save.isPending ? <Loader2 className="animate-spin" /> : <Save />} Save</Button>
          <Button onClick={async () => { if (await validate()) setRunOpen(true); }}><Play /> Run</Button>
        </div>
      </div>
      {problems && (
        <div className={cn("border-b px-5 py-2 text-[12.5px]", problems.length ? "border-[#fecaca] bg-danger-soft text-[#991b1b]" : "border-[#c6f1df] bg-success-soft text-[#047857]")}>
          {problems.length ? <><AlertTriangle className="mr-1.5 inline size-3.5" />{problems.join(" · ")}</> : <><CheckCircle2 className="mr-1.5 inline size-3.5" />Valid workflow — types, connections and acyclicity check out.</>}
        </div>
      )}
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="nx-scroll w-full shrink-0 overflow-y-auto border-b border-line bg-surface p-3 lg:w-[220px] lg:border-b-0 lg:border-r">
          <div className="mb-2 px-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-faint">Add node</div>
          <div className="grid grid-cols-2 gap-1.5 lg:grid-cols-1">
            {specs.map((s) => {
              const Icon = NODE_ICONS[s.type] ?? WorkflowIcon;
              return (
                <button key={s.type} onClick={() => addNode(s.type)} className="flex items-center gap-2 rounded-lg border border-line px-2.5 py-2 text-left text-[12.5px] text-ink-2 transition hover:border-primary/40 hover:bg-primary-soft/40">
                  <Icon className="size-3.5 text-primary" /> {s.label} <Plus className="ml-auto size-3 text-faint" />
                </button>
              );
            })}
          </div>
          <p className="mt-3 px-1 text-[11.5px] leading-snug text-faint">Drag from a node&apos;s right handle to another node&apos;s left handle to connect. Select and press Backspace to delete.</p>
        </aside>
        <div className="nx-grid relative min-h-[420px] flex-1 bg-bg">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, n) => setSelected(n.id)}
            onPaneClick={() => setSelected(null)}
            deleteKeyCode={["Backspace", "Delete"]}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background variant={BackgroundVariant.Dots} gap={22} size={1.3} color="#d5ddeb" />
            <Controls position="bottom-left" />
          </ReactFlow>
        </div>
        <aside className="nx-scroll w-full shrink-0 overflow-y-auto border-t border-line bg-surface lg:w-[320px] lg:border-l lg:border-t-0">
          {sel ? (
            <NodeConfig node={sel} spec={specMap.get(sel.data.type)!} onChange={updateConfig} onRename={(l) => setNodes((ns) => ns.map((n) => (n.id === sel.id ? { ...n, data: { ...n.data, label: l } } : n)))} onDelete={() => { setNodes((ns) => ns.filter((n) => n.id !== sel.id)); setEdges((es) => es.filter((e) => e.source !== sel.id && e.target !== sel.id)); setSelected(null); }} />
          ) : (
            <div className="p-4">
              <div className="text-[13px] font-semibold text-ink">Runs</div>
              <div className="mt-2 space-y-1.5">
                {runs.data?.map((r) => (
                  <Link key={r.run_id} href={`/missions/${r.task_id}`} className="block rounded-lg border border-line p-2.5 hover:border-primary/40">
                    <div className="flex items-center gap-2"><StatusBadge status={r.status} /><span className="ml-auto text-[11px] text-faint">{timeAgo(r.created_at)}</span></div>
                    <div className="mt-1 line-clamp-2 text-[12px] text-ink-2">{r.input}</div>
                  </Link>
                ))}
                {!runs.data?.length && <p className="text-[12.5px] text-faint">No runs yet. Select a node to configure it.</p>}
              </div>
            </div>
          )}
        </aside>
      </div>
      <Dialog open={runOpen} onOpenChange={setRunOpen}>
        <DialogContent title="Run workflow" description="The definition is saved, snapshotted and executed by the background worker.">
          <Textarea rows={4} value={runInput} onChange={(e) => setRunInput(e.target.value)} placeholder="Input for the Input node (e.g. a question or topic)" aria-label="Run input" />
          <div className="mt-4 flex justify-end"><Button onClick={() => run.mutate()} disabled={run.isPending}>{run.isPending ? <Loader2 className="animate-spin" /> : <Play />} Start run</Button></div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function NodeConfig({ node, spec, onChange, onRename, onDelete }: { node: FlowNode; spec: NodeTypeSpec; onChange: (k: string, v: unknown) => void; onRename: (l: string) => void; onDelete: () => void }) {
  const { data: datasets } = useDatasets();
  const { data: docs } = useDocuments();
  const props = spec.config_schema.properties ?? {};
  return (
    <div className="space-y-4 p-4">
      <div className="flex items-center gap-2">
        <Badge tone="blue">{spec.label}</Badge>
        <Button variant="danger-ghost" size="icon-sm" className="ml-auto" onClick={onDelete} aria-label="Delete node"><Trash2 /></Button>
      </div>
      <Field label="Label"><Input value={node.data.label} onChange={(e) => onRename(e.target.value)} /></Field>
      <div className="text-[11.5px] text-faint">Accepts {spec.consumes.join(", ") || "nothing"} · produces {spec.produces}</div>
      {Object.entries(props).map(([key, p]) => {
        const value = node.data.config[key] ?? p.default;
        const label = key.replace(/_/g, " ");
        if (key === "dataset_id") {
          return <Field key={key} label="Dataset"><Select ariaLabel="Dataset" value={(value as string) ?? undefined} onValueChange={(v) => onChange(key, v)} className="w-full" placeholder="Select a dataset" options={(datasets ?? []).map((d) => ({ value: d.id, label: d.name }))} /></Field>;
        }
        if (key === "document_ids") {
          const ids = (value as string[]) ?? [];
          return (
            <Field key={key} label="Documents (empty = whole library)">
              <div className="flex flex-wrap gap-1.5">
                {(docs ?? []).filter((d) => d.status === "ready").map((d) => (
                  <button key={d.id} onClick={() => onChange(key, ids.includes(d.id) ? ids.filter((x) => x !== d.id) : [...ids, d.id])} className={cn("rounded-md border px-2 py-0.5 text-[11.5px]", ids.includes(d.id) ? "border-primary bg-primary-soft text-primary-deep" : "border-line text-ink-2")}>{d.filename}</button>
                ))}
              </div>
            </Field>
          );
        }
        if (p.type === "boolean") return <Field key={key} label={label}><Switch checked={!!value} onCheckedChange={(v) => onChange(key, v)} /></Field>;
        if (p.type === "integer") return <Field key={key} label={`${label}${p.maximum ? ` (max ${p.maximum})` : ""}`}><Input type="number" min={p.minimum} max={p.maximum} value={String(value ?? "")} onChange={(e) => onChange(key, Number(e.target.value))} /></Field>;
        return (
          <Field key={key} label={label} hint={p.description}>
            <Textarea rows={key.includes("instruction") || key === "prompt" ? 4 : 2} value={String(value ?? "")} onChange={(e) => onChange(key, e.target.value)} />
          </Field>
        );
      })}
      {Object.keys(props).some((k) => k.endsWith("template")) && <p className="text-[11.5px] text-faint">Templates accept <code className="font-mono">{"{input}"}</code> and <code className="font-mono">{"{previous}"}</code>.</p>}
    </div>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return <div className="space-y-1"><div className="text-[12px] font-medium capitalize text-ink-2">{label}</div>{children}{hint && <div className="text-[11px] text-faint">{hint}</div>}</div>;
}
