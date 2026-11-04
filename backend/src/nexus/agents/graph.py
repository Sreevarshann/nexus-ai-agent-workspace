"""LangGraph mission graph.

    planner ─▶ approval? ─▶ ┬─▶ web_researcher ─┐
                            ├─▶ doc_researcher ─┼─▶ synthesizer ─▶ verifier? ─▶ artifact_builder ─▶ END
                            └─▶ data_analyst ───┘

Only the agents the plan needs are scheduled. Every node is wrapped so that it emits typed events, records an
``agent_runs`` row, honours cancel/pause requests at its boundary and reports failures honestly.
"""

from __future__ import annotations

import json
import operator
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, TypedDict

from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from nexus.agents.analyst import result_text, run_analysis
from nexus.agents.evidence import Evidence, gather_docs, gather_web, render_evidence
from nexus.agents.prompts import MODE_GUIDANCE, PLANNER_SYSTEM, SYNTH_SYSTEM
from nexus.agents.verify import verify_report
from nexus.artifacts.service import create_artifact
from nexus.db import session_scope
from nexus.events import control_requested, emit
from nexus.llm.base import ChatMessage, GenOptions, LLMError, structured
from nexus.llm.factory import get_llm
from nexus.models import AgentRun, Dataset, Document
from nexus.redis import get_redis
from nexus.tools.registry import ToolContext

Mode = Literal["quick", "deep", "compare", "doc_web"]

MODE_LIMITS: dict[str, dict[str, int]] = {
    "quick": {"queries": 1, "sources": 3},
    "deep": {"queries": 4, "sources": 8},
    "compare": {"queries": 6, "sources": 9},
    "doc_web": {"queries": 2, "sources": 5},
}

AGENTS = {
    "planner": ("Planner", "Breaks the task into an executable plan"),
    "approval": ("Human Approval", "Waits for you to approve outbound research"),
    "web_researcher": ("Research Agent", "Searches the live web and retrieves sources"),
    "doc_researcher": ("Document Agent", "Retrieves passages from your knowledge library"),
    "data_analyst": ("Data Analyst", "Runs typed analysis over the attached dataset"),
    "synthesizer": ("Synthesizer", "Combines evidence into cited findings"),
    "verifier": ("Evidence Verifier", "Checks citations and numeric claims against sources"),
    "artifact_builder": ("Artifact Generator", "Builds the downloadable report"),
}


class PauseRequested(Exception):
    pass


class MissionCancelled(Exception):
    pass


class PlanStep(BaseModel):
    agent: Literal["web_researcher", "doc_researcher", "data_analyst", "synthesizer", "verifier", "artifact_builder"]
    description: str


class MissionPlan(BaseModel):
    objective: str = Field(description="One-sentence restatement of the goal")
    report_title: str = Field(description="Short title for the final report (max 10 words)")
    steps: list[PlanStep] = Field(min_length=1, max_length=8)
    web_queries: list[str] = Field(default_factory=list, max_length=6, description="Search engine queries")
    doc_queries: list[str] = Field(
        default_factory=list, max_length=4, description="Queries for the user's documents, if relevant"
    )
    entities: list[str] = Field(
        default_factory=list, max_length=5, description="Things being compared, if this is a comparison"
    )


class ComparisonValue(BaseModel):
    criterion: str
    value: str = Field(description="Short value or description, as stated in the evidence")
    numeric_value: float | None = Field(default=None, description="Only if the evidence states a number")
    citation: str = Field(description="Evidence label like S3, or empty if unsupported")


class ComparisonEntity(BaseModel):
    name: str
    values: list[ComparisonValue]


class ComparisonMatrix(BaseModel):
    criteria: list[str] = Field(min_length=1, max_length=8)
    entities: list[ComparisonEntity] = Field(min_length=2, max_length=5)


class MissionState(TypedDict, total=False):
    task_id: str
    user_id: str
    mode: str
    prompt: str
    options: dict[str, Any]
    plan: dict[str, Any]
    route: list[str]
    web_evidence: list[dict[str, Any]]
    doc_evidence: list[dict[str, Any]]
    analysis: dict[str, Any] | None
    evidence: list[dict[str, Any]]
    report: str
    comparison: dict[str, Any] | None
    verification: dict[str, Any] | None
    artifact_id: str | None
    errors: Annotated[list[str], operator.add]


