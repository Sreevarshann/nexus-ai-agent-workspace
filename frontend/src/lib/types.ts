/** API contract types mirrored from the FastAPI response models. */

export type User = { id: string; email: string; name: string };

export type Project = {
  id: string;
  name: string;
  description: string;
  pinned: boolean;
  created_at: string;
  updated_at: string;
  counts: Record<string, number>;
};

export type Conversation = { id: string; title: string; project_id: string | null; created_at: string; updated_at: string };

export type ChatMode = "chat" | "research" | "analysis" | "agent";

export type Citation = {
  label: string;
  kind: "web" | "doc" | "data";
  title?: string;
  url?: string | null;
  domain?: string | null;
  source_id?: string | null;
  chunk_id?: string | null;
  document_id?: string | null;
  filename?: string | null;
  page?: number | null;
  excerpt?: string;
  retrieved_at?: string | null;
  flags?: string[];
  sql?: string;
};

export type AnalysisResult = {
  label: string;
  title: string;
  op: string;
  sql: string;
  columns: string[];
  rows: unknown[][];
  chart: ChartSpec | null;
  checks: { check: string; passed: boolean; [k: string]: unknown }[];
  insights: Record<string, unknown>;
};

export type ChartSpec = {
  type: "bar" | "line" | "area" | "scatter" | "pie";
  x: string;
  y: string[];
  series?: string | null;
  horizontal?: boolean;
  highlight?: string;
  title?: string;
  data?: Record<string, unknown>[];
  columns?: string[];
  rows?: unknown[][];
  note?: string;
  label?: string;
};

export type Analysis = {
  dataset_id: string;
  dataset: string;
  plan: { objective: string; operations: Record<string, unknown>[] };
  fallback_plan: boolean;
  results: AnalysisResult[];
  errors: string[];
};

export type Message = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  status: "complete" | "streaming" | "error" | "cancelled";
  mode: ChatMode;
  citations: Citation[];
  attachments: { kind: "document" | "dataset"; id: string; name: string }[];
  meta: {
    model?: string;
    provider?: string;
    latency_ms?: number;
    tokens?: { prompt?: number; completion?: number };
    error?: string;
    task_id?: string;
    artifact_id?: string;
    suggestions?: string[];
    analysis?: Analysis;
    evidence_count?: number;
    removed_citations?: string[];
    [k: string]: unknown;
  };
  created_at: string;
};

export type TaskStatus = "queued" | "running" | "paused" | "waiting_approval" | "completed" | "failed" | "cancelled";

export type Task = {
  id: string;
  kind: "mission" | "workflow" | "ingest";
  mode: string;
  title: string;
  prompt: string;
  status: TaskStatus;
  options: Record<string, unknown>;
  result: {
    artifact_id?: string;
    summary?: string;
    sources?: number;
    errors?: string[];
    verification?: { claims_checked: number; supported: number; weak: number; unsupported: number } | null;
  };
  error: string | null;
  project_id: string | null;
  conversation_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type TaskEvent = {
  id: number;
  task_id: string;
  type: string;
  node: string | null;
  payload: Record<string, any>; // eslint-disable-line @typescript-eslint/no-explicit-any
  created_at: string;
};

export type AgentRun = {
  id: string;
  node: string;
  agent: string;
  status: string;
  error: string | null;
  input_summary: string;
  output_summary: string;
  started_at: string;
  finished_at: string | null;
};

export type ToolCall = {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  status: "ok" | "error" | "denied";
  error: string | null;
  result_summary: string;
  duration_ms: number;
  agent_run_id: string | null;
  created_at: string;
};

export type Source = {
  id: string;
  url: string;
  final_url: string | null;
  domain: string;
  title: string;
  status: "retrieved" | "failed" | "blocked";
  http_status: number | null;
  excerpt: string;
  error: string | null;
  published_at: string | null;
  retrieved_at: string;
  search_query: string | null;
  task_id?: string | null;
  content?: string;
  chars?: number;
};

export type TaskDetail = {
  task: Task;
  events: TaskEvent[];
  agent_runs: AgentRun[];
  tool_calls: ToolCall[];
  sources: Source[];
  artifacts: { id: string; title: string; kind: string }[];
};

export type DocumentItem = {
  id: string;
  filename: string;
  mime: string;
  size: number;
  status: "queued" | "processing" | "ready" | "failed";
  error: string | null;
  page_count: number | null;
  chunk_count: number;
  project_id: string | null;
  meta: Record<string, unknown>;
  created_at: string;
};

export type SearchHit = {
  chunk_id: string;
  document_id: string;
  filename: string;
  page: number | null;
  text: string;
  score: number;
  similarity: number | null;
  vector_rank: number | null;
  keyword_rank: number | null;
  signals: string[];
};

export type Column = {
  name: string;
  type: string;
  kind: "numeric" | "categorical" | "temporal" | "boolean";
  nulls: number;
  null_pct: number;
  distinct: number;
  min?: unknown;
  max?: unknown;
  mean?: number | null;
  std?: number | null;
  median?: number | null;
  top?: { value: unknown; count: number }[];
};

export type Dataset = {
  id: string;
  name: string;
  filename: string;
  row_count: number;
  columns: Column[];
  profile: { numeric: string[]; categorical: string[]; temporal: string[]; missing_cells: number };
  project_id: string | null;
  created_at: string;
};

export type ArtifactSummary = {
  id: string;
  title: string;
  kind: string;
  current_version: number;
  task_id: string | null;
  project_id: string | null;
  conversation_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ArtifactVersion = {
  version: number;
  content: string;
  data: {
    citations?: Citation[];
    tables?: { title: string; columns: string[]; rows: unknown[][]; sql?: string }[];
    charts?: ChartSpec[];
    verification?: Record<string, any> | null; // eslint-disable-line @typescript-eslint/no-explicit-any
    mode?: string;
  };
  note: string;
  created_at: string;
};

export type ArtifactDetail = ArtifactSummary & {
  versions: { version: number; note: string; created_at: string }[];
  latest: ArtifactVersion;
  formats: string[];
};

export type WorkflowNode = {
  id: string;
  type: string;
  position: { x: number; y: number };
  data: { label?: string; config?: Record<string, unknown> };
};

export type WorkflowGraph = { nodes: WorkflowNode[]; edges: { id?: string; source: string; target: string }[] };

export type Workflow = {
  id: string;
  name: string;
  description: string;
  template: string | null;
  graph: WorkflowGraph;
  created_at: string;
  updated_at: string;
};

export type NodeTypeSpec = {
  type: string;
  label: string;
  consumes: string[];
  produces: string;
  config_schema: { properties?: Record<string, { type?: string; default?: unknown; description?: string; maximum?: number; minimum?: number }> };
};

export type Health = {
  status: string;
  env: string;
  checks: Record<string, { ok: boolean; error?: string | null; latency_ms: number; [k: string]: unknown }>;
};
