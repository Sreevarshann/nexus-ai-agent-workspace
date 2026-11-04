"""Compile a validated workflow definition into a LangGraph StateGraph and execute it with the shared runner."""

from __future__ import annotations

import operator
import uuid
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from nexus.agents.analyst import result_text, run_analysis
from nexus.agents.evidence import Evidence, gather_docs, gather_web, render_evidence
from nexus.agents.graph import MissionCancelled, instrument
from nexus.agents.prompts import ASSISTANT_SYSTEM, GROUNDED_RULES
from nexus.agents.verify import verify_report
from nexus.artifacts.service import create_artifact
from nexus.db import session_scope
from nexus.llm.base import ChatMessage, GenOptions
from nexus.llm.factory import get_llm
from nexus.models import Dataset
from nexus.workflows.spec import NODE_TYPES, WorkflowGraph, validate_graph


def _merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    return {**a, **b}


class WFState(TypedDict, total=False):
    task_id: str
    user_id: str
    input: str
    outputs: Annotated[dict[str, Any], _merge]
    report: str
    artifact_id: str | None
    evidence: list[dict[str, Any]]
    errors: Annotated[list[str], operator.add]


def _gather(state: WFState, preds: list[str]) -> dict[str, Any]:
    texts, evidence, analyses, artifacts = [], [], [], []
    for p in preds:
        o = state.get("outputs", {}).get(p) or {}
        if o.get("text"):
            texts.append(o["text"])
        evidence.extend(o.get("evidence", []))
        if o.get("analysis"):
            analyses.append(o["analysis"])
        if o.get("artifact_id"):
            artifacts.append(o["artifact_id"])
    # de-duplicate evidence by underlying source/chunk
    seen, uniq = set(), []
    for e in evidence:
        key = e.get("source_id") or e.get("chunk_id") or e.get("label")
        if key not in seen:
            seen.add(key)
            uniq.append(e)
    return {"texts": texts, "evidence": uniq, "analyses": analyses, "artifacts": artifacts}


def _fill(template: str, state: WFState, texts: list[str]) -> str:
    return template.replace("{input}", state.get("input", "")).replace("{previous}", "\n\n".join(texts))[:1000]


