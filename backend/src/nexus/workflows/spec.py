"""Workflow definition schema, typed node configs and static graph validation."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

Port = Literal["text", "evidence", "analysis", "artifact"]


class InputCfg(BaseModel):
    prompt: str = Field(default="", max_length=4000, description="Default input; can be overridden per run")


class WebSearchCfg(BaseModel):
    query_template: str = Field(default="{input}", max_length=500)
    max_sources: int = Field(default=4, ge=1, le=10)


class DocRetrievalCfg(BaseModel):
    query_template: str = Field(default="{input}", max_length=500)
    k: int = Field(default=5, ge=1, le=15)
    document_ids: list[uuid.UUID] = Field(default_factory=list)


class LLMCfg(BaseModel):
    instruction: str = Field(default="Answer the request using the evidence.", max_length=4000)
    grounded: bool = Field(default=True, description="Require citations to upstream evidence")


class DataAnalysisCfg(BaseModel):
    dataset_id: uuid.UUID | None = None
    question_template: str = Field(default="{input}", max_length=1000)


class VerificationCfg(BaseModel):
    pass


class ApprovalCfg(BaseModel):
    message: str = Field(default="Review the intermediate result before continuing.", max_length=500)


class ArtifactCfg(BaseModel):
    title: str = Field(default="Workflow report", max_length=200)


class OutputCfg(BaseModel):
    pass


NODE_TYPES: dict[str, dict[str, Any]] = {
    "input": {"label": "Input", "cfg": InputCfg, "consumes": set(), "produces": "text"},
    "web_search": {"label": "Web Search", "cfg": WebSearchCfg, "consumes": {"text"}, "produces": "evidence"},
    "document_retrieval": {
        "label": "Document Retrieval",
        "cfg": DocRetrievalCfg,
        "consumes": {"text"},
        "produces": "evidence",
    },
    "llm_reasoning": {
        "label": "LLM Reasoning",
        "cfg": LLMCfg,
        "consumes": {"text", "evidence", "analysis"},
        "produces": "text",
    },
    "data_analysis": {"label": "Data Analysis", "cfg": DataAnalysisCfg, "consumes": {"text"}, "produces": "analysis"},
    "verification": {
        "label": "Verification",
        "cfg": VerificationCfg,
        "consumes": {"text", "evidence", "analysis"},
        "produces": "text",
    },
    "human_approval": {
        "label": "Human Approval",
        "cfg": ApprovalCfg,
        "consumes": {"text", "evidence", "analysis"},
        "produces": "passthrough",
    },
    "artifact_generation": {
        "label": "Artifact Generation",
        "cfg": ArtifactCfg,
        "consumes": {"text", "evidence", "analysis"},
        "produces": "artifact",
    },
    "output": {
        "label": "Output",
        "cfg": OutputCfg,
        "consumes": {"text", "artifact", "evidence", "analysis"},
        "produces": "terminal",
    },
}


class WFNode(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    type: str
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    data: dict[str, Any] = Field(default_factory=dict)


class WFEdge(BaseModel):
    id: str | None = None
    source: str
    target: str


class WorkflowGraph(BaseModel):
    nodes: list[WFNode] = Field(max_length=40)
    edges: list[WFEdge] = Field(max_length=120)


class WorkflowInvalid(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


def topo_order(nodes: list[str], edges: list[tuple[str, str]]) -> list[str] | None:
    indeg = {n: 0 for n in nodes}
    out: dict[str, list[str]] = {n: [] for n in nodes}
    for a, b in edges:
        out[a].append(b)
        indeg[b] += 1
    ready = [n for n in nodes if indeg[n] == 0]
    order = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for m in out[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
    return order if len(order) == len(nodes) else None


def _produces(node_type: str, preds: list[str], types: dict[str, str]) -> set[str]:
    p = NODE_TYPES[node_type]["produces"]
    if p == "passthrough":
        out: set[str] = set()
        for pr in preds:
            out |= _produces(types[pr], [], types) if NODE_TYPES[types[pr]]["produces"] != "passthrough" else {"text"}
        return out
    return {p}


def validate_graph(raw: dict[str, Any]) -> WorkflowGraph:
    try:
        g = WorkflowGraph.model_validate(raw)
    except ValidationError as e:
        raise WorkflowInvalid([f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:5]]) from e
    problems: list[str] = []
    ids = [n.id for n in g.nodes]
    if len(set(ids)) != len(ids):
        problems.append("Node ids must be unique")
    types = {n.id: n.type for n in g.nodes}
    for n in g.nodes:
        spec = NODE_TYPES.get(n.type)
        if spec is None:
            problems.append(f"Node {n.id}: unknown type '{n.type}'")
            continue
        try:
            spec["cfg"].model_validate(n.data.get("config", {}))
        except ValidationError as e:
            problems.append(
                f"Node {n.id} ({spec['label']}): {e.errors()[0]['msg']} at {'.'.join(map(str, e.errors()[0]['loc']))}"
            )
    if problems:
        raise WorkflowInvalid(problems)

    edges = []
    for edge in g.edges:
        if edge.source not in types or edge.target not in types:
            problems.append(f"Edge {edge.source}→{edge.target} references a missing node")
        elif edge.source == edge.target:
            problems.append(f"Node {edge.source} cannot connect to itself")
        else:
            edges.append((edge.source, edge.target))
    if len(set(edges)) != len(edges):
        problems.append("Duplicate edges")
    inputs = [n for n in ids if types[n] == "input"]
    outputs = [n for n in ids if types[n] == "output"]
    if len(inputs) != 1:
        problems.append("A workflow needs exactly one Input node")
    if not outputs:
        problems.append("A workflow needs at least one Output node")
    if problems:
        raise WorkflowInvalid(problems)
    order = topo_order(ids, edges)
    if order is None:
        raise WorkflowInvalid(["The workflow contains a cycle; cycles are not supported by the execution engine"])

    preds = {nid: [a for a, b in edges if b == nid] for nid in ids}
    succs = {nid: [b for a, b in edges if a == nid] for nid in ids}
    for nid in ids:
        t = types[nid]
        if t != "input" and not preds[nid]:
            problems.append(f"{NODE_TYPES[t]['label']} node '{nid}' has no incoming connection")
        if t != "output" and not succs[nid]:
            problems.append(f"{NODE_TYPES[t]['label']} node '{nid}' is not connected to anything downstream")
        if t == "input" and preds[nid]:
            problems.append("The Input node cannot have incoming connections")
        if t == "output" and succs[nid]:
            problems.append("Output nodes cannot have outgoing connections")
        incoming: set[str] = set()
        for p in preds[nid]:
            incoming |= _produces(types[p], preds[p], types)
        consumes = NODE_TYPES[t]["consumes"]
        if preds[nid] and consumes and not incoming & consumes:
            problems.append(
                f"{NODE_TYPES[t]['label']} node '{nid}' cannot accept "
                f"{'/'.join(sorted(incoming))} input (needs {'/'.join(sorted(consumes))})"
            )
        if t == "verification" and not incoming >= {"text"}:
            problems.append(f"Verification node '{nid}' needs an upstream text-producing node")
        if t == "data_analysis":
            cfg = DataAnalysisCfg.model_validate(next(x for x in g.nodes if x.id == nid).data.get("config", {}))
            if cfg.dataset_id is None:
                problems.append(f"Data Analysis node '{nid}' needs a dataset selected")
    if problems:
        raise WorkflowInvalid(problems)
    return g
