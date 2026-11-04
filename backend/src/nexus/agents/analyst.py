"""AI data analyst: model chooses typed operations, the engine computes, the model narrates computed values."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from nexus.agents.evidence import EventCb
from nexus.agents.prompts import ANALYST_NARRATIVE, ANALYST_SYSTEM
from nexus.data.analysis import AnalysisError, AnalysisPlan, execute_operation
from nexus.data.engine import QueryError
from nexus.llm.base import ChatMessage, LLMError, structured
from nexus.llm.factory import get_llm
from nexus.models import Dataset


def profile_for_prompt(ds: Dataset) -> str:
    cols = []
    for c in ds.columns:
        extra = ""
        if c["kind"] == "numeric":
            mean = round(c["mean"], 3) if c.get("mean") is not None else None
            extra = f" min={c.get('min')} max={c.get('max')} mean={mean}"
        elif c["kind"] == "temporal":
            extra = f" range={c.get('min')}..{c.get('max')}"
        elif c.get("top"):
            extra = " values e.g. " + ", ".join(str(t["value"]) for t in c["top"][:5])
        cols.append(f"- {c['name']} ({c['kind']}, {c['type']}, nulls={c['nulls']}, distinct={c['distinct']}){extra}")
    return f"Dataset '{ds.name}' with {ds.row_count} rows. Columns:\n" + "\n".join(cols)


def result_text(label: str, r: dict[str, Any], max_rows: int = 30) -> str:
    head = f"[{label}] {r['title']} ({r['op']})"
    lines = [head, " | ".join(r["columns"])]
    for row in r["rows"][:max_rows]:
        lines.append(" | ".join("" if v is None else (f"{v:.4g}" if isinstance(v, float) else str(v)) for v in row))
    if len(r["rows"]) > max_rows:
        lines.append(f"... {len(r['rows']) - max_rows} more rows")
    if r.get("insights"):
        lines.append("insights: " + json.dumps(r["insights"], default=str))
    return "\n".join(lines)


_AVG_HINTS = ("rating", "score", "pct", "percent", "rate", "price", "age", "ratio", "avg", "mean")
_PRIMARY_HINTS = ("revenue", "sales", "amount", "total", "profit", "value", "income", "cost", "units", "quantity")


def _agg_for(col: str) -> str:
    return "avg" if any(h in col.lower() for h in _AVG_HINTS) else "sum"


def build_catalog(ds: Dataset) -> list[dict[str, Any]]:
    """Candidate operations derived from the real profile. A small model picks from these far more reliably
    than it composes free-form plans, and every candidate is valid against the schema by construction."""
    nums = [c["name"] for c in ds.columns if c["kind"] == "numeric"]
    temporal = [c["name"] for c in ds.columns if c["kind"] == "temporal"]
    cats = [c["name"] for c in ds.columns if c["kind"] in ("categorical", "boolean") and 1 < c["distinct"] <= 30]
    primary = next((n for h in _PRIMARY_HINTS for n in nums if h in n.lower()), nums[0] if nums else None)
    metric = {"column": primary, "agg": _agg_for(primary)} if primary else {"column": "*", "agg": "count"}
    mlabel = f"{metric['agg']} of {primary}" if primary else "row count"
    out: list[dict[str, Any]] = []

    def add(desc: str, op: dict[str, Any]) -> None:
        out.append({"id": len(out) + 1, "description": desc, "operation": op})

    for t in temporal[:1]:
        add(
            f"Monthly trend of {mlabel} (seasonality)",
            {
                "op": "timeseries",
                "title": f"Monthly {mlabel}",
                "date_column": t,
                "granularity": "month",
                "metric": metric,
            },
        )
        add(
            f"Quarterly trend of {mlabel}",
            {
                "op": "timeseries",
                "title": f"Quarterly {mlabel}",
                "date_column": t,
                "granularity": "quarter",
                "metric": metric,
                "chart": "bar",
            },
        )
        add(
            f"Unusual months: anomaly detection on {mlabel}",
            {
                "op": "anomalies",
                "title": f"Anomalies in monthly {mlabel}",
                "date_column": t,
                "granularity": "month",
                "metric": metric,
            },
        )
        for c in cats[:3]:
            add(
                f"Monthly trend of {mlabel} split by {c}",
                {
                    "op": "timeseries",
                    "title": f"Monthly {mlabel} by {c}",
                    "date_column": t,
                    "granularity": "month",
                    "metric": metric,
                    "split_by": c,
                },
            )
    for c in cats[:4]:
        add(
            f"Compare {mlabel} across {c}",
            {"op": "aggregate", "title": f"{mlabel.capitalize()} by {c}", "group_by": [c], "metrics": [metric]},
        )
        for n in nums:
            if n != primary and _agg_for(n) == "avg":
                add(
                    f"Average {n} across {c}",
                    {
                        "op": "aggregate",
                        "title": f"Average {n} by {c}",
                        "group_by": [c],
                        "metrics": [{"column": n, "agg": "avg"}],
                    },
                )
                break
    if len(cats) >= 2:
        add(
            f"{mlabel.capitalize()} by {cats[0]} and {cats[1]}",
            {
                "op": "aggregate",
                "title": f"{mlabel.capitalize()} by {cats[0]} and {cats[1]}",
                "group_by": cats[:2],
                "metrics": [metric],
                "limit": 100,
            },
        )
    for i, a in enumerate(nums[:3]):
        for b in nums[i + 1 : 4]:
            add(f"Correlation between {a} and {b}", {"op": "correlation", "title": f"{a} vs {b}", "x": a, "y": b})
    if primary:
        add(
            f"Distribution of {primary}",
            {"op": "distribution", "title": f"Distribution of {primary}", "column": primary},
        )
    return out[:30]


class AnalysisSelection(BaseModel):
    """The analyst's choice of operations from the catalog."""

    objective: str = Field(description="One sentence restating what the user wants to learn")
    selected: list[int] = Field(min_length=1, max_length=6, description="Catalog ids, most relevant first")


