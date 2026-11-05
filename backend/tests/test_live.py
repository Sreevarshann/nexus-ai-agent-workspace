"""Live smoke tests: real Ollama model and real SearXNG. Run with `make test-live` (pytest -m live).

These bypass the fixture provider and the fake search engine used by the rest of the suite.
"""

import pytest

from nexus.config import get_settings
from nexus.llm.base import ChatMessage, GenOptions
from nexus.llm.ollama import OllamaProvider
from nexus.research.search import SearxngProvider

pytestmark = pytest.mark.live
SEARXNG = "http://localhost:8888"


def ollama() -> OllamaProvider:
    s = get_settings()
    # Same context size as the running API: a different num_ctx forces Ollama to reload the model.
    return OllamaProvider(
        s.ollama_url, s.chat_model, s.embed_model, 300, GenOptions(temperature=0.1, num_ctx=s.num_ctx)
    )


async def test_real_model_streams_tokens() -> None:
    chunks = [c async for c in ollama().stream_chat([ChatMessage("user", "Reply with exactly: NEXUS online")])]
    text = "".join(c.delta for c in chunks)
    assert len(chunks) > 2 and chunks[-1].done and chunks[-1].usage.completion_tokens
    assert "nexus" in text.lower()


async def test_real_embeddings_have_expected_dimension_and_semantics() -> None:
    import math

    a, b, c = await ollama().embed(["battery storage capacity", "energy storage in batteries", "medieval poetry"])
    assert len(a) == 768

    def cos(x: list[float], y: list[float]) -> float:
        return sum(i * j for i, j in zip(x, y, strict=True)) / (math.hypot(*x) * math.hypot(*y))

    assert cos(a, b) > cos(a, c)


async def test_real_structured_output() -> None:
    from pydantic import BaseModel

    from nexus.llm.base import structured

    class Capital(BaseModel):
        country: str
        capital: str

    r = await structured(ollama(), [ChatMessage("user", "What is the capital of France?")], Capital)
    assert r.capital.lower() == "paris"


async def test_real_web_search_and_fetch() -> None:
    from nexus.research.extract import extract_content
    from nexus.research.safe_fetch import safe_fetch

    get_settings().allow_private_fetch = False
    results = await SearxngProvider(SEARXNG).search("Model Context Protocol specification", 5)
    assert results and all(r.url.startswith("http") for r in results)
    res = await safe_fetch("https://en.wikipedia.org/wiki/Model_Context_Protocol")
    page = extract_content(res.body, res.content_type, res.final_url)
    assert res.status == 200 and "protocol" in page.text.lower()
