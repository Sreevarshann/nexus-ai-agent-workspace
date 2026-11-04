"""Data Lab: dataset upload, profiling, preview, guarded SQL, typed analysis, export."""

from __future__ import annotations

import asyncio
import csv
import io
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select

from nexus.agents.analyst import run_analysis
from nexus.api.deps import DB, CurrentUser, not_found
from nexus.api.routers.documents import read_limited
from nexus.api.routers.projects import get_owned_project
from nexus.data.analysis import AnalysisError, Operation, execute_operation, run_sql
from nexus.data.engine import QueryError
from nexus.data.store import convert_to_parquet, preview, profile
from nexus.domain.sqlguard import UnsafeSQL
from nexus.models import Dataset
from nexus.rag.ingest import UploadRejected
from nexus.tools.registry import ToolContext, ToolError, invoke

router = APIRouter(prefix="/datasets", tags=["datasets"])


class DatasetOut(BaseModel):
    id: uuid.UUID
    name: str
    filename: str
    row_count: int
    columns: list[Any]
    profile: dict[str, Any]
    project_id: uuid.UUID | None
    created_at: datetime


async def owned(db: DB, user_id: uuid.UUID, ds_id: uuid.UUID) -> Dataset:
    d = await db.get(Dataset, ds_id)
    if d is None or d.user_id != user_id:
        raise not_found("Dataset")
    return d


@router.post("", response_model=DatasetOut, status_code=201)
async def upload(
    user: CurrentUser,
    db: DB,
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    project_id: uuid.UUID | None = Form(default=None),
) -> Dataset:
    if project_id:
        await get_owned_project(db, user.id, project_id)
    data = await read_limited(file)
    try:
        filename, parquet = await asyncio.to_thread(convert_to_parquet, user.id, file.filename or "data.csv", data)
        rows, columns, summary = await asyncio.to_thread(profile, parquet)
    except UploadRejected as e:
        raise HTTPException(422, str(e)) from e
    ds = Dataset(
        user_id=user.id,
        project_id=project_id,
        name=(name or Path(filename).stem)[:255],
        filename=filename,
        row_count=rows,
        columns=columns,
        profile=summary,
        parquet_path=str(parquet),
    )
    db.add(ds)
    await db.commit()
    return ds


@router.get("", response_model=list[DatasetOut])
async def list_datasets(user: CurrentUser, db: DB) -> list[Any]:
    return list(
        (
            await db.execute(select(Dataset).where(Dataset.user_id == user.id).order_by(Dataset.created_at.desc()))
        ).scalars()
    )


@router.get("/{ds_id}", response_model=DatasetOut)
async def get_dataset(ds_id: uuid.UUID, user: CurrentUser, db: DB) -> Dataset:
    return await owned(db, user.id, ds_id)


@router.get("/{ds_id}/preview")
async def get_preview(ds_id: uuid.UUID, user: CurrentUser, db: DB, limit: int = 100, offset: int = 0) -> dict[str, Any]:
    d = await owned(db, user.id, ds_id)
    return await asyncio.to_thread(preview, d.parquet_path, min(max(limit, 1), 1000), max(offset, 0))


class SQLIn(BaseModel):
    sql: str = Field(min_length=6, max_length=5000)


@router.post("/{ds_id}/query")
async def query(ds_id: uuid.UUID, body: SQLIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    await owned(db, user.id, ds_id)
    try:
        return await invoke(
            "query_dataset", {"dataset_id": str(ds_id), "sql": body.sql}, ToolContext(user_id=user.id, origin="api")
        )
    except ToolError as e:
        raise HTTPException(422, str(e)) from e


class OpIn(BaseModel):
    operation: dict[str, Any]
    filters: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/{ds_id}/operation")
async def operation(ds_id: uuid.UUID, body: OpIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    """Run one typed operation chosen in the UI (no model involved)."""
    from pydantic import TypeAdapter

    from nexus.data.analysis import Condition

    d = await owned(db, user.id, ds_id)
    try:
        op = TypeAdapter(Operation).validate_python(body.operation)
        filters = [Condition.model_validate(f) for f in body.filters]
        return await asyncio.to_thread(execute_operation, d.parquet_path, d.columns, op, filters)
    except ValidationError as e:
        raise HTTPException(422, f"Invalid operation: {e.errors()[0]['msg']}") from e
    except (AnalysisError, QueryError) as e:
        raise HTTPException(422, str(e)) from e


class AnalyzeIn(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


@router.post("/{ds_id}/analyze")
async def analyze(ds_id: uuid.UUID, body: AnalyzeIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    """AI analyst: model plans typed operations, engine computes them. Narrative is produced via chat."""
    d = await owned(db, user.id, ds_id)
    return await run_analysis(d, body.question)


@router.post("/{ds_id}/export")
async def export(ds_id: uuid.UUID, body: SQLIn, user: CurrentUser, db: DB) -> Response:
    """Export the result of a guarded query (e.g. a filtered/transformed view) as CSV."""
    d = await owned(db, user.id, ds_id)
    try:
        res = await asyncio.to_thread(run_sql, d.parquet_path, body.sql)
    except (UnsafeSQL, QueryError) as e:
        raise HTTPException(422, str(e)) from e
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(res.columns)
    w.writerows(res.rows)
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{d.name}-export.csv"'},
    )


@router.delete("/{ds_id}", status_code=204)
async def delete(ds_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    d = await owned(db, user.id, ds_id)
    await asyncio.to_thread(Path(d.parquet_path).unlink, missing_ok=True)
    await db.delete(d)
    await db.commit()
