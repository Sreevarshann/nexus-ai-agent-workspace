"""Artifact Studio API: list, view versions, edit (new version), export."""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from nexus.api.deps import DB, CurrentUser, not_found
from nexus.artifacts.export import FORMATS, available_formats, render
from nexus.models import Artifact, ArtifactVersion

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


class ArtifactSummary(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    current_version: int
    task_id: uuid.UUID | None
    project_id: uuid.UUID | None
    conversation_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


async def owned(db: DB, user_id: uuid.UUID, aid: uuid.UUID) -> Artifact:
    a = await db.get(Artifact, aid)
    if a is None or a.user_id != user_id:
        raise not_found("Artifact")
    await db.refresh(a, ["versions"])
    return a


def _version(v: ArtifactVersion) -> dict[str, Any]:
    return {"version": v.version, "content": v.content, "data": v.data, "note": v.note, "created_at": v.created_at}


@router.get("", response_model=list[ArtifactSummary])
async def list_artifacts(
    user: CurrentUser, db: DB, project_id: uuid.UUID | None = None, task_id: uuid.UUID | None = None
) -> list[Any]:
    stmt = select(Artifact).where(Artifact.user_id == user.id)
    if project_id:
        stmt = stmt.where(Artifact.project_id == project_id)
    if task_id:
        stmt = stmt.where(Artifact.task_id == task_id)
    return list((await db.execute(stmt.order_by(Artifact.updated_at.desc()))).scalars())


@router.get("/{aid}")
async def get_artifact(aid: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    a = await owned(db, user.id, aid)
    latest = a.versions[-1]
    return {
        **ArtifactSummary.model_validate(a, from_attributes=True).model_dump(mode="json"),
        "versions": [{"version": v.version, "note": v.note, "created_at": v.created_at} for v in a.versions],
        "latest": _version(latest),
        "formats": available_formats(latest),
    }


@router.get("/{aid}/versions/{version}")
async def get_version(aid: uuid.UUID, version: int, user: CurrentUser, db: DB) -> dict[str, Any]:
    a = await owned(db, user.id, aid)
    v = next((v for v in a.versions if v.version == version), None)
    if v is None:
        raise not_found("Version")
    return _version(v)


class EditIn(BaseModel):
    content: str = Field(max_length=500_000)
    title: str | None = Field(default=None, max_length=240)
    note: str = Field(default="Edited", max_length=240)


@router.post("/{aid}/versions")
async def edit(aid: uuid.UUID, body: EditIn, user: CurrentUser, db: DB) -> dict[str, Any]:
    a = await owned(db, user.id, aid)
    latest = a.versions[-1]
    a.current_version += 1
    if body.title:
        a.title = body.title
    v = ArtifactVersion(
        artifact_id=a.id, version=a.current_version, content=body.content, data=latest.data, note=body.note
    )
    db.add(v)
    await db.commit()
    return _version(v)


@router.get("/{aid}/export")
async def export(
    aid: uuid.UUID,
    user: CurrentUser,
    db: DB,
    format: Literal["md", "json", "csv", "pdf"] = "md",
    version: int | None = None,
) -> Response:
    a = await owned(db, user.id, aid)
    v = next((x for x in a.versions if x.version == version), None) if version else a.versions[-1]
    if v is None:
        raise not_found("Version")
    try:
        body = render(a, v, format)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    slug = re.sub(r"[^a-z0-9]+", "-", a.title.lower()).strip("-")[:60] or "artifact"
    return Response(
        body,
        media_type=FORMATS[format],
        headers={"Content-Disposition": f'attachment; filename="{slug}-v{v.version}.{format}"'},
    )


@router.delete("/{aid}", status_code=204)
async def delete(aid: uuid.UUID, user: CurrentUser, db: DB) -> None:
    a = await owned(db, user.id, aid)
    await db.delete(a)
    await db.commit()
