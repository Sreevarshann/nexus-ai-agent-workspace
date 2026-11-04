"""Retrieve a URL into a persisted Source with honest status reporting."""

from __future__ import annotations

import uuid
from urllib.parse import urlsplit

from nexus.db import session_scope
from nexus.domain.untrusted import detect_injection
from nexus.models import Source
from nexus.research.extract import best_excerpt, extract_content
from nexus.research.safe_fetch import FetchBlocked, FetchFailed, safe_fetch

MAX_STORED_CHARS = 60_000


async def retrieve_source(
    user_id: uuid.UUID,
    url: str,
    query: str = "",
    task_id: uuid.UUID | None = None,
    fallback_title: str = "",
) -> Source:
    domain = (urlsplit(url).hostname or "").lower()
    src = Source(
        user_id=user_id,
        task_id=task_id,
        url=url,
        domain=domain,
        title=fallback_title,
        status="failed",
        search_query=query or None,
    )
    try:
        res = await safe_fetch(url)
        src.final_url, src.http_status, src.content_type = res.final_url, res.status, res.content_type[:127]
        if res.status >= 400:
            src.error = f"HTTP {res.status}"
        else:
            page = extract_content(res.body, res.content_type, res.final_url)
            if len(page.text) < 200:
                src.error = "Too little readable content (page may require JavaScript or sign-in)"
                src.title = page.title or fallback_title
            else:
                src.status = "retrieved"
                src.title = page.title or fallback_title or domain
                src.content = page.text[:MAX_STORED_CHARS]
                src.excerpt = best_excerpt(page.text, query or page.title)
                src.published_at = page.published
                flags = detect_injection(page.text)
                if flags:
                    src.error = "Suspicious embedded instructions detected and ignored: " + "; ".join(flags[:3])
    except FetchBlocked as e:
        src.status, src.error = "blocked", str(e)
    except FetchFailed as e:
        src.error = str(e)
    except Exception as e:  # parser failures on hostile content must not crash a mission
        src.error = f"Extraction failed: {type(e).__name__}"
    async with session_scope() as db:
        db.add(src)
    return src
