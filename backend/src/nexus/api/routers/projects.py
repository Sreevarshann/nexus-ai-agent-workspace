"""Projects within the user's workspace."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from nexus.api.deps import DB, CurrentUser, not_found
from nexus.models import Artifact, Conversation, Dataset, Document, Project, Task, Workspace

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    pinned: bool | None = None


class ProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    pinned: bool
    created_at: datetime
    updated_at: datetime
    counts: dict[str, int] = {}


async def get_owned_project(db: DB, user_id: uuid.UUID, project_id: uuid.UUID) -> Project:
    p = await db.get(Project, project_id)
    if p is None or p.user_id != user_id:
        raise not_found("Project")
    return p


@router.get("", response_model=list[ProjectOut])
async def list_projects(user: CurrentUser, db: DB) -> list[ProjectOut]:
    rows = (
        (
            await db.execute(
                select(Project)
                .where(Project.user_id == user.id)
                .order_by(Project.pinned.desc(), Project.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )
    out = []
    for p in rows:
        counts = {}
        for key, model in (
            ("conversations", Conversation),
            ("documents", Document),
            ("datasets", Dataset),
            ("artifacts", Artifact),
            ("tasks", Task),
        ):
            counts[key] = await db.scalar(select(func.count()).select_from(model).where(model.project_id == p.id)) or 0
        out.append(ProjectOut.model_validate(p, from_attributes=True).model_copy(update={"counts": counts}))
    return out


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectIn, user: CurrentUser, db: DB) -> ProjectOut:
    ws = (await db.execute(select(Workspace).where(Workspace.user_id == user.id))).scalar()
    if ws is None:
        ws = Workspace(user_id=user.id, name="Workspace")
        db.add(ws)
        await db.flush()
    p = Project(user_id=user.id, workspace_id=ws.id, name=body.name, description=body.description)
    db.add(p)
    await db.commit()
    return ProjectOut.model_validate(p, from_attributes=True)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(project_id: uuid.UUID, body: ProjectPatch, user: CurrentUser, db: DB) -> ProjectOut:
    p = await get_owned_project(db, user.id, project_id)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    await db.commit()
    await db.refresh(p)
    return ProjectOut.model_validate(p, from_attributes=True)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    p = await get_owned_project(db, user.id, project_id)
    await db.delete(p)
    await db.commit()
