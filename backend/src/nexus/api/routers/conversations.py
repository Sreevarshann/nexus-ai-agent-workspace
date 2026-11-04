"""Conversations, messages and resumable SSE streaming."""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from nexus.api.deps import DB, CurrentUser, not_found
from nexus.api.routers.projects import get_owned_project
from nexus.jobs import enqueue
from nexus.models import Conversation, Dataset, Document, Message, Task
from nexus.ratelimit import enforce
from nexus.redis import get_redis
from nexus.services import chat

router = APIRouter(tags=["conversations"])

Mode = Literal["chat", "research", "analysis", "agent"]


class ConversationIn(BaseModel):
    title: str = Field(default="New conversation", max_length=200)
    project_id: uuid.UUID | None = None


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    project_id: uuid.UUID | None = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    title: str
    project_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class Attachment(BaseModel):
    kind: Literal["document", "dataset"]
    id: uuid.UUID


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    mode: Mode = "chat"
    attachments: list[Attachment] = Field(default_factory=list, max_length=10)
    options: dict[str, Any] = Field(default_factory=dict)


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    status: str
    mode: str
    citations: list[Any]
    attachments: list[Any]
    meta: dict[str, Any]
    created_at: datetime


async def owned_conversation(db: DB, user_id: uuid.UUID, cid: uuid.UUID) -> Conversation:
    c = await db.get(Conversation, cid)
    if c is None or c.user_id != user_id:
        raise not_found("Conversation")
    return c


async def owned_message(db: DB, user_id: uuid.UUID, mid: uuid.UUID) -> Message:
    m = await db.get(Message, mid)
    if m is None:
        raise not_found("Message")
    await owned_conversation(db, user_id, m.conversation_id)
    return m


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    user: CurrentUser,
    db: DB,
    project_id: uuid.UUID | None = None,
    q: str | None = Query(default=None, max_length=200),
    limit: int = 50,
) -> list[Any]:
    stmt = select(Conversation).where(Conversation.user_id == user.id)
    if project_id:
        stmt = stmt.where(Conversation.project_id == project_id)
    if q:
        stmt = stmt.where(Conversation.title.ilike(f"%{q}%"))
    return list((await db.execute(stmt.order_by(Conversation.updated_at.desc()).limit(min(limit, 200)))).scalars())


@router.post("/conversations", response_model=ConversationOut, status_code=201)
async def create_conversation(body: ConversationIn, user: CurrentUser, db: DB) -> Conversation:
    if body.project_id:
        await get_owned_project(db, user.id, body.project_id)
    c = Conversation(user_id=user.id, title=body.title, project_id=body.project_id)
    db.add(c)
    await db.commit()
    return c


@router.patch("/conversations/{cid}", response_model=ConversationOut)
async def update_conversation(cid: uuid.UUID, body: ConversationPatch, user: CurrentUser, db: DB) -> Conversation:
    c = await owned_conversation(db, user.id, cid)
    if body.title is not None:
        c.title = body.title
    if body.project_id is not None:
        await get_owned_project(db, user.id, body.project_id)
        c.project_id = body.project_id
    await db.commit()
    await db.refresh(c)
    return c


@router.delete("/conversations/{cid}", status_code=204)
async def delete_conversation(cid: uuid.UUID, user: CurrentUser, db: DB) -> None:
    c = await owned_conversation(db, user.id, cid)
    await db.delete(c)
    await db.commit()


@router.get("/conversations/{cid}/messages", response_model=list[MessageOut])
async def list_messages(cid: uuid.UUID, user: CurrentUser, db: DB) -> list[Any]:
    await owned_conversation(db, user.id, cid)
    return list(
        (await db.execute(select(Message).where(Message.conversation_id == cid).order_by(Message.created_at))).scalars()
    )


async def _validate_attachments(db: DB, user_id: uuid.UUID, atts: list[Attachment]) -> list[dict[str, Any]]:
    out = []
    for a in atts:
        row: Document | Dataset | None = await db.get(Document if a.kind == "document" else Dataset, a.id)
        if row is None or row.user_id != user_id:
            raise not_found("Attachment")
        name = row.filename if isinstance(row, Document) else row.name
        out.append({"kind": a.kind, "id": str(a.id), "name": name})
    return out


