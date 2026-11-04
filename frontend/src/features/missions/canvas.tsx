"use client";

import {
  Background,
  BackgroundVariant,
  Controls,
  type Edge,
  Handle,
  MarkerType,
  MiniMap,
  type Node,
  type NodeChange,
  type NodeProps,
  type XYPosition,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
} from "@xyflow/react";
import {
  Bot,
  BookOpenText,
  Brain,
  CheckCircle2,
  CircleDashed,
  Database,
  FileOutput,
  Flag,
  Globe2,
  Hand,
  ListChecks,
  Loader2,
  OctagonX,
  ShieldCheck,
  Sparkles,
  Wrench,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import * as React from "react";

import type { GraphModel, GraphNode, NodeStatus } from "@/features/missions/model";
import { cn, formatDuration } from "@/lib/utils";

export const NODE_ICONS: Record<string, LucideIcon> = {
  planner: ListChecks,
  approval: Hand,
  human_approval: Hand,
  web_researcher: Globe2,
  web_search: Globe2,
  doc_researcher: BookOpenText,
  document_retrieval: BookOpenText,
  data_analyst: Database,
  data_analysis: Database,
  synthesizer: Brain,
  llm_reasoning: Brain,
  verifier: ShieldCheck,
  verification: ShieldCheck,
  artifact_builder: FileOutput,
  artifact_generation: FileOutput,
  final: Flag,
  output: Flag,
  input: Sparkles,
};

const STATUS_STYLE: Record<NodeStatus, { ring: string; chip: string; label: string; Icon: LucideIcon }> = {
  pending: { ring: "border-line", chip: "bg-surface-2 text-muted", label: "Pending", Icon: CircleDashed },
  running: { ring: "border-primary ring-4 ring-[var(--primary-ring)]", chip: "bg-primary-soft text-primary-deep", label: "Running", Icon: Loader2 },
  waiting_approval: { ring: "border-warning ring-4 ring-[rgb(245_158_11/0.22)]", chip: "bg-warning-soft text-[#b45309]", label: "Waiting for approval", Icon: Hand },
  completed: { ring: "border-[#a7e8cf]", chip: "bg-success-soft text-[#047857]", label: "Completed", Icon: CheckCircle2 },
  failed: { ring: "border-[#fca5a5]", chip: "bg-danger-soft text-[#b91c1c]", label: "Failed", Icon: XCircle },
  cancelled: { ring: "border-line", chip: "bg-surface-2 text-muted", label: "Cancelled", Icon: OctagonX },
  skipped: { ring: "border-dashed border-line opacity-60", chip: "bg-surface-2 text-faint", label: "Not needed", Icon: CircleDashed },
};

type AgentNodeData = GraphNode & { selected?: boolean; vertical?: boolean };

function AgentNode({ data }: NodeProps<Node<AgentNodeData>>) {
  const s = STATUS_STYLE[data.status];
  const Icon = NODE_ICONS[data.kind] ?? Bot;
  return (
    <div
      className={cn(
        "w-[236px] rounded-2xl border bg-surface shadow-card transition-[box-shadow,border-color] duration-300",
        s.ring,
        data.selected && "shadow-pop outline-2 outline-offset-2 outline-primary",
      )}
      data-testid={`node-${data.id}`}
      data-status={data.status}
    >
      <Handle type="target" position={data.vertical ? Position.Top : Position.Left} className="!size-2 !border-2 !border-surface !bg-line-strong" />
      <div className="flex items-start gap-2.5 p-3">
        <div className={cn("flex size-9 shrink-0 items-center justify-center rounded-xl", data.status === "running" ? "bg-primary text-white" : data.status === "completed" ? "bg-success-soft text-[#047857]" : "bg-primary-soft text-primary")}>
          <Icon className="size-[18px]" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-[13.5px] font-semibold text-ink">{data.agent}</div>
          <div className="line-clamp-2 text-[11.5px] leading-snug text-muted">{data.role}</div>
        </div>
      </div>
      <div className="flex items-center gap-2 border-t border-line/80 px-3 py-2">
        <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10.5px] font-semibold", s.chip)}>
          <s.Icon className={cn("size-3", data.status === "running" && "animate-spin")} /> {s.label}
        </span>
        {data.toolCalls > 0 && (
          <span className="inline-flex items-center gap-1 text-[11px] text-muted"><Wrench className="size-3" />{data.toolCalls}</span>
        )}
        <span className="ml-auto text-[11px] tabular-nums text-faint">{data.durationMs != null ? formatDuration(data.durationMs) : ""}</span>
      </div>
      {(data.output || data.error) && (
        <div className={cn("line-clamp-2 border-t border-line/80 px-3 py-2 text-[11.5px] leading-snug", data.error ? "text-danger" : "text-ink-2")}>
          {data.error ?? data.output}
        </div>
      )}
      <Handle type="source" position={data.vertical ? Position.Bottom : Position.Right} className="!size-2 !border-2 !border-surface !bg-line-strong" />
    </div>
  );
}

