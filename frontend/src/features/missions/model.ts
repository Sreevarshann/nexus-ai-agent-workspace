import type { AgentRun, TaskDetail, TaskEvent, WorkflowGraph } from "@/lib/types";

export type NodeStatus = "pending" | "running" | "waiting_approval" | "completed" | "failed" | "cancelled" | "skipped";

export type GraphNode = {
  id: string;
  agent: string;
  role: string;
  kind: string;
  status: NodeStatus;
  startedAt?: string;
  finishedAt?: string;
  durationMs?: number;
  output?: string;
  error?: string;
  toolCalls: number;
  agentRunIds: string[];
  position: { x: number; y: number };
};

export type GraphModel = { nodes: GraphNode[]; edges: { id: string; source: string; target: string }[]; vertical: boolean };

const MISSION: { id: string; agent: string; role: string; x: number; y: number }[] = [
  // top-to-bottom layout: research agents fan out side by side, everything else is a single column
  { id: "planner", agent: "Planner", role: "Breaks the task into an executable plan", x: 280, y: 0 },
  { id: "approval", agent: "Human Approval", role: "Approve outbound web research", x: 280, y: 170 },
  { id: "web_researcher", agent: "Research Agent", role: "Searches the live web and retrieves sources", x: 0, y: 340 },
  { id: "doc_researcher", agent: "Document Agent", role: "Retrieves passages from your library", x: 280, y: 340 },
  { id: "data_analyst", agent: "Data Analyst", role: "Runs typed analysis over the dataset", x: 560, y: 340 },
  { id: "synthesizer", agent: "Synthesizer", role: "Combines evidence into cited findings", x: 280, y: 510 },
  { id: "verifier", agent: "Evidence Verifier", role: "Checks citations and numbers against sources", x: 280, y: 680 },
  { id: "artifact_builder", agent: "Artifact Generator", role: "Builds the downloadable report", x: 280, y: 850 },
  { id: "final", agent: "Final Output", role: "Report saved to your workspace", x: 280, y: 1020 },
];

const MISSION_EDGES: [string, string][] = [
  ["planner", "approval"],
  ["approval", "web_researcher"],
  ["approval", "doc_researcher"],
  ["approval", "data_analyst"],
  ["web_researcher", "synthesizer"],
  ["doc_researcher", "synthesizer"],
  ["data_analyst", "synthesizer"],
  ["synthesizer", "verifier"],
  ["verifier", "artifact_builder"],
  ["artifact_builder", "final"],
];

const TERMINAL = new Set(["completed", "failed", "cancelled"]);

/** Derive node states purely from persisted events — the canvas never animates work that did not happen. */
export function buildModel(detail: TaskDetail, events: TaskEvent[]): GraphModel {
  const task = detail.task;
  const plan = events.find((e) => e.type === "plan_created")?.payload.plan as
    | { route?: string[]; verify?: boolean }
    | undefined;
  const finished = TERMINAL.has(task.status);
  const isWorkflow = task.kind === "workflow" && detail.graph;

  let specs: { id: string; agent: string; role: string; x: number; y: number; kind: string }[];
  let edges: [string, string][];
  if (isWorkflow) {
    const g = detail.graph as WorkflowGraph;
    specs = g.nodes.map((n) => ({ id: n.id, agent: n.data.label ?? n.type, role: n.type.replace(/_/g, " "), x: n.position.x, y: n.position.y, kind: n.type }));
    edges = g.edges.map((e) => [e.source, e.target]);
  } else {
    const approval = !!task.options.require_approval;
    specs = MISSION.filter((s) => approval || s.id !== "approval").map((s) => ({ ...s, kind: s.id }));
    edges = MISSION_EDGES.filter(([a, b]) => approval || (a !== "approval" && b !== "approval"));
    if (!approval) edges = [...edges, ["planner", "web_researcher"], ["planner", "doc_researcher"], ["planner", "data_analyst"]];
  }

  const byId = new Map<string, GraphNode>(
    specs.map((s) => [s.id, { id: s.id, agent: s.agent, role: s.role, kind: s.kind, status: "pending", toolCalls: 0, agentRunIds: [], position: { x: s.x, y: s.y } }]),
  );
  for (const e of events) {
    const n = e.node ? byId.get(e.node) : undefined;
    if (e.type === "node_started" && n) {
      n.status = "running";
      n.startedAt = e.created_at;
      n.error = undefined;
      if (e.payload.agent_run_id) n.agentRunIds.push(e.payload.agent_run_id);
    } else if (e.type === "node_completed" && n) {
      n.status = "completed";
      n.finishedAt = e.created_at;
      n.durationMs = e.payload.duration_ms;
      n.output = e.payload.output;
    } else if (e.type === "node_failed" && n) {
      n.status = "failed";
      n.finishedAt = e.created_at;
      n.durationMs = e.payload.duration_ms;
      n.error = e.payload.error;
    } else if (e.type === "tool_call" && n) {
      n.toolCalls += 1;
    } else if (e.type === "approval_required") {
      const target = byId.get(e.node ?? "approval") ?? [...byId.values()].find((x) => x.kind === "human_approval" && x.status === "running");
      if (target) target.status = "waiting_approval";
    }
  }

  if (!isWorkflow) {
    const route = new Set(plan?.route ?? []);
    for (const id of ["web_researcher", "doc_researcher", "data_analyst"]) {
      const n = byId.get(id);
      if (n && plan && !route.has(id) && n.status === "pending") n.status = "skipped";
    }
    const v = byId.get("verifier");
    if (v && plan && plan.verify === false && v.status === "pending") v.status = "skipped";
    const f = byId.get("final");
    if (f) {
      f.status = task.status === "completed" ? "completed" : task.status === "failed" ? "failed" : task.status === "cancelled" ? "cancelled" : "pending";
      f.finishedAt = task.finished_at ?? undefined;
      f.output = task.status === "completed" ? `${task.result.sources ?? 0} sources · artifact saved` : task.error ?? undefined;
    }
  }
  for (const n of byId.values()) {
    if (finished && n.status === "running") n.status = task.status === "cancelled" ? "cancelled" : "failed";
    if (finished && n.status === "pending") n.status = task.status === "completed" ? "skipped" : "cancelled";
    if (task.status === "paused" && n.status === "running") n.status = "pending";
  }

  // hide edges into skipped research agents to keep the graph honest and readable
  const visible = edges.filter(([a, b]) => byId.get(a)?.status !== "skipped" && byId.get(b)?.status !== "skipped");
  return {
    vertical: !isWorkflow,
    nodes: [...byId.values()],
    edges: visible.map(([a, b]) => ({ id: `${a}-${b}`, source: a, target: b })),
  };
}

export function runsFor(node: GraphNode, runs: AgentRun[]): AgentRun[] {
  return runs.filter((r) => node.agentRunIds.includes(r.id) || r.node === node.id);
}
