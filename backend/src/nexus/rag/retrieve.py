"""Hybrid retrieval: pgvector cosine similarity + Postgres full-text search, fused with reciprocal rank fusion."""

from __future__ import annotations

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.llm.factory import get_llm

RRF_K = 60


@dataclass
class Hit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page: int | None
    text: str
    score: float
    vector_rank: int | None = None
    keyword_rank: int | None = None
    similarity: float | None = None
    signals: list[str] = field(default_factory=list)


def to_or_tsquery(query: str) -> str:
    words = [w for w in re.findall(r"[A-Za-z0-9]+", query.lower()) if len(w) > 2][:24]
    return " | ".join(words)


async def hybrid_search(
    db: AsyncSession,
    user_id: uuid.UUID,
    query: str,
    k: int = 6,
    document_ids: list[uuid.UUID] | None = None,
    candidates: int = 30,
) -> list[Hit]:
    [qvec] = await get_llm().embed([query], kind="query")
    scope = "c.user_id = :uid AND d.status = 'ready'"
    params: dict[str, object] = {"uid": user_id, "n": candidates}
    if document_ids:
        scope += " AND c.document_id = ANY(:docs)"
        params["docs"] = list(document_ids)

    vec_rows = (
        await db.execute(
            text(f"""
        SELECT c.id, c.document_id, d.filename, c.page, c.text, 1 - (c.embedding <=> CAST(:q AS vector)) AS sim
        FROM document_chunks c JOIN documents d ON d.id = c.document_id
        WHERE {scope} AND c.embedding IS NOT NULL
        ORDER BY c.embedding <=> CAST(:q AS vector) LIMIT :n"""),
            {**params, "q": str(qvec)},
        )
    ).all()

    kw_rows: Sequence[Any] = []
    tsq = to_or_tsquery(query)
    if tsq:
        kw_rows = (
            await db.execute(
                text(f"""
            SELECT c.id, c.document_id, d.filename, c.page, c.text,
                   ts_rank_cd(c.tsv, to_tsquery('english', :tsq)) AS rank
            FROM document_chunks c JOIN documents d ON d.id = c.document_id
            WHERE {scope} AND c.tsv @@ to_tsquery('english', :tsq)
            ORDER BY rank DESC LIMIT :n"""),
                {**params, "tsq": tsq},
            )
        ).all()

    hits: dict[uuid.UUID, Hit] = {}
    for rank, r in enumerate(vec_rows, 1):
        h = hits.setdefault(r.id, Hit(r.id, r.document_id, r.filename, r.page, r.text, 0.0))
        h.vector_rank, h.similarity = rank, float(r.sim)
        h.score += 1 / (RRF_K + rank)
        h.signals.append("vector")
    for rank, r in enumerate(kw_rows, 1):
        h = hits.setdefault(r.id, Hit(r.id, r.document_id, r.filename, r.page, r.text, 0.0))
        h.keyword_rank = rank
        h.score += 1 / (RRF_K + rank)
        h.signals.append("keyword")
    return sorted(hits.values(), key=lambda h: h.score, reverse=True)[:k]