const nodeTypes = { agent: AgentNode };
const MINIMAP_COLORS: Record<string, string> = { running: "#2563eb", completed: "#10b981", failed: "#ef4444", waiting_approval: "#f59e0b" };

function Inner({ model, selected, onSelect }: { model: GraphModel; selected: string | null; onSelect: (id: string | null) => void }) {
  const flow = useReactFlow();
  const statuses = new Map(model.nodes.map((n) => [n.id, n.status]));
  // Node data comes from the event-derived model; React Flow owns measured size and dragged position.
  const [layout, setLayout] = React.useState<Record<string, { position?: XYPosition; measured?: { width: number; height: number } }>>({});
  const nodes: Node<AgentNodeData>[] = model.nodes.map((n) => ({
    id: n.id,
    type: "agent",
    position: layout[n.id]?.position ?? n.position,
    measured: layout[n.id]?.measured,
    data: { ...n, selected: n.id === selected, vertical: model.vertical },
    draggable: true,
  }));
  const onNodesChange = React.useCallback((changes: NodeChange<Node<AgentNodeData>>[]) => {
    setLayout((prev) => {
      const next = { ...prev };
      for (const c of changes) {
        if (c.type === "dimensions" && c.dimensions) next[c.id] = { ...next[c.id], measured: c.dimensions };
        if (c.type === "position" && c.position) next[c.id] = { ...next[c.id], position: c.position };
      }
      return next;
    });
  }, []);
  const edges: Edge[] = model.edges.map((e) => {
    const src = statuses.get(e.source);
    const dst = statuses.get(e.target);
    const active = src === "completed" && (dst === "running" || dst === "waiting_approval");
    const done = src === "completed" && dst === "completed";
    return {
      id: e.id,
      source: e.source,
      target: e.target,
      animated: active,
      style: { stroke: active ? "#2563eb" : done ? "#6ee7b7" : "#cbd5e1", strokeWidth: active ? 2.2 : 1.6 },
      markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16, color: active ? "#2563eb" : done ? "#6ee7b7" : "#cbd5e1" },
    };
  });
  const count = model.nodes.length;
  React.useEffect(() => {
    const t = setTimeout(() => void flow.fitView({ padding: 0.12, duration: 300, maxZoom: 1 }), 50);
    return () => clearTimeout(t);
  }, [count, flow]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodesChange={onNodesChange}
      onNodeClick={(_, n) => onSelect(n.id)}
      onPaneClick={() => onSelect(null)}
      fitView
      minZoom={0.25}
      maxZoom={1.6}
      proOptions={{ hideAttribution: true }}
      nodesConnectable={false}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1.3} color="#d5ddeb" />
      <Controls showInteractive={false} position="bottom-left" />
      <MiniMap pannable zoomable position="bottom-right" nodeColor={(n) => (MINIMAP_COLORS[(n.data as AgentNodeData).status] ?? "#cbd5e1")} maskColor="rgb(248 250 255 / 0.7)" className="!hidden md:!block" />
    </ReactFlow>
  );
}

export function MissionCanvas(props: { model: GraphModel; selected: string | null; onSelect: (id: string | null) => void }) {
  return (
    <ReactFlowProvider>
      <Inner {...props} />
    </ReactFlowProvider>
  );
}