_KEYWORDS = {
    "timeseries": ("trend", "season", "month", "over time", "growth", "quarter"),
    "anomalies": ("unusual", "anomal", "spike", "drop", "outlier", "change"),
    "aggregate": ("compare", "region", "product", "channel", "by ", "across", "segment", "top"),
    "correlation": ("correl", "relationship", "affect", "impact", "driver"),
    "distribution": ("distribution", "spread", "histogram"),
}


def heuristic_selection(catalog: list[dict[str, Any]], question: str) -> list[int]:
    q = question.lower()
    wanted = [op for op, kws in _KEYWORDS.items() if any(k in q for k in kws)] or ["timeseries", "aggregate"]
    picked: list[int] = []
    for op in wanted:
        picked += [c["id"] for c in catalog if c["operation"]["op"] == op][:2]
    return list(dict.fromkeys(picked))[:5] or [c["id"] for c in catalog[:4]]


async def plan_analysis(ds: Dataset, question: str) -> tuple[AnalysisPlan, bool]:
    catalog = build_catalog(ds)
    if not catalog:
        plan = AnalysisPlan.model_validate(
            {
                "objective": question,
                "operations": [{"op": "aggregate", "title": "Row count", "metrics": [{"column": "*", "agg": "count"}]}],
            }
        )
        return plan, True
    menu = "\n".join(f"{c['id']}. {c['description']}" for c in catalog)
    msgs = [
        ChatMessage("system", ANALYST_SYSTEM),
        ChatMessage(
            "user",
            f"{profile_for_prompt(ds)}\n\nAvailable analyses:\n{menu}\n\nQuestion: {question}\n"
            "Select the 2-5 analyses that best answer the question.",
        ),
    ]
    by_id = {c["id"]: c for c in catalog}
    used_fallback = False
    try:
        sel = await structured(get_llm(), msgs, AnalysisSelection)
        ids = [i for i in dict.fromkeys(sel.selected) if i in by_id][:5]
        objective = sel.objective
    except (LLMError, ValidationError):
        ids, objective = [], question
    if not ids:
        ids, used_fallback = heuristic_selection(catalog, question), True
    plan = AnalysisPlan.model_validate({"objective": objective, "operations": [by_id[i]["operation"] for i in ids]})
    return plan, used_fallback


async def run_analysis(ds: Dataset, question: str, emit: EventCb | None = None) -> dict[str, Any]:
    plan, used_fallback = await plan_analysis(ds, question)
    if emit:
        await emit(
            "log",
            message="Analysis plan ready"
            + (" (model selection unusable; used keyword heuristic)" if used_fallback else ""),
            plan=plan.model_dump(),
        )
    results: list[dict[str, Any]] = []
    errors: list[str] = []
    for i, op in enumerate(plan.operations, 1):
        try:
            r = await asyncio.to_thread(execute_operation, ds.parquet_path, ds.columns, op, plan.filters)
        except (AnalysisError, QueryError) as e:
            errors.append(f"{op.op}: {e}")
            if emit:
                await emit("tool_call", tool="analysis." + op.op, args=op.model_dump(), status="error", error=str(e))
            continue
        r["label"] = f"D{len(results) + 1}"
        results.append(r)
        if emit:
            await emit(
                "tool_call",
                tool="analysis." + op.op,
                args=op.model_dump(),
                status="ok",
                result={"rows": len(r["rows"]), "sql": r["sql"], "checks": r["checks"]},
            )
        del i
    return {
        "dataset_id": str(ds.id),
        "dataset": ds.name,
        "plan": plan.model_dump(),
        "fallback_plan": used_fallback,
        "results": results,
        "errors": errors,
    }


def narrative_messages(question: str, analysis: dict[str, Any]) -> list[ChatMessage]:
    body = "\n\n".join(result_text(r["label"], r) for r in analysis["results"])
    return [
        ChatMessage("system", ANALYST_NARRATIVE),
        ChatMessage("user", f"Question: {question}\n\nComputed results:\n{body or 'No results computed.'}"),
    ]


async def stream_narrative(question: str, analysis: dict[str, Any]) -> AsyncIterator[str]:
    async for chunk in get_llm().stream_chat(narrative_messages(question, analysis)):
        if chunk.delta:
            yield chunk.delta