NodeFn = Callable[[MissionState, ToolContext, Callable[..., Awaitable[Any]]], Awaitable[dict[str, Any]]]


def _summ(v: Any, n: int = 280) -> str:
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s[:n] + ("…" if len(s) > n else "")


def agent_node(
    name: str, check_pause: bool = True
) -> Callable[[NodeFn], Callable[[MissionState], Awaitable[dict[str, Any]]]]:
    agent, role = AGENTS[name]

    def deco(fn: NodeFn) -> Callable[[MissionState], Awaitable[dict[str, Any]]]:
        return instrument(name, agent, role, fn, check_pause)

    return deco


def instrument(name: str, agent: str, role: str, fn: Any, check_pause: bool = True) -> Any:
    """Wrap a node function with events, agent_runs bookkeeping and cancel/pause checks."""

    async def wrapped(state: Any) -> dict[str, Any]:
        task_id = uuid.UUID(state["task_id"])
        if await control_requested(task_id, "cancel"):
            raise MissionCancelled()
        if check_pause and await control_requested(task_id, "pause"):
            raise PauseRequested(name)
        async with session_scope() as db:
            run = AgentRun(
                task_id=task_id, node=name, agent=agent, status="running", input_summary=_summ(state.get("prompt", ""))
            )
            db.add(run)
            await db.flush()
            run_id = run.id
        started = time.perf_counter()
        started_at = datetime.now(UTC).isoformat()
        await emit(
            task_id, "node_started", node=name, agent=agent, role=role, agent_run_id=str(run_id), started_at=started_at
        )

        async def node_emit(type_: Any, **payload: Any) -> Any:
            return await emit(task_id, type_, node=name, **payload)

        ctx = ToolContext(user_id=uuid.UUID(state["user_id"]), origin="agent", task_id=task_id, agent_run_id=run_id)
        try:
            update = await fn(state, ctx, node_emit)
        except (GraphInterrupt, PauseRequested, MissionCancelled):
            async with session_scope() as db:
                r = await db.get(AgentRun, run_id)
                if r:
                    await db.delete(r)  # the node will run again on resume
            raise
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"[:1000]
            async with session_scope() as db:
                r = await db.get(AgentRun, run_id)
                if r:
                    r.status, r.error, r.finished_at = "failed", msg, datetime.now(UTC)
            await emit(
                task_id,
                "node_failed",
                node=name,
                agent=agent,
                error=msg,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )
            raise
        out_summary = update.pop("_summary", "") if isinstance(update, dict) else ""
        async with session_scope() as db:
            r = await db.get(AgentRun, run_id)
            if r:
                r.status, r.output_summary, r.finished_at = "completed", out_summary, datetime.now(UTC)
        await emit(
            task_id,
            "node_completed",
            node=name,
            agent=agent,
            output=out_summary,
            duration_ms=int((time.perf_counter() - started) * 1000),
            finished_at=datetime.now(UTC).isoformat(),
        )
        return update

    wrapped.__name__ = name
    return wrapped


# --------------------------------------------------------------------------------------------- nodes


@agent_node("planner")
async def planner(state: MissionState, ctx: ToolContext, ev: Callable[..., Awaitable[Any]]) -> dict[str, Any]:
    mode, opts = state["mode"], state.get("options", {})
    limits = MODE_LIMITS[mode]
    async with session_scope() as db:
        from sqlalchemy import func, select

        n_docs = (
            await db.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.user_id == ctx.user_id, Document.status == "ready")
            )
            or 0
        )
    context = [f"Research mode: {mode}. Use at most {limits['queries']} web queries."]
    if opts.get("dataset_id"):
        context.append("A dataset is attached: include a data_analyst step.")
    if n_docs and (mode == "doc_web" or opts.get("document_ids")):
        context.append("The user's document library must be searched: include doc_queries.")
    msgs = [
        ChatMessage("system", PLANNER_SYSTEM),
        ChatMessage("user", f"Task: {state['prompt']}\n\n" + "\n".join(context)),
    ]
    try:
        plan = await structured(get_llm(), msgs, MissionPlan)
    except LLMError as e:
        raise RuntimeError(f"Planner could not produce a valid plan: {e}") from e

    # Enforce mode semantics in code, not just in the prompt.
    queries = [q.strip() for q in plan.web_queries if q.strip()]
    if mode == "compare":
        if len(plan.entities) < 2:
            raise RuntimeError("Compare mode needs at least two things to compare; name them in the prompt.")
        year = datetime.now(UTC).year
        queries = queries[:2] + [f"{e} features strengths limitations {year}" for e in plan.entities[:4]]
    if not queries:
        queries = [state["prompt"][:200]]
    queries = list(dict.fromkeys(queries))[: limits["queries"]]
    needs_docs = bool(n_docs) and (mode == "doc_web" or bool(opts.get("document_ids")))
    doc_queries = (plan.doc_queries or [state["prompt"][:300]])[:3] if needs_docs else []
    route = ["web_researcher"]
    if needs_docs:
        route.append("doc_researcher")
    if opts.get("dataset_id"):
        route.append("data_analyst")
    plan_d = plan.model_dump()
    plan_d.update(
        web_queries=queries, doc_queries=doc_queries, route=route, max_sources=limits["sources"], verify=mode != "quick"
    )
    await ev("plan_created", plan=plan_d)
    return {
        "plan": plan_d,
        "route": route,
        "_summary": f"{len(plan.steps)} steps; {len(queries)} web queries; agents: {', '.join(route)}",
    }