def make_node(node_id: str, node_type: str, cfg: dict[str, Any], preds: list[str]) -> Any:
    label = NODE_TYPES[node_type]["label"]

    async def run(state: WFState, ctx: Any, ev: Any) -> dict[str, Any]:
        up = _gather(state, preds)
        out: dict[str, Any]
        if node_type == "input":
            text = state.get("input") or cfg.get("prompt", "")
            if not text.strip():
                raise ValueError("Workflow input is empty")
            out, summary = {"text": text}, text[:120]
        elif node_type == "web_search":
            q = _fill(cfg.get("query_template", "{input}"), state, up["texts"])
            items, errors = await gather_web(ctx, [q], cfg.get("max_sources", 4), ev)
            out, summary = {"evidence": [e.__dict__ for e in items]}, f"{len(items)} sources retrieved"
            if errors:
                return {"outputs": {node_id: out}, "errors": errors, "_summary": summary}
        elif node_type == "document_retrieval":
            q = _fill(cfg.get("query_template", "{input}"), state, up["texts"])
            ids = [str(i) for i in cfg.get("document_ids", [])] or None
            items, _ = await gather_docs(ctx, [q], cfg.get("k", 5), ids, ev)
            out, summary = {"evidence": [e.__dict__ for e in items]}, f"{len(items)} passages"
        elif node_type == "data_analysis":
            async with session_scope() as db:
                ds = await db.get(Dataset, uuid.UUID(str(cfg["dataset_id"])))
            if ds is None or ds.user_id != ctx.user_id:
                raise LookupError("Dataset not found")
            analysis = await run_analysis(ds, _fill(cfg.get("question_template", "{input}"), state, up["texts"]), ev)
            out, summary = {"analysis": analysis}, f"{len(analysis['results'])} computed results"
        elif node_type == "llm_reasoning":
            items = [Evidence(**e) for e in up["evidence"]]
            for i, e in enumerate(items, 1):
                e.label = f"S{i}"
            data = "\n\n".join(result_text(r["label"], r, 20) for a in up["analyses"] for r in a["results"])
            parts = [f"Request: {state.get('input', '')}", f"Instruction: {cfg.get('instruction', '')}"]
            if up["texts"]:
                parts.append("Upstream notes:\n" + "\n\n".join(up["texts"])[:6000])
            if items:
                parts.append("Evidence:\n" + render_evidence(items))
            if data:
                parts.append("Computed data results (cite as [D#]):\n" + data)
            system = ASSISTANT_SYSTEM + (" " + GROUNDED_RULES if cfg.get("grounded", True) and (items or data) else "")
            res = await get_llm().chat(
                [ChatMessage("system", system), ChatMessage("user", "\n\n".join(parts))], GenOptions(temperature=0.2)
            )
            out = {
                "text": res.text,
                "evidence": [e.__dict__ for e in items],
                "analysis": up["analyses"][0] if up["analyses"] else None,
            }
            summary = (
                f"{len(res.text.split())} words ({res.usage.completion_tokens or '?'} tokens, {res.latency_ms} ms)"
            )
        elif node_type == "verification":
            ev_text = {e["label"]: e["text"] for e in up["evidence"]}
            for a in up["analyses"]:
                for r in a["results"]:
                    ev_text[r["label"]] = result_text(r["label"], r, 500)
            cleaned, report = verify_report("\n\n".join(up["texts"]), ev_text)
            await ev(
                "log",
                message=f"{report['supported']}/{report['claims_checked']} claims supported",
                verification={k: v for k, v in report.items() if k != "claims"},
            )
            out = {
                "text": cleaned,
                "evidence": up["evidence"],
                "verification": report,
                "analysis": up["analyses"][0] if up["analyses"] else None,
            }
            summary = f"{report['supported']}/{report['claims_checked']} claims supported"
        elif node_type == "human_approval":
            decision = interrupt(
                {
                    "kind": "workflow_approval",
                    "node": node_id,
                    "message": cfg.get("message", ""),
                    "preview": "\n\n".join(up["texts"])[:3000],
                }
            )
            if not (decision or {}).get("approved"):
                raise MissionCancelled("Rejected at approval step")
            out = {
                "text": "\n\n".join(up["texts"]),
                "evidence": up["evidence"],
                "analysis": up["analyses"][0] if up["analyses"] else None,
            }
            summary = "Approved"
        elif node_type == "artifact_generation":
            content = "\n\n".join(up["texts"]) or "(no text produced upstream)"
            used = [e for e in up["evidence"] if f"[{e['label']}]" in content]
            tables, charts = [], []
            for a in up["analyses"]:
                for r in a["results"]:
                    tables.append(
                        {
                            "title": f"[{r['label']}] {r['title']}",
                            "columns": r["columns"],
                            "rows": r["rows"][:200],
                            "sql": r["sql"],
                        }
                    )
                    if r.get("chart"):
                        charts.append(
                            {
                                "title": r["title"],
                                **r["chart"],
                                "columns": r["columns"],
                                "rows": r["rows"][:500],
                                "label": r["label"],
                            }
                        )
            if used:
                content += "\n\n## Sources\n\n" + "\n".join(
                    f"- **[{e['label']}]** "
                    + (
                        f"[{e['title']}]({e['url']})"
                        if e["kind"] == "web"
                        else f"{e['filename']}" + (f", page {e['page']}" if e.get("page") else "")
                    )
                    for e in used
                )
            art = await create_artifact(
                ctx.user_id,
                cfg.get("title") or "Workflow report",
                "report",
                content,
                {
                    "citations": [
                        {k: v for k, v in e.items() if k != "text"} | {"excerpt": e["text"][:500]} for e in used
                    ],
                    "tables": tables,
                    "charts": charts,
                },
                task_id=ctx.task_id,
            )
            await ev("artifact_created", artifact_id=str(art.id), title=art.title, kind="report")
            out = {"text": content, "artifact_id": str(art.id), "evidence": up["evidence"]}
            summary = f"Artifact '{art.title}'"
        elif node_type == "output":
            text = "\n\n".join(up["texts"])
            return {
                "outputs": {node_id: {"text": text}},
                "report": text,
                "artifact_id": up["artifacts"][0] if up["artifacts"] else state.get("artifact_id"),
                "evidence": up["evidence"],
                "_summary": f"{len(text.split())} words",
            }
        else:
            raise ValueError(f"Unsupported node type {node_type}")
        return {"outputs": {node_id: out}, "_summary": summary}

    return instrument(node_id, label, node_type, run, check_pause=node_type != "human_approval")


