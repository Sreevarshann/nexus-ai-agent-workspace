"""Document upload validation, storage and indexing."""

from __future__ import annotations

import asyncio
import hashlib
import re
import uuid
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from nexus.config import get_settings
from nexus.db import session_scope
from nexus.domain.chunking import chunk_pages
from nexus.llm.factory import get_llm
from nexus.logging import log
from nexus.models import Document, DocumentChunk
from nexus.rag.extract import DOC_TYPES, ExtractionError, extract, sniff_ok


class UploadRejected(ValueError):
    pass


def safe_filename(name: str) -> str:
    name = Path(name).name  # strip any directory components
    name = re.sub(r"[^\w.\- ()]+", "_", name).strip(" .") or "upload"
    return name[:200]


async def store_upload(
    db: AsyncSession, user_id: uuid.UUID, filename: str, data: bytes, project_id: uuid.UUID | None
) -> tuple[Document, bool]:
    """Validate and persist an upload. Returns (document, created). Duplicate content is deduplicated."""
    s = get_settings()
    filename = safe_filename(filename)
    suffix = Path(filename).suffix.lower()
    if suffix not in DOC_TYPES:
        raise UploadRejected(f"Unsupported file type '{suffix or filename}'. Allowed: {', '.join(DOC_TYPES)}")
    if not data:
        raise UploadRejected("File is empty")
    if len(data) > s.max_upload_bytes:
        raise UploadRejected(f"File exceeds {s.max_upload_bytes // (1024 * 1024)} MB limit")
    if not sniff_ok(suffix, data[:4096]):
        raise UploadRejected("File contents do not match its extension")

    digest = hashlib.sha256(data).hexdigest()
    existing = (
        await db.execute(select(Document).where(Document.user_id == user_id, Document.sha256 == digest))
    ).scalar()
    if existing:
        return existing, False

    user_dir = s.upload_dir / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / f"{digest}{suffix}"
    path.write_bytes(data)
    doc = Document(
        user_id=user_id,
        project_id=project_id,
        filename=filename,
        mime=DOC_TYPES[suffix],
        size=len(data),
        sha256=digest,
        storage_path=str(path),
        status="queued",
    )
    db.add(doc)
    await db.commit()
    return doc, True


async def ingest_document(document_id: uuid.UUID) -> None:
    """Extract → chunk → embed → index. Idempotent: re-running replaces the document's chunks."""
    async with session_scope() as db:
        doc = await db.get(Document, document_id)
        if doc is None:
            return
        doc.status, doc.error = "processing", None
        path, suffix, user_id = Path(doc.storage_path), Path(doc.filename).suffix.lower(), doc.user_id

    try:
        extracted = extract(path, suffix)
        chunks = chunk_pages(extracted.pages)
        if not chunks:
            raise ExtractionError("No text content found")
        vectors = await get_llm().embed([c.text for c in chunks], kind="document")
    except Exception as e:
        log.warning("ingest_failed", document_id=str(document_id), error=str(e))
        async with session_scope() as db:
            doc = await db.get(Document, document_id)
            if doc:
                doc.status, doc.error = "failed", str(e)[:1000]
        return

    async with session_scope() as db:
        await db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
        for c, v in zip(chunks, vectors, strict=True):
            db.add(
                DocumentChunk(
                    document_id=document_id, user_id=user_id, ord=c.ord, text=c.text, page=c.page, embedding=v
                )
            )
        doc = await db.get(Document, document_id)
        assert doc is not None
        doc.status, doc.chunk_count, doc.page_count = "ready", len(chunks), extracted.page_count
        doc.meta = {**(doc.meta or {}), **extracted.meta}
    log.info("ingested", document_id=str(document_id), chunks=len(chunks))


async def delete_document(db: AsyncSession, doc: Document) -> None:
    """Delete the row (chunks and citations cascade) and the stored file."""
    path = Path(doc.storage_path)
    await db.delete(doc)
    await db.commit()
    still_used = (await db.execute(select(Document.id).where(Document.storage_path == str(path)))).first()
    if not still_used:
        await asyncio.to_thread(path.unlink, missing_ok=True)