@agent_node("approval", check_pause=False)
async def approval(state: MissionState, ctx: ToolContext, ev: Callable[..., Awaitable[Any]]) -> dict[str, Any]:
    plan = state["plan"]
    decision = interrupt(
        {
            "kind": "plan_approval",
            "message": "Approve outbound web research for this plan?",
            "web_queries": plan["web_queries"],
            "max_sources": plan["max_sources"],
            "agents": plan["route"],
        }
    )
    approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
    await ev(
        "approval_resolved",
        approved=approved,
        comment=(decision or {}).get("comment", "") if isinstance(decision, dict) else "",
    )
    if not approved:
        raise MissionCancelled("Plan rejected by user")
    edited = decision.get("web_queries") if isinstance(decision, dict) else None
    if edited:
        plan = {**plan, "web_queries": [q for q in edited if isinstance(q, str) and q.strip()][:6]}
    return {"plan": plan, "_summary": "Approved by user"}


@agent_node("web_researcher")
async def web_researcher(state: MissionState, ctx: ToolContext, ev: Callable[..., Awaitable[Any]]) -> dict[str, Any]:
    plan = state["plan"]
    evidence, errors = await gather_web(ctx, plan["web_queries"], plan["max_sources"], ev)
    if not evidence:
        errors.append("No web sources could be retrieved")
    return {
        "web_evidence": [e.__dict__ for e in evidence],
        "errors": errors,
        "_summary": f"Retrieved {len(evidence)} sources ({len(errors)} failures)",
    }


@agent_node("doc_researcher")
async def doc_researcher(state: MissionState, ctx: ToolContext, ev: Callable[..., Awaitable[Any]]) -> dict[str, Any]:
    plan, opts = state["plan"], state.get("options", {})
    evidence, errors = await gather_docs(ctx, plan["doc_queries"], 4, opts.get("document_ids"), ev)
    return {
        "doc_evidence": [e.__dict__ for e in evidence],
        "errors": errors,
        "_summary": f"Found {len(evidence)} relevant passages",
    }


@agent_node("data_analyst")
async def data_analyst(state: MissionState, ctx: ToolContext, ev: Callable[..., Awaitable[Any]]) -> dict[str, Any]:
    async with session_scope() as db:
        ds = await db.get(Dataset, uuid.UUID(state["options"]["dataset_id"]))
    if ds is None or ds.user_id != ctx.user_id:
        raise LookupError("Attached dataset not found")
    analysis = await run_analysis(ds, state["prompt"], ev)
    return {
        "analysis": analysis,
        "errors": analysis["errors"],
        "_summary": f"{len(analysis['results'])} computed results on {ds.name}",
    }


async def _stream_to_redis(task_id: str, node: str, messages: list[ChatMessage]) -> str:
    """Stream generation; live deltas go to Redis only (not persisted) so watchers see the draft forming."""
    out: list[str] = []
    r = get_redis()
    buf, last = "", time.perf_counter()
    async for chunk in get_llm().stream_chat(messages, GenOptions(temperature=0.2)):
        out.append(chunk.delta)
        buf += chunk.delta
        if buf and (time.perf_counter() - last > 0.25 or chunk.done):
            await r.publish(f"task:{task_id}:events", json.dumps({"type": "draft", "node": node, "delta": buf}))
            buf, last = "", time.perf_counter()
    return re.sub(r"<think>.*?</think>\s*", "", "".join(out), flags=re.S).strip()