def build_workflow_graph(raw: dict[str, Any]) -> StateGraph:
    g: WorkflowGraph = validate_graph(raw)
    sg = StateGraph(WFState)
    preds = {n.id: [e.source for e in g.edges if e.target == n.id] for n in g.nodes}
    for n in g.nodes:
        sg.add_node(n.id, make_node(n.id, n.type, n.data.get("config", {}), preds[n.id]))
    for n in g.nodes:
        if n.type == "input":
            sg.add_edge(START, n.id)
        if preds[n.id]:
            # a list edge waits for ALL predecessors (proper DAG join semantics)
            sg.add_edge(preds[n.id] if len(preds[n.id]) > 1 else preds[n.id][0], n.id)
        if n.type == "output":
            sg.add_edge(n.id, END)
    return sg


TEMPLATES: dict[str, dict[str, Any]] = {
    "web_research_report": {
        "name": "Web Research Report",
        "description": "Search the web, write a cited answer, verify it and save a report.",
        "chain": [
            ("input", {}),
            ("web_search", {"max_sources": 4}),
            ("llm_reasoning", {"instruction": "Write a structured, cited research brief."}),
            ("verification", {}),
            ("artifact_generation", {"title": "Web research report"}),
            ("output", {}),
        ],
    },
    "document_qa": {
        "name": "Document Question Answering",
        "description": "Answer a question from your knowledge library with page-level citations.",
        "chain": [
            ("input", {}),
            ("document_retrieval", {"k": 6}),
            ("llm_reasoning", {"instruction": "Answer precisely from the document passages."}),
            ("verification", {}),
            ("output", {}),
        ],
    },
    "dataset_investigation": {
        "name": "Dataset Investigation",
        "description": "Analyse a dataset with typed operations and write up the findings.",
        "chain": [
            ("input", {}),
            ("data_analysis", {}),
            ("llm_reasoning", {"instruction": "Explain the computed results; cite [D#] for every number."}),
            ("artifact_generation", {"title": "Dataset investigation"}),
            ("output", {}),
        ],
    },
    "research_data_comparison": {
        "name": "Research + Data Comparison",
        "description": "Combine live web research with your dataset, review, then publish a report.",
        "parallel": True,
        "chain": [
            ("input", {}),
            ("web_search", {"max_sources": 3}),
            ("data_analysis", {}),
            ("llm_reasoning", {"instruction": "Compare what the web sources say with the dataset results."}),
            ("human_approval", {"message": "Review the draft before the report is generated."}),
            ("artifact_generation", {"title": "Research and data comparison"}),
            ("output", {}),
        ],
    },
}


def template_graph(key: str) -> dict[str, Any]:
    t = TEMPLATES[key]
    nodes, edges = [], []
    for i, (typ, cfg) in enumerate(t["chain"]):
        nodes.append(
            {
                "id": f"n{i + 1}",
                "type": typ,
                "position": {"x": 80 + i * 260, "y": 160},
                "data": {"label": NODE_TYPES[typ]["label"], "config": cfg},
            }
        )
    ids = [n["id"] for n in nodes]
    if t.get("parallel"):
        # input → (web_search, data_analysis) → llm → ...
        nodes[1]["position"] = {"x": 340, "y": 60}
        nodes[2]["position"] = {"x": 340, "y": 280}
        for j, n in enumerate(nodes[3:], 3):
            n["position"] = {"x": 600 + (j - 3) * 260, "y": 160}
        pairs = [(ids[0], ids[1]), (ids[0], ids[2]), (ids[1], ids[3]), (ids[2], ids[3])]
        pairs += [(ids[k], ids[k + 1]) for k in range(3, len(ids) - 1)]
    else:
        pairs = [(ids[k], ids[k + 1]) for k in range(len(ids) - 1)]
    edges = [{"id": f"e{a}-{b}", "source": a, "target": b} for a, b in pairs]
    return {"nodes": nodes, "edges": edges}
