"""Content extraction for supported upload types. Parsers run on untrusted files with hard limits."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MAX_PDF_PAGES = 1500
MAX_TEXT_CHARS = 5_000_000

DOC_TYPES = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class ExtractionError(ValueError):
    pass


@dataclass
class Extracted:
    pages: list[tuple[int | None, str]]
    page_count: int | None = None
    meta: dict[str, Any] = field(default_factory=dict)


def sniff_ok(suffix: str, head: bytes) -> bool:
    """Check magic bytes so a renamed binary cannot masquerade as a supported type."""
    if suffix == ".pdf":
        return head.startswith(b"%PDF-")
    if suffix in (".xlsx", ".docx"):
        return head.startswith(b"PK\x03\x04")
    # text types: reject NUL bytes and invalid UTF-8 in the sample
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError as e:
        # a multibyte character may be cut at the sample boundary
        return e.start >= len(head) - 3
    return True


def extract(path: Path, suffix: str) -> Extracted:
    if suffix == ".pdf":
        return _pdf(path)
    if suffix in (".txt", ".md", ".markdown"):
        text = path.read_text(encoding="utf-8", errors="replace")[:MAX_TEXT_CHARS]
        pages: list[tuple[int | None, str]] = [(None, text)]
        return Extracted(pages=pages)
    if suffix == ".csv":
        return _csv(path)
    if suffix == ".xlsx":
        return _xlsx(path)
    if suffix == ".docx":
        return _docx(path)
    raise ExtractionError(f"Unsupported file type {suffix}")


def _pdf(path: Path) -> Extracted:
    import pymupdf

    try:
        doc = pymupdf.open(path)
    except Exception as e:
        raise ExtractionError(f"Could not open PDF: {e}") from e
    with doc:
        if doc.needs_pass:
            raise ExtractionError("Encrypted PDFs are not supported")
        if doc.page_count > MAX_PDF_PAGES:
            raise ExtractionError(f"PDF has {doc.page_count} pages; limit is {MAX_PDF_PAGES}")
        pages: list[tuple[int | None, str]] = [(i + 1, str(doc[i].get_text("text"))) for i in range(doc.page_count)]
        md = {
            k: v for k, v in (doc.metadata or {}).items() if v and k in ("title", "author", "subject", "creationDate")
        }
        if not any(t.strip() for _, t in pages):
            raise ExtractionError("PDF contains no extractable text (scanned images are not OCR'd)")
        return Extracted(pages=pages, page_count=doc.page_count, meta=md)


def _table_text(header: list[str], rows: list[list[Any]], label: str) -> str:
    lines = [f"{label} with columns: {', '.join(header)}"]
    for r in rows:
        lines.append("; ".join(f"{h}: {v}" for h, v in zip(header, r, strict=False) if v not in (None, "")))
    return "\n".join(lines)


def _csv(path: Path) -> Extracted:
    with path.open(newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader, [])
        rows = [r for _, r in zip(range(2000), reader, strict=False)]
    # one "page" per 40 rows keeps chunks coherent
    pages: list[tuple[int | None, str]] = [
        (None, _table_text(header, rows[i : i + 40], f"Rows {i + 1}-{i + len(rows[i : i + 40])}"))
        for i in range(0, len(rows), 40)
    ]
    return Extracted(pages=pages or [(None, ", ".join(header))], meta={"columns": header, "rows_indexed": len(rows)})


def _xlsx(path: Path) -> Extracted:
    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    pages: list[tuple[int | None, str]] = []
    for ws in wb.worksheets[:20]:
        it = ws.iter_rows(values_only=True)
        header = [str(h) if h is not None else "" for h in next(it, ())]
        rows = [list(r) for _, r in zip(range(2000), it, strict=False)]
        for i in range(0, len(rows), 40):
            pages.append((None, _table_text(header, rows[i : i + 40], f"Sheet {ws.title} rows {i + 1}+")))
    wb.close()
    return Extracted(pages=pages, meta={"sheets": len(pages)})


def _docx(path: Path) -> Extracted:
    import docx

    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for table in d.tables:
        for row in table.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells))
    return Extracted(pages=[(None, "\n\n".join(parts))])


def decode_preview(data: bytes, limit: int = 4000) -> str:
    return io.BytesIO(data).read(limit).decode("utf-8", errors="replace")
