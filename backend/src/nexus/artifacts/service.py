"""Versioned artifact storage."""

from __future__ import annotations

import uuid
from typing import Any

from nexus.db import session_scope
from nexus.models import Artifact, ArtifactVersion


async def create_artifact(
    user_id: uuid.UUID,
    title: str,
    kind: str,
    content: str,
    data: dict[str, Any] | None = None,
    *,
    task_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    note: str = "Generated",
) -> Artifact:
    async with session_scope() as db:
        art = Artifact(
            user_id=user_id,
            title=title[:240],
            kind=kind,
            task_id=task_id,
            project_id=project_id,
            conversation_id=conversation_id,
            current_version=1,
        )
        db.add(art)
        await db.flush()
        db.add(ArtifactVersion(artifact_id=art.id, version=1, content=content, data=data or {}, note=note))
    return art


async def add_version(artifact: Artifact, content: str, data: dict[str, Any], note: str) -> ArtifactVersion:
    async with session_scope() as db:
        art = await db.get(Artifact, artifact.id)
        assert art is not None
        art.current_version += 1
        v = ArtifactVersion(artifact_id=art.id, version=art.current_version, content=content, data=data, note=note)
        db.add(v)
    return v
