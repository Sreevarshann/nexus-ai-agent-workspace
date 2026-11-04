"""Conversation generation.

Generation runs as a server-side task that appends events to a Redis stream (``msg:<id>:stream``). The
browser reads that stream over SSE and can reconnect from any offset, so a refresh mid-answer loses nothing,
and the final message is persisted to Postgres regardless of whether a client is connected.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from nexus.agents.analyst import run_analysis, stream_narrative
from nexus.agents.evidence import Evidence, gather_docs, gather_web, render_evidence
from nexus.agents.prompts import ASSISTANT_SYSTEM, GROUNDED_RULES
from nexus.agents.verify import used_labels
from nexus.config import get_settings
from nexus.db import session_scope
from nexus.llm.base import ChatMessage, LLMError, structured
from nexus.llm.factory import get_llm
from nexus.logging import log
from nexus.models import Dataset, Message, Task
from nexus.redis import get_redis
from nexus.tools.registry import ToolContext

STREAM_TTL_S = 3600
_running: dict[uuid.UUID, asyncio.Task[None]] = {}


def stream_key(message_id: uuid.UUID | str) -> str:
    return f"msg:{message_id}:stream"


def cancel_key(message_id: uuid.UUID | str) -> str:
    return f"msg:{message_id}:cancel"


async def push(message_id: uuid.UUID, type_: str, **data: Any) -> None:
    r = get_redis()
    await r.xadd(stream_key(message_id), {"type": type_, "data": json.dumps(data, default=str)})
    await r.expire(stream_key(message_id), STREAM_TTL_S)


class Suggestions(BaseModel):
    questions: list[str] = Field(min_length=1, max_length=3, description="Short follow-up questions")


def start(message_id: uuid.UUID) -> None:
    task = asyncio.create_task(_generate(message_id))
    _running[message_id] = task
    task.add_done_callback(lambda _: _running.pop(message_id, None))


async def wait_all() -> None:
    """Test helper."""
    while _running:
        await asyncio.gather(*list(_running.values()), return_exceptions=True)


async def _history(conversation_id: uuid.UUID, before: Any) -> list[ChatMessage]:
    async with session_scope() as db:
        rows = (
            (
                await db.execute(
                    select(Message)
                    .where(
                        Message.conversation_id == conversation_id,
                        Message.created_at < before,
                        Message.status == "complete",
                    )
                    .order_by(Message.created_at.desc())
                    .limit(12)
                )
            )
            .scalars()
            .all()
        )
    return [ChatMessage("user" if m.role == "user" else "assistant", m.content[:6000]) for m in reversed(rows)]


async def _generate(message_id: uuid.UUID) -> None:
    started = time.perf_counter()
    async with session_scope() as db:
        msg = await db.get(Message, message_id)
        assert msg is not None
        from nexus.models import Conversation

        conv = await db.get(Conversation, msg.conversation_id)
        assert conv is not None
        user_msg_id = (msg.meta or {}).get("reply_to")
        user_msg = await db.get(Message, uuid.UUID(user_msg_id)) if user_msg_id else None
        assert user_msg is not None
        mode, attachments, user_id, created = (
            user_msg.mode,
            user_msg.attachments or [],
            conv.user_id,
            user_msg.created_at,
        )
        question, conv_id, options = user_msg.content, conv.id, (user_msg.meta or {}).get("options", {})

    ctx = ToolContext(user_id=user_id, origin="chat")
    content: list[str] = []
    citations: list[dict[str, Any]] = []
    meta: dict[str, Any] = {}
    status, error = "complete", None
    llm = get_llm()

    tool_log: list[dict[str, Any]] = []

    async def tool_event(type_: str, **payload: Any) -> None:
        # persisted (compactly) so the tool trace survives reloads, not just the live stream
        tool_log.append({"event": type_, **{k: v for k, v in payload.items() if k not in ("plan", "excerpt")}})
        await push(message_id, "tool", event=type_, **payload)

    try:
        history = await _history(conv_id, created)
        evidence: list[Evidence] = []
        system = ASSISTANT_SYSTEM
        prompt_msgs: list[ChatMessage]
        doc_ids = [a["id"] for a in attachments if a.get("kind") == "document"]
        dataset_ids = [a["id"] for a in attachments if a.get("kind") == "dataset"]

        if mode == "analysis":
            ds_id = dataset_ids[0] if dataset_ids else None
            async with session_scope() as db:
                ds = (
                    await db.get(Dataset, uuid.UUID(ds_id))
                    if ds_id
                    else (
                        await db.execute(
                            select(Dataset).where(Dataset.user_id == user_id).order_by(Dataset.created_at.desc())
                        )
                    ).scalar()
                )
            if ds is None or ds.user_id != user_id:
                raise ValueError("Analysis mode needs a dataset. Upload one in the Data Lab or attach it.")
            await push(message_id, "status", text=f"Analysing {ds.name}…")
            analysis = await run_analysis(ds, question, tool_event)
            meta["analysis"] = {**analysis, "results": [{**r, "rows": r["rows"][:500]} for r in analysis["results"]]}
            await push(message_id, "analysis", analysis=meta["analysis"])
            async for delta in stream_narrative(question, analysis):
                if await get_redis().exists(cancel_key(message_id)):
                    status = "cancelled"
                    break
                content.append(delta)
                await push(message_id, "delta", text=delta)
            prompt_msgs = []
            used = used_labels("".join(content))
            citations = [
                {"label": r["label"], "kind": "data", "title": r["title"], "sql": r["sql"]}
                for r in analysis["results"]
                if r["label"] in used
            ]
        else:
            if mode == "research":
                await push(message_id, "status", text="Searching the web…")
                evidence, errs = await gather_web(
                    ctx, [question[:300]], int(options.get("max_sources", 3)), tool_event, per_query=6
                )
                if errs and not evidence:
                    meta["research_errors"] = errs[:5]
            if doc_ids or options.get("use_library"):
                await push(message_id, "status", text="Searching your documents…")
                docs, _ = await gather_docs(
                    ctx, [question[:500]], 6, doc_ids or None, tool_event, start_label=len(evidence) + 1
                )
                evidence += docs
            if evidence:
                system += " " + GROUNDED_RULES
                user_content = f"{render_evidence(evidence)}\n\nQuestion: {question}"
            elif mode == "research":
                user_content = (
                    f"Question: {question}\n\n(No web sources could be retrieved: "
                    f"{'; '.join(meta.get('research_errors', ['search unavailable']))[:400]}. "
                    "Say that live sources were unavailable before answering from general knowledge.)"
                )
            else:
                user_content = question
            prompt_msgs = [ChatMessage("system", system), *history, ChatMessage("user", user_content)]
            if evidence:
                await push(message_id, "sources", sources=[e.citation() for e in evidence])
            await push(message_id, "status", text="Generating…")
            usage = None
            async for chunk in llm.stream_chat(prompt_msgs):
                if chunk.delta:
                    content.append(chunk.delta)
                    await push(message_id, "delta", text=chunk.delta)
                if chunk.done:
                    usage = chunk.usage
                if await get_redis().exists(cancel_key(message_id)):
                    status = "cancelled"
                    break
            if usage:
                meta["tokens"] = {"prompt": usage.prompt_tokens, "completion": usage.completion_tokens}
            text = "".join(content)
            used = used_labels(text)
            known = {e.label for e in evidence}
            for bogus in used - known:  # never show a citation to evidence that was not retrieved
                text = text.replace(f"[{bogus}]", "")
            content = [text]
            if used - known:
                meta["removed_citations"] = sorted(used - known)
            citations = [e.citation() for e in evidence if e.label in used]
            meta["evidence_count"] = len(evidence)
    except (LLMError, ValueError, LookupError) as e:
        status, error = "error", str(e)
    except Exception as e:  # never leave a message stuck in "streaming"
        log.exception("generation_failed", message_id=str(message_id))
        status, error = "error", f"{type(e).__name__}: {e}"

    text = "".join(content)
    meta.update(model=llm.model, provider=llm.name, latency_ms=int((time.perf_counter() - started) * 1000))
    if tool_log:
        meta["tools"] = tool_log[:60]
    if error:
        meta["error"] = error
    async with session_scope() as db:
        m = await db.get(Message, message_id)
        if m:
            m.content, m.status, m.citations = text, status, citations
            m.meta = {**(m.meta or {}), **meta}
    await push(message_id, "done", status=status, content=text, citations=citations, meta=meta)

    if status == "complete" and text and get_settings().env != "test":
        try:
            sug = await asyncio.wait_for(
                structured(
                    llm,
                    [
                        ChatMessage(
                            "system", "Suggest up to 3 short, specific follow-up questions the user might ask next."
                        ),
                        ChatMessage("user", f"Question: {question[:800]}\n\nAnswer: {text[:2500]}"),
                    ],
                    Suggestions,
                ),
                25,
            )
            async with session_scope() as db:
                m = await db.get(Message, message_id)
                if m:
                    m.meta = {**m.meta, "suggestions": sug.questions[:3]}
            await push(message_id, "suggestions", questions=sug.questions[:3])
        except (TimeoutError, LLMError):
            pass
    await push(message_id, "end")
    await get_redis().delete(cancel_key(message_id))


async def start_agent_message(message_id: uuid.UUID, task: Task) -> None:
    async with session_scope() as db:
        m = await db.get(Message, message_id)
        if m:
            m.meta = {**(m.meta or {}), "task_id": str(task.id)}
    await push(message_id, "task", task_id=str(task.id))
    await push(message_id, "end")


async def mark_interrupted() -> None:
    """On startup: messages left 'streaming' by a crashed process are marked honestly."""
    async with session_scope() as db:
        rows = (await db.execute(select(Message).where(Message.status == "streaming"))).scalars().all()
        for m in rows:
            if (m.meta or {}).get("task_id"):
                continue  # agent messages are owned by the worker
            m.status = "error"
            m.meta = {**(m.meta or {}), "error": "Generation was interrupted by a server restart. Retry to regenerate."}
