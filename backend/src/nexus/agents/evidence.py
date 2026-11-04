"""Evidence gathering shared by chat research mode, missions and workflows."""

from __future__ import annotations

import asyncio
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from nexus.domain.untrusted import evidence_block
from nexus.tools.registry import ToolContext, ToolError, invoke

EventCb = Callable[..., Awaitable[Any]]


@dataclass
class Evidence:
    label: str
    kind: str  # web | doc
    title: str
    text: str
    url: str | None = None
    domain: str | None = None
    source_id: str | None = None
    chunk_id: str | None = None
    document_id: str | None = None
    filename: str | None = None
    page: int | None = None
    score: float | None = None
    retrieved_at: str | None = None
    flags: list[str] = field(default_factory=list)

    def header(self) -> str:
        if self.kind == "web":
            return f"{self.title} ({self.domain})"
        return f"{self.filename}" + (f", page {self.page}" if self.page else "")

    def citation(self) -> dict[str, Any]:
        d = asdict(self)
        d["excerpt"] = self.text[:500]
        d.pop("text")
        return d


def relevant_passages(text: str, query: str, max_chars: int = 1400) -> str:
    """Select the paragraphs with the highest query-term overlap, in document order."""
    terms = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 3}
    paras = [p.strip() for p in re.split(r"\n+", text) if len(p.strip()) > 40]
    if not paras:
        return text[:max_chars]
    scored = sorted(range(len(paras)), key=lambda i: -sum(1 for t in terms if t in paras[i].lower()))
    keep: list[int] = []
    total = 0
    for i in scored:
        if total + len(paras[i]) > max_chars and keep:
            continue
        keep.append(i)
        total += len(paras[i])
        if total >= max_chars:
            break
    return "\n".join(paras[i] for i in sorted(keep))[:max_chars]


async def gather_web(
    ctx: ToolContext,
    queries: list[str],
    max_sources: int,
    emit: EventCb | None = None,
    per_query: int = 6,
    start_label: int = 1,
) -> tuple[list[Evidence], list[str]]:
    """Search each query, pick diverse results, retrieve them. Returns (evidence, errors)."""
    errors: list[str] = []
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for q in queries:
        try:
            res = await invoke("web_search", {"query": q, "limit": per_query}, ctx)
        except ToolError as e:
            errors.append(f"Search '{q}' failed: {e}")
            if emit:
                await emit("tool_call", tool="web_search", args={"query": q}, status="error", error=str(e))
            continue
        if emit:
            await emit(
                "tool_call",
                tool="web_search",
                args={"query": q},
                status="ok",
                result={
                    "count": len(res["results"]),
                    "top": [{"title": r["title"], "url": r["url"]} for r in res["results"][:5]],
                },
            )
        for r in res["results"]:
            if r["url"] not in seen:
                seen.add(r["url"])
                candidates.append({**r, "query": q})

    # Round-robin across queries, at most 2 per domain, to diversify evidence.
    by_query: dict[str, list[dict[str, Any]]] = {}
    for c in candidates:
        by_query.setdefault(c["query"], []).append(c)
    picked: list[dict[str, Any]] = []
    per_domain: dict[str, int] = {}
    # over-select so failed fetches can be replaced
    target = max_sources + max(2, max_sources // 2)
    while len(picked) < target and any(by_query.values()):
        for q in list(by_query):
            if not by_query[q]:
                continue
            c = by_query[q].pop(0)
            if per_domain.get(c["domain"], 0) >= 2:
                continue
            per_domain[c["domain"]] = per_domain.get(c["domain"], 0) + 1
            picked.append(c)

    sem = asyncio.Semaphore(4)

    async def fetch(c: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
        async with sem:
            try:
                return (
                    c,
                    await invoke("fetch_url", {"url": c["url"], "query": c["query"], "title": c["title"]}, ctx),
                    None,
                )
            except ToolError as e:
                return c, None, str(e)

    evidence: list[Evidence] = []
    results = await asyncio.gather(*(fetch(c) for c in picked))
    from nexus.db import session_scope
    from nexus.models import Source

    for c, src, err in results:
        status = src["status"] if src else "failed"
        if emit:
            await emit(
                "source_retrieved",
                url=c["url"],
                title=(src or {}).get("title") or c["title"],
                domain=c["domain"],
                status=status,
                error=err or (src or {}).get("error"),
                source_id=(src or {}).get("source_id"),
                excerpt=(src or {}).get("excerpt", ""),
                published_at=(src or {}).get("published_at"),
                query=c["query"],
            )
        if src is None or status != "retrieved":
            errors.append(f"{c['url']}: {err or (src or {}).get('error') or status}")
            continue
        if len(evidence) >= max_sources:
            continue
        async with session_scope() as db:
            row = await db.get(Source, uuid.UUID(src["source_id"]))
            content = row.content if row else ""
            retrieved_at = row.retrieved_at.isoformat() if row else None
        flags = [src["error"]] if src.get("error") else []
        evidence.append(
            Evidence(
                label=f"S{start_label + len(evidence)}",
                kind="web",
                title=src["title"],
                text=relevant_passages(content, c["query"]),
                url=src["final_url"] or src["url"],
                domain=src["domain"],
                source_id=src["source_id"],
                retrieved_at=retrieved_at,
                flags=flags,
            )
        )
    return evidence, errors


async def gather_docs(
    ctx: ToolContext,
    queries: list[str],
    k: int,
    document_ids: list[str] | None = None,
    emit: EventCb | None = None,
    start_label: int = 1,
) -> tuple[list[Evidence], list[str]]:
    errors: list[str] = []
    seen: dict[str, Evidence] = {}
    for q in queries:
        args: dict[str, Any] = {"query": q, "k": k}
        if document_ids:
            args["document_ids"] = document_ids
        try:
            res = await invoke("search_documents", args, ctx)
        except ToolError as e:
            errors.append(f"Document search failed: {e}")
            continue
        if emit:
            await emit(
                "tool_call",
                tool="search_documents",
                args={"query": q},
                status="ok",
                result={
                    "count": len(res["hits"]),
                    "top": [{"filename": h["filename"], "page": h["page"]} for h in res["hits"][:5]],
                },
            )
        for h in res["hits"]:
            if h["chunk_id"] in seen:
                continue
            seen[h["chunk_id"]] = Evidence(
                label="",
                kind="doc",
                title=h["filename"],
                text=h["text"],
                chunk_id=h["chunk_id"],
                document_id=h["document_id"],
                filename=h["filename"],
                page=h["page"],
                score=h["score"],
            )
    ev = sorted(seen.values(), key=lambda e: -(e.score or 0))[: k * max(1, min(len(queries), 2))]
    for i, item in enumerate(ev):
        item.label = f"S{start_label + i}"
        if emit:
            await emit(
                "evidence",
                label=item.label,
                kind="doc",
                filename=item.filename,
                page=item.page,
                chunk_id=item.chunk_id,
                excerpt=item.text[:300],
                score=item.score,
            )
    return ev, errors


def render_evidence(evidence: list[Evidence]) -> str:
    return evidence_block([(e.label, e.header(), e.text) for e in evidence])
