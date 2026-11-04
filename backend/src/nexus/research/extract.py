"""Readable-content extraction from fetched HTML and PDF responses."""

from __future__ import annotations

import re
from dataclasses import dataclass

import trafilatura


@dataclass
class PageContent:
    title: str
    text: str
    published: str | None
    kind: str  # html | pdf | text


def _decode(body: bytes, content_type: str) -> str:
    m = re.search(r"charset=([\w-]+)", content_type, re.I)
    try:
        return body.decode(m.group(1) if m else "utf-8", errors="replace")
    except LookupError:
        return body.decode("utf-8", errors="replace")


def extract_content(body: bytes, content_type: str, url: str) -> PageContent:
    ct = content_type.lower()
    if "pdf" in ct or body.startswith(b"%PDF-"):
        import pymupdf

        with pymupdf.open(stream=body, filetype="pdf") as doc:
            text = "\n\n".join(p.get_text("text") for _, p in zip(range(60), doc, strict=False))
            title = (doc.metadata or {}).get("title") or url.rsplit("/", 1)[-1]
        return PageContent(title=title, text=text.strip(), published=None, kind="pdf")
    html = _decode(body, content_type)
    if "html" not in ct and not re.search(r"<html|<body|<p", html[:2000], re.I):
        return PageContent(title=url, text=html[:200_000], published=None, kind="text")
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=True, favor_precision=True) or ""
    meta = trafilatura.extract_metadata(html, default_url=url)
    title = (meta.title if meta and meta.title else "") or _title_tag(html) or url
    published = meta.date if meta and meta.date else None
    return PageContent(title=title.strip()[:300], text=text.strip(), published=published, kind="html")


def _title_tag(html: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def best_excerpt(text: str, query: str, length: int = 420) -> str:
    """Pick the paragraph with the most query-term overlap."""
    terms = {w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 3}
    paras = [p.strip() for p in re.split(r"\n+", text) if len(p.strip()) > 60] or [text]
    best = max(paras, key=lambda p: sum(1 for t in terms if t in p.lower()))
    return best[:length] + ("…" if len(best) > length else "")
