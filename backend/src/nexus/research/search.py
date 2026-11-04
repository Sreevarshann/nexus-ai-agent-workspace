"""Web search provider abstraction. Results always come from a real configured engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from nexus.config import get_settings


class SearchUnavailable(RuntimeError):
    pass


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    engine: str
    published: str | None = None

    @property
    def domain(self) -> str:
        return urlsplit(self.url).hostname or ""


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, limit: int = 8) -> list[SearchResult]: ...

    async def health(self) -> dict[str, object]: ...


class SearxngProvider:
    name = "searxng"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    async def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=3.0)) as client:
                resp = await client.get(
                    f"{self.base_url}/search", params={"q": query, "format": "json", "language": "en", "safesearch": 1}
                )
        except httpx.HTTPError as e:
            raise SearchUnavailable(f"SearXNG unreachable at {self.base_url}: {type(e).__name__}") from e
        if resp.status_code != 200:
            raise SearchUnavailable(f"SearXNG returned HTTP {resp.status_code}")
        seen: set[str] = set()
        out: list[SearchResult] = []
        for r in resp.json().get("results", []):
            url = r.get("url", "")
            if not url.startswith(("http://", "https://")) or url in seen:
                continue
            seen.add(url)
            out.append(
                SearchResult(
                    title=r.get("title", "")[:300],
                    url=url,
                    snippet=(r.get("content") or "")[:600],
                    engine=",".join(r.get("engines", [])) or r.get("engine", ""),
                    published=r.get("publishedDate"),
                )
            )
            if len(out) >= limit:
                break
        return out

    async def health(self) -> dict[str, object]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
                ok = (await client.get(f"{self.base_url}/healthz")).status_code == 200
        except httpx.HTTPError as e:
            return {"ok": False, "provider": self.name, "error": f"unreachable: {type(e).__name__}"}
        return {"ok": ok, "provider": self.name, "error": None if ok else "unhealthy"}


class DisabledProvider:
    name = "none"

    async def search(self, query: str, limit: int = 8) -> list[SearchResult]:
        raise SearchUnavailable(
            "Web search is disabled (NEXUS_SEARCH_PROVIDER=none). Paste URLs to research them directly."
        )

    async def health(self) -> dict[str, object]:
        return {"ok": False, "provider": self.name, "error": "Search disabled; direct URL research only"}


_override: SearchProvider | None = None


def get_search() -> SearchProvider:
    if _override:
        return _override
    s = get_settings()
    if s.search_provider == "searxng":
        return SearxngProvider(s.searxng_url)
    return DisabledProvider()


def set_search(p: SearchProvider | None) -> None:
    global _override
    _override = p
