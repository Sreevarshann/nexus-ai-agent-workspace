"""Artifact export renderers. Every export is generated from stored content on request."""

from __future__ import annotations

import csv
import io
import json
import re
from typing import Any

from fpdf import FPDF

from nexus.models import Artifact, ArtifactVersion

FORMATS = {"md": "text/markdown", "json": "application/json", "csv": "text/csv", "pdf": "application/pdf"}


def tables_of(v: ArtifactVersion) -> list[dict[str, Any]]:
    return [t for t in (v.data or {}).get("tables", []) if t.get("columns")]


def available_formats(v: ArtifactVersion) -> list[str]:
    fmts = ["md", "json", "pdf"]
    if tables_of(v):
        fmts.insert(2, "csv")
    return fmts


def to_markdown(a: Artifact, v: ArtifactVersion) -> bytes:
    body = v.content
    cites = (v.data or {}).get("citations", [])
    if cites and "## Sources" not in body:
        lines = []
        for c in cites:
            where = c.get("url") or (f"page {c['page']}" if c.get("page") else "")
            lines.append(f"- [{c['label']}] {c.get('title') or c.get('filename', '')} — {where}")
        body += "\n\n## Sources\n\n" + "\n".join(lines)
    return f"# {a.title}\n\n{body}\n".encode()


def to_json(a: Artifact, v: ArtifactVersion) -> bytes:
    return json.dumps(
        {
            "id": str(a.id),
            "title": a.title,
            "kind": a.kind,
            "version": v.version,
            "created_at": v.created_at.isoformat(),
            "content": v.content,
            "data": v.data,
        },
        indent=2,
        default=str,
    ).encode()


def to_csv(a: Artifact, v: ArtifactVersion, table_index: int = 0) -> bytes:
    tables = tables_of(v)
    if not tables:
        raise ValueError("This artifact has no tabular data")
    t = tables[min(table_index, len(tables) - 1)]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(t["columns"])
    w.writerows(t["rows"])
    return buf.getvalue().encode()


def _latin(text: str) -> str:
    # Core PDF fonts are Latin-1; replace common typography and drop the rest rather than crash.
    repl = {
        "—": "-",
        "–": "-",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "…": "...",
        "•": "-",
        " ": " ",
        "→": "->",
        "≥": ">=",
        "≤": "<=",
    }
    for k, val in repl.items():
        text = text.replace(k, val)
    return text.encode("latin-1", "replace").decode("latin-1")


def to_pdf(a: Artifact, v: ArtifactVersion) -> bytes:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(True, margin=18)
    pdf.set_margins(18, 18, 18)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(15, 23, 42)
    pdf.multi_cell(0, 9, _latin(a.title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(
        0,
        6,
        _latin(f"NEXUS AI - {a.kind} - version {v.version} - {v.created_at:%Y-%m-%d %H:%M UTC}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)
    pdf.set_text_color(15, 23, 42)
    for line in to_markdown(a, v).decode().splitlines()[2:]:
        s = line.rstrip()
        if s.startswith("|") and set(s.replace("|", "").strip()) <= set("-: "):
            continue
        if s.startswith("#"):
            level = len(s) - len(s.lstrip("#"))
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", {1: 15, 2: 13}.get(level, 11))
            pdf.multi_cell(0, 7, _latin(s.lstrip("# ").strip()), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 10)
        elif not s:
            pdf.ln(3)
        else:
            pdf.set_font("Helvetica", "", 10)
            clean = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
            clean = re.sub(r"`([^`]+)`", r"\1", clean)
            clean = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 (\2)", clean)
            if clean.lstrip().startswith(("- ", "* ")):
                clean = "  - " + clean.lstrip()[2:]
            pdf.multi_cell(0, 5.5, _latin(clean), new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def render(a: Artifact, v: ArtifactVersion, fmt: str) -> bytes:
    if fmt == "md":
        return to_markdown(a, v)
    if fmt == "json":
        return to_json(a, v)
    if fmt == "csv":
        return to_csv(a, v)
    if fmt == "pdf":
        return to_pdf(a, v)
    raise ValueError(f"Unknown format {fmt}")
