"""Workflow Builder API: templates, definitions (CRUD + validation) and runs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from nexus.api.deps import DB, CurrentUser, not_found
from nexus.jobs import enqueue
from nexus.models import Dataset, Document, Task, WorkflowDefinition, WorkflowRun
from nexus.workflows.engine import TEMPLATES, template_graph
from nexus.workflows.spec import NODE_TYPES, WorkflowInvalid, validate_graph

router = APIRouter(prefix="/workflows", tags=["workflows"])


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    graph: dict[str, Any] = Field(default_factory=lambda: {"nodes": [], "edges": []})
    template: str | None = None


class WorkflowOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    template: str | None
    graph: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@router.get("/node-types")
async def node_types() -> list[dict[str, Any]]:
    return [
        {
            "type": k,
            "label": v["label"],
            "consumes": sorted(v["consumes"]),
            "produces": v["produces"],
            "config_schema": v["cfg"].model_json_schema(),
        }
        for k, v in NODE_TYPES.items()
    ]


@router.get("/templates")
async def templates() -> list[dict[str, Any]]:
    return [
        {"key": k, "name": t["name"], "description": t["description"], "graph": template_graph(k)}
        for k, t in TEMPLATES.items()
    ]


async def owned(db: DB, user_id: uuid.UUID, wid: uuid.UUID) -> WorkflowDefinition:
    w = await db.get(WorkflowDefinition, wid)
    if w is None or w.user_id != user_id:
        raise not_found("Workflow")
    return w


async def _check_refs(db: DB, user_id: uuid.UUID, graph: dict[str, Any]) -> None:
    """Config may reference documents/datasets; they must belong to the user."""
    for n in graph.get("nodes", []):
        cfg = (n.get("data") or {}).get("config") or {}
        if cfg.get("dataset_id"):
            d = await db.get(Dataset, uuid.UUID(str(cfg["dataset_id"])))
            if d is None or d.user_id != user_id:
                raise HTTPException(422, f"Node {n.get('id')}: dataset not found")
        for did in cfg.get("document_ids") or []:
            doc = await db.get(Document, uuid.UUID(str(did)))
            if doc is None or doc.user_id != user_id:
                raise HTTPException(422, f"Node {n.get('id')}: document not found")


@router.get("", response_model=list[WorkflowOut])
async def list_workflows(user: CurrentUser, db: DB) -> list[Any]:
    return list(
        (
            await db.execute(
                select(WorkflowDefinition)
                .where(WorkflowDefinition.user_id == user.id)
                .order_by(WorkflowDefinition.updated_at.desc())
            )
        ).scalars()
    )


@router.post("", response_model=WorkflowOut, status_code=201)
async def create(body: WorkflowIn, user: CurrentUser, db: DB) -> WorkflowDefinition:
    graph = template_graph(body.template) if body.template in TEMPLATES and not body.graph.get("nodes") else body.graph
    await _check_refs(db, user.id, graph)
    w = WorkflowDefinition(
        user_id=user.id, name=body.name, description=body.description, graph=graph, template=body.template
    )
    db.add(w)
    await db.commit()
    return w


@router.get("/{wid}", response_model=WorkflowOut)
async def get(wid: uuid.UUID, user: CurrentUser, db: DB) -> WorkflowDefinition:
    return await owned(db, user.id, wid)


@router.put("/{wid}", response_model=WorkflowOut)
async def update(wid: uuid.UUID, body: WorkflowIn, user: CurrentUser, db: DB) -> WorkflowDefinition:
    w = await owned(db, user.id, wid)
    await _check_refs(db, user.id, body.graph)
    w.name, w.description, w.graph = body.name, body.description, body.graph
    await db.commit()
    await db.refresh(w)
    return w


@router.delete("/{wid}", status_code=204)
async def delete(wid: uuid.UUID, user: CurrentUser, db: DB) -> None:
    await db.delete(await owned(db, user.id, wid))
    await db.commit()


@router.post("/validate")
async def validate(body: dict[str, Any], user: CurrentUser) -> dict[str, Any]:
    try:
        validate_graph(body)
    except WorkflowInvalid as e:
        return {"valid": False, "problems": e.problems}
    return {"valid": True, "problems": []}


class RunIn(BaseModel):
    input: str = Field(default="", max_length=4000)


@router.post("/{wid}/runs", status_code=201)
async def run(wid: uuid.UUID, body: RunIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    w = await owned(db, user.id, wid)
    try:
        g = validate_graph(w.graph)
    except WorkflowInvalid as e:
        raise HTTPException(422, {"message": "Workflow is invalid", "problems": e.problems}) from e
    await _check_refs(db, user.id, w.graph)
    default_input = next((n.data.get("config", {}).get("prompt", "") for n in g.nodes if n.type == "input"), "")
    text = body.input or default_input
    if not text.strip():
        raise HTTPException(422, "Provide an input for this run")
    t = Task(
        user_id=user.id,
        kind="workflow",
        mode="workflow",
        title=f"{w.name}: {text[:180]}",
        prompt=text,
        options={"workflow_id": str(w.id)},
    )
    db.add(t)
    await db.flush()
    r = WorkflowRun(user_id=user.id, workflow_id=w.id, task_id=t.id, graph_snapshot=w.graph, inputs={"input": text})
    db.add(r)
    await db.commit()
    await enqueue("run_task", str(t.id))
    return {"run_id": str(r.id), "task_id": str(t.id)}


@router.get("/{wid}/runs")
async def runs(wid: uuid.UUID, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    await owned(db, user.id, wid)
    rows = (
        await db.execute(
            select(WorkflowRun, Task)
            .join(Task, Task.id == WorkflowRun.task_id)
            .where(WorkflowRun.workflow_id == wid)
            .order_by(WorkflowRun.created_at.desc())
        )
    ).all()
    return [
        {
            "run_id": str(r.id),
            "task_id": str(t.id),
            "status": t.status,
            "input": r.inputs.get("input"),
            "created_at": r.created_at,
            "finished_at": t.finished_at,
            "error": t.error,
        }
        for r, t in rows
    ]