@agent_node("synthesizer")
async def synthesizer(state: MissionState, ctx: ToolContext, ev: Callable[..., Awaitable[Any]]) -> dict[str, Any]:
    items = [Evidence(**e) for e in state.get("web_evidence", []) + state.get("doc_evidence", [])]
    for i, e in enumerate(items, 1):
        e.label = f"S{i}"
    analysis = state.get("analysis") or {}
    data_block = "\n\n".join(result_text(r["label"], r, 20) for r in analysis.get("results", []))
    if not items and not data_block:
        report = (
            "## Executive summary\n\nNo evidence could be gathered for this task, so no findings are "
            "reported. See the execution log for the failures encountered.\n\n## Limitations\n\n"
            + "\n".join(f"- {e}" for e in state.get("errors", [])[:10])
        )
        return {"evidence": [], "report": report, "_summary": "No evidence available; reported honestly"}
    user = (
        f"Task: {state['prompt']}\n\nObjective: {state['plan']['objective']}\n"
        f"Guidance: {MODE_GUIDANCE[state['mode']]}\n\n"
    )
    if items:
        user += f"Evidence:\n{render_evidence(items)}\n\n"
    if data_block:
        user += f"Computed data results:\n{data_block}\n\n"
    user += "Write the report now."
    report = await _stream_to_redis(
        state["task_id"], "synthesizer", [ChatMessage("system", SYNTH_SYSTEM), ChatMessage("user", user)]
    )
    comparison = None
    if state["mode"] == "compare" and items:
        try:
            matrix = await structured(
                get_llm(),
                [
                    ChatMessage(
                        "system",
                        "Extract a comparison matrix strictly from the evidence. Use the evidence "
                        "label (e.g. S2) that states each value; leave citation empty if none does. "
                        "Set numeric_value only for numbers literally stated in the evidence.",
                    ),
                    ChatMessage(
                        "user", f"Entities: {', '.join(state['plan'].get('entities', []))}\n{render_evidence(items)}"
                    ),
                ],
                ComparisonMatrix,
            )
            comparison = matrix.model_dump()
        except LLMError as e:
            await ev("log", message=f"Comparison matrix extraction failed: {e}")
    return {
        "evidence": [e.__dict__ for e in items],
        "report": report,
        "comparison": comparison,
        "_summary": f"Drafted {len(report.split())}-word report from {len(items)} sources",
    }


@agent_node("verifier")
async def verifier(state: MissionState, ctx: ToolContext, ev: Callable[..., Awaitable[Any]]) -> dict[str, Any]:
    ev_text = {e["label"]: e["text"] for e in state.get("evidence", [])}
    from nexus.agents.analyst import result_text as rt

    for r in (state.get("analysis") or {}).get("results", []):
        ev_text[r["label"]] = rt(r["label"], r, 500)
    cleaned, report = verify_report(state.get("report", ""), ev_text)
    comparison = state.get("comparison")
    if comparison:
        for ent in comparison["entities"]:
            for v in ent["values"]:
                src = ev_text.get(v.get("citation", ""), "")
                v["verified"] = bool(src) and (
                    v.get("numeric_value") is None or _number_in_text(v["numeric_value"], src)
                )
    await ev(
        "log",
        message=f"Verified {report['claims_checked']} cited claims: {report['supported']} supported, "
        f"{report['weak']} weak, {report['unsupported']} unsupported",
        verification={k: v for k, v in report.items() if k != "claims"},
    )
    return {
        "report": cleaned,
        "verification": report,
        "comparison": comparison,
        "_summary": f"{report['supported']}/{report['claims_checked']} claims supported; "
        f"{len(report['fabricated_labels_removed'])} invalid citations removed",
    }


def _number_in_text(n: float, text: str) -> bool:
    nums = {float(m.replace(",", "")) for m in re.findall(r"\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?", text)}
    return any(abs(x - n) <= max(0.005 * abs(n), 0.051) for x in nums)


