"""Knowledge library: upload, list, inspect, search, delete."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from nexus.api.deps import DB, CurrentUser, not_found
from nexus.api.routers.projects import get_owned_project
from nexus.config import get_settings
from nexus.jobs import enqueue
from nexus.models import Document, DocumentChunk
from nexus.rag.ingest import UploadRejected, delete_document, store_upload
from nexus.rag.retrieve import hybrid_search

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentOut(BaseModel):
    id: uuid.UUID
    filename: str
    mime: str
    size: int
    status: str
    error: str | None
    page_count: int | None
    chunk_count: int
    project_id: uuid.UUID | None
    meta: dict[str, Any]
    created_at: datetime


async def owned_document(db: DB, user_id: uuid.UUID, doc_id: uuid.UUID) -> Document:
    d = await db.get(Document, doc_id)
    if d is None or d.user_id != user_id:
        raise not_found("Document")
    return d


async def read_limited(file: UploadFile) -> bytes:
    limit = get_settings().max_upload_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File exceeds {limit // (1024 * 1024)} MB limit")
    return data


@router.post("", response_model=DocumentOut, status_code=201)
async def upload(
    user: CurrentUser, db: DB, file: UploadFile = File(...), project_id: uuid.UUID | None = Form(default=None)
) -> Document:
    if project_id:
        await get_owned_project(db, user.id, project_id)
    data = await read_limited(file)
    try:
        doc, created = await store_upload(db, user.id, file.filename or "upload", data, project_id)
    except UploadRejected as e:
        raise HTTPException(422, str(e)) from e
    if created or doc.status == "failed":
        await enqueue("ingest", str(doc.id))
    return doc


@router.get("", response_model=list[DocumentOut])
async def list_documents(user: CurrentUser, db: DB, project_id: uuid.UUID | None = None) -> list[Any]:
    stmt = select(Document).where(Document.user_id == user.id)
    if project_id:
        stmt = stmt.where(Document.project_id == project_id)
    return list((await db.execute(stmt.order_by(Document.created_at.desc()))).scalars())


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_document(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> Document:
    return await owned_document(db, user.id, doc_id)


@router.get("/{doc_id}/chunks")
async def get_chunks(
    doc_id: uuid.UUID, user: CurrentUser, db: DB, page: int | None = None, limit: int = 50, offset: int = 0
) -> list[dict[str, Any]]:
    await owned_document(db, user.id, doc_id)
    stmt = select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
    if page is not None:
        stmt = stmt.where(DocumentChunk.page == page)
    rows = (await db.execute(stmt.order_by(DocumentChunk.ord).offset(offset).limit(min(limit, 200)))).scalars()
    return [{"id": str(c.id), "ord": c.ord, "page": c.page, "text": c.text} for c in rows]


@router.get("/chunks/{chunk_id}")
async def get_chunk(chunk_id: uuid.UUID, user: CurrentUser, db: DB) -> dict[str, Any]:
    c = await db.get(DocumentChunk, chunk_id)
    if c is None or c.user_id != user.id:
        raise not_found("Passage")
    d = await db.get(Document, c.document_id)
    return {
        "id": str(c.id),
        "document_id": str(c.document_id),
        "filename": d.filename if d else "",
        "mime": d.mime if d else "",
        "page": c.page,
        "ord": c.ord,
        "text": c.text,
    }


@router.get("/{doc_id}/file")
async def download(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> FileResponse:
    d = await owned_document(db, user.id, doc_id)
    path = await asyncio.to_thread(Path(d.storage_path).resolve)
    root = await asyncio.to_thread(get_settings().upload_dir.resolve)
    if not path.is_relative_to(root) or not await asyncio.to_thread(path.exists):
        raise not_found("File")
    return FileResponse(
        path,
        media_type=d.mime,
        filename=d.filename,
        content_disposition_type="inline" if d.mime == "application/pdf" else "attachment",
    )


@router.post("/{doc_id}/reindex", response_model=DocumentOut)
async def reindex(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> Document:
    d = await owned_document(db, user.id, doc_id)
    d.status = "queued"
    await db.commit()
    await enqueue("ingest", str(d.id))
    return d


@router.delete("/{doc_id}", status_code=204)
async def remove(doc_id: uuid.UUID, user: CurrentUser, db: DB) -> None:
    await delete_document(db, await owned_document(db, user.id, doc_id))


class SearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=1000)
    k: int = Field(default=8, ge=1, le=30)
    document_ids: list[uuid.UUID] | None = None


@router.post("/search")
async def search(body: SearchIn, user: CurrentUser, db: DB) -> list[dict[str, Any]]:
    hits = await hybrid_search(db, user.id, body.query, body.k, body.document_ids)
    return [
        {
            "chunk_id": str(h.chunk_id),
            "document_id": str(h.document_id),
            "filename": h.filename,
            "page": h.page,
            "text": h.text,
            "score": round(h.score, 5),
            "similarity": h.similarity,
            "vector_rank": h.vector_rank,
            "keyword_rank": h.keyword_rank,
            "signals": h.signals,
        }
        for h in hits
    ]
