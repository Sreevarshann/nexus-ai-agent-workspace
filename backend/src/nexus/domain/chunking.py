"""Page-aware text chunking."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    page: int | None
    ord: int


_WS = re.compile(r"[ \t]+")


def normalize(text: str) -> str:
    text = text.replace("\x00", "")
    text = _WS.sub(" ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _split_units(text: str) -> list[str]:
    """Paragraphs, falling back to sentences for long paragraphs."""
    units: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= 1200:
            units.append(para)
        else:
            units.extend(s.strip() for s in re.split(r"(?<=[.!?])\s+", para) if s.strip())
    return units


def chunk_pages(pages: list[tuple[int | None, str]], target: int = 900, overlap: int = 150) -> list[Chunk]:
    """Greedy packing of paragraphs into ~``target``-char chunks; chunks never span pages, so every
    chunk has one exact page reference."""
    chunks: list[Chunk] = []
    for page, raw in pages:
        text = normalize(raw)
        if not text:
            continue
        buf = ""
        for unit in _split_units(text):
            while len(unit) > target * 2:  # pathological unbroken text
                chunks.append(Chunk(unit[: target * 2], page, len(chunks)))
                unit = unit[target * 2 - overlap :]
            if buf and len(buf) + len(unit) + 2 > target:
                chunks.append(Chunk(buf, page, len(chunks)))
                tail = buf[-overlap:]
                buf = (tail[tail.find(" ") + 1 :] if " " in tail else tail) + "\n" + unit
            else:
                buf = f"{buf}\n\n{unit}" if buf else unit
        if buf.strip():
            chunks.append(Chunk(buf, page, len(chunks)))
    return chunks
