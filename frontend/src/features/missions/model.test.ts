import { describe, expect, it } from "vitest";

import { buildModel } from "@/features/missions/model";
import type { TaskDetail, TaskEvent } from "@/lib/types";

const base = (status: string, options: Record<string, unknown> = {}): TaskDetail => ({
  graph: null,
  task: { id: "t", kind: "mission", mode: "quick", title: "x", prompt: "x", status, options, result: {}, error: null, project_id: null, conversation_id: null, created_at: "", started_at: null, finished_at: null } as never,
  events: [], agent_runs: [], tool_calls: [], sources: [], artifacts: [],
});
let id = 0;
const ev = (type: string, node: string | null, payload: Record<string, unknown> = {}): TaskEvent => ({ id: ++id, task_id: "t", type, node, payload, created_at: new Date(2026, 0, 1, 0, 0, id).toISOString() });

describe("buildModel", () => {
  it("shows only real progress: pending until events arrive", () => {
    const m = buildModel(base("queued"), []);
    expect(m.nodes.every((n) => n.status === "pending")).toBe(true);
    expect(m.nodes.find((n) => n.id === "approval")).toBeUndefined();
  });

  it("derives running, completed, tool counts and skipped agents from events", () => {
    const events = [
      ev("node_started", "planner", { agent_run_id: "r1" }),
      ev("plan_created", "planner", { plan: { route: ["web_researcher"], verify: false } }),
      ev("node_completed", "planner", { duration_ms: 1200, output: "1 step" }),
      ev("node_started", "web_researcher"),
      ev("tool_call", "web_researcher", { tool: "web_search" }),
      ev("tool_call", "web_researcher", { tool: "fetch_url" }),
    ];
    const m = buildModel(base("running"), events);
    const by = Object.fromEntries(m.nodes.map((n) => [n.id, n]));
    expect(by.planner.status).toBe("completed");
    expect(by.planner.durationMs).toBe(1200);
    expect(by.web_researcher.status).toBe("running");
    expect(by.web_researcher.toolCalls).toBe(2);
    expect(by.doc_researcher.status).toBe("skipped");
    expect(by.verifier.status).toBe("skipped");
    expect(m.edges.some((e) => e.target === "doc_researcher")).toBe(false);
  });

  it("marks approval waits and failures", () => {
    const events = [ev("node_started", "planner"), ev("node_completed", "planner"), ev("node_started", "approval"), ev("approval_required", "approval")];
    expect(buildModel(base("waiting_approval", { require_approval: true }), events).nodes.find((n) => n.id === "approval")!.status).toBe("waiting_approval");
    const failed = buildModel(base("failed"), [ev("node_started", "planner"), ev("node_failed", "planner", { error: "boom" })]);
    const p = failed.nodes.find((n) => n.id === "planner")!;
    expect(p.status).toBe("failed");
    expect(p.error).toBe("boom");
    expect(failed.nodes.find((n) => n.id === "final")!.status).toBe("failed");
  });

  it("uses the workflow snapshot for workflow runs", () => {
    const d = { ...base("running"), graph: { nodes: [{ id: "a", type: "input", position: { x: 0, y: 0 }, data: { label: "Input" } }, { id: "b", type: "output", position: { x: 200, y: 0 }, data: { label: "Output" } }], edges: [{ source: "a", target: "b" }] } };
    d.task = { ...d.task, kind: "workflow" };
    const m = buildModel(d, [ev("node_started", "a"), ev("node_completed", "a")]);
    expect(m.vertical).toBe(false);
    expect(m.nodes.map((n) => [n.id, n.status])).toEqual([["a", "completed"], ["b", "pending"]]);
  });
});