@router.post("/conversations/{cid}/messages", response_model=list[MessageOut], status_code=201)
async def send_message(cid: uuid.UUID, body: MessageIn, user: CurrentUser, db: DB) -> list[Message]:
    await enforce(f"chat:{user.id}", 30, 60)
    conv = await owned_conversation(db, user.id, cid)
    atts = await _validate_attachments(db, user.id, body.attachments)
    first = (await db.execute(select(Message.id).where(Message.conversation_id == cid).limit(1))).first() is None
    user_msg = Message(
        conversation_id=cid,
        role="user",
        content=body.content,
        mode=body.mode,
        attachments=atts,
        meta={"options": body.options},
    )
    db.add(user_msg)
    await db.flush()
    asst = Message(
        conversation_id=cid,
        role="assistant",
        content="",
        status="streaming",
        mode=body.mode,
        meta={"reply_to": str(user_msg.id)},
    )
    db.add(asst)
    if first and conv.title == "New conversation":
        conv.title = body.content.strip().splitlines()[0][:80]
    conv.updated_at = user_msg.created_at
    task = None
    if body.mode == "agent":
        mode = body.options.get("mission_mode", "deep")
        if mode not in ("quick", "deep", "compare", "doc_web"):
            raise HTTPException(422, "Invalid mission_mode")
        opts: dict[str, Any] = {"require_approval": bool(body.options.get("require_approval", False))}
        docs = [a["id"] for a in atts if a["kind"] == "document"]
        dsets = [a["id"] for a in atts if a["kind"] == "dataset"]
        if docs:
            opts["document_ids"] = docs
        if dsets:
            opts["dataset_id"] = dsets[0]
        task = Task(
            user_id=user.id,
            project_id=conv.project_id,
            conversation_id=cid,
            kind="mission",
            mode=mode,
            title=body.content[:240],
            prompt=body.content,
            options=opts,
        )
        db.add(task)
    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(asst)
    if task is not None:
        await chat.start_agent_message(asst.id, task)
        await enqueue("run_task", str(task.id))
        await db.refresh(asst)
    else:
        chat.start(asst.id)
    return [user_msg, asst]


@router.post("/messages/{mid}/cancel", status_code=202)
async def cancel_message(mid: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, str]:
    m = await owned_message(db, user.id, mid)
    if m.status != "streaming":
        return {"status": m.status}
    await get_redis().set(chat.cancel_key(mid), "1", ex=600)
    if (m.meta or {}).get("task_id"):
        from nexus.events import request_control

        await request_control(uuid.UUID(m.meta["task_id"]), "cancel")
    return {"status": "cancelling"}


@router.post("/messages/{mid}/regenerate", response_model=MessageOut, status_code=201)
async def regenerate(mid: uuid.UUID, user: CurrentUser, db: DB) -> Message:
    """Replace an assistant reply (retry after error, or regenerate) with a fresh generation."""
    m = await owned_message(db, user.id, mid)
    if m.role != "assistant" or m.status == "streaming":
        raise HTTPException(409, "Only a finished assistant message can be regenerated")
    if (m.meta or {}).get("task_id"):
        raise HTTPException(409, "Agent missions are retried from Mission Control")
    reply_to = (m.meta or {}).get("reply_to")
    await db.execute(delete(Message).where(Message.id == mid))
    new = Message(
        conversation_id=m.conversation_id,
        role="assistant",
        content="",
        status="streaming",
        mode=m.mode,
        meta={"reply_to": reply_to, "regenerated": True},
    )
    db.add(new)
    await db.commit()
    await db.refresh(new)
    chat.start(new.id)
    return new


@router.get("/messages/{mid}/stream")
async def stream_message(
    mid: uuid.UUID, request: Request, user: CurrentUser, db: DB, last_event_id: str | None = Header(default=None)
) -> StreamingResponse:
    """SSE. Resumable: pass ``Last-Event-ID`` (or ``?after=``) to continue from a Redis stream offset."""
    m = await owned_message(db, user.id, mid)
    after = last_event_id or request.query_params.get("after") or "0-0"
    snapshot = MessageOut.model_validate(m, from_attributes=True).model_dump(mode="json")
    await db.close()

    async def gen() -> AsyncIterator[str]:
        r = get_redis()
        cursor = after
        if not await r.exists(chat.stream_key(mid)) and snapshot["status"] != "streaming":
            final = {k: snapshot[k] for k in ("status", "content", "citations", "meta")}
            yield f"event: done\ndata: {json.dumps(final)}\n\n"
            yield "event: end\ndata: {}\n\n"
            return
        idle = 0
        while True:
            if await request.is_disconnected():
                return
            res = await r.xread({chat.stream_key(mid): cursor}, count=200, block=1000)
            if not res:
                idle += 1
                yield ": keep-alive\n\n"
                if idle > 600:
                    return
                continue
            idle = 0
            for _, entries in res:
                for entry_id, fields in entries:
                    cursor = entry_id
                    yield f"id: {entry_id}\nevent: {fields['type']}\ndata: {fields['data']}\n\n"
                    if fields["type"] == "end":
                        return
            await asyncio.sleep(0)

    return StreamingResponse(
        gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