def _comparison_tables(comparison: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    criteria = comparison["criteria"]
    rows = []
    for ent in comparison["entities"]:
        vals = {v["criterion"]: v for v in ent["values"]}
        rows.append(
            [ent["name"]]
            + [
                (vals[c]["value"] + (f" [{vals[c]['citation']}]" if vals[c].get("citation") else ""))
                if c in vals
                else ""
                for c in criteria
            ]
        )
    tables = [{"title": "Comparison matrix", "columns": ["Entity", *criteria], "rows": rows}]
    charts = []
    for c in criteria:
        pts = []
        for ent in comparison["entities"]:
            v = next((x for x in ent["values"] if x["criterion"] == c), None)
            if v and v.get("numeric_value") is not None and v.get("verified"):
                pts.append({"name": ent["name"], "value": v["numeric_value"], "citation": v["citation"]})
        if len(pts) >= 2:  # only chart numbers that were verified against the cited source
            charts.append(
                {
                    "title": c,
                    "type": "bar",
                    "x": "name",
                    "y": ["value"],
                    "data": pts,
                    "note": "Values verified against cited sources",
                }
            )
    return tables, charts


@agent_node("artifact_builder")
async def artifact_builder(state: MissionState, ctx: ToolContext, ev: Callable[..., Awaitable[Any]]) -> dict[str, Any]:
    evidence = state.get("evidence", [])
    report = state.get("report", "")
    used = set(re.findall(r"\[(S\d+)\]", report))
    citations = [
        {k: v for k, v in e.items() if k != "text"} | {"excerpt": e["text"][:500]}
        for e in evidence
        if e["label"] in used
    ]
    tables: list[dict[str, Any]] = []
    charts: list[dict[str, Any]] = []
    for r in (state.get("analysis") or {}).get("results", []):
        tables.append(
            {"title": f"[{r['label']}] {r['title']}", "columns": r["columns"], "rows": r["rows"][:200], "sql": r["sql"]}
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
    if state.get("comparison"):
        t, c = _comparison_tables(state["comparison"])
        tables = t + tables
        charts = c + charts
    sources_md = "\n".join(
        f"- **[{c['label']}]** "
        + (
            f"[{c['title']}]({c['url']}) — {c['domain']}, retrieved {c['retrieved_at'][:10]}"
            if c["kind"] == "web"
            else f"{c['filename']}" + (f", page {c['page']}" if c.get("page") else "")
        )
        for c in citations
    )
    content = report + (f"\n\n## Sources\n\n{sources_md}" if sources_md else "")
    title = state["plan"].get("report_title") or state["prompt"][:80]
    art = await create_artifact(
        ctx.user_id,
        title,
        "report",
        content,
        {
            "citations": citations,
            "tables": tables,
            "charts": charts,
            "verification": state.get("verification"),
            "mode": state["mode"],
            "all_evidence_count": len(evidence),
        },
        task_id=ctx.task_id,
        project_id=state.get("options", {}).get("project_id"),
    )
    await ev("artifact_created", artifact_id=str(art.id), title=title, kind="report")
    return {
        "artifact_id": str(art.id),
        "_summary": f"Report artifact with {len(citations)} citations, {len(charts)} charts, {len(tables)} tables",
    }


# --------------------------------------------------------------------------------------------- wiring


def _after_planner(state: MissionState) -> str | list[str]:
    if state.get("options", {}).get("require_approval"):
        return "approval"
    return state["route"]


def _after_approval(state: MissionState) -> list[str]:
    return state["route"]


def _after_synth(state: MissionState) -> str:
    return "verifier" if state["plan"].get("verify") else "artifact_builder"


def build_graph() -> StateGraph:
    g = StateGraph(MissionState)
    g.add_node("planner", planner)
    g.add_node("approval", approval)
    g.add_node("web_researcher", web_researcher)
    g.add_node("doc_researcher", doc_researcher)
    g.add_node("data_analyst", data_analyst)
    g.add_node("synthesizer", synthesizer)
    g.add_node("verifier", verifier)
    g.add_node("artifact_builder", artifact_builder)
    research = ["web_researcher", "doc_researcher", "data_analyst"]
    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", _after_planner, ["approval", *research])
    g.add_conditional_edges("approval", _after_approval, research)
    for r in research:
        g.add_edge(r, "synthesizer")
    g.add_conditional_edges("synthesizer", _after_synth, ["verifier", "artifact_builder"])
    g.add_edge("verifier", "artifact_builder")
    g.add_edge("artifact_builder", END)
    return g
