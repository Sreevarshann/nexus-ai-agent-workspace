"""Deterministic provider for automated tests ONLY.

Selectable solely when NEXUS_ENV=test (enforced in Settings). It never pretends to be a real model: its
health report names it as a fixture, and every response is a transparent function of its input.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import AsyncIterator, Callable
from typing import Any, Literal

from nexus.llm.base import ChatMessage, GenOptions, LLMResult, StreamChunk, Usage

StructuredHandler = Callable[[list[ChatMessage], dict[str, Any]], dict[str, Any]]
_HANDLERS: dict[str, StructuredHandler] = {}

_EVIDENCE = re.compile(r"\[(S\d+)\][^\n]*\n(.+?)(?=\n\[S\d+\]|\n</evidence>|\Z)", re.S)


def register_fixture(schema_title: str) -> Callable[[StructuredHandler], StructuredHandler]:
    def deco(fn: StructuredHandler) -> StructuredHandler:
        _HANDLERS[schema_title] = fn
        return fn

    return deco


def hash_embedding(text: str, dim: int = 768) -> list[float]:
    """Bag-of-words feature hashing: texts sharing words have high cosine similarity."""
    vec = [0.0] * dim
    for word in re.findall(r"[a-z0-9]+", text.lower()):
        if len(word) < 3:
            continue
        h = int(hashlib.md5(word.encode(), usedforsecurity=False).hexdigest(), 16)
        vec[h % dim] += 1.0 if (h >> 8) & 1 else -1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _fixture_answer(messages: list[ChatMessage]) -> str:
    joined = "\n".join(m.content for m in messages)
    question = next((m.content for m in reversed(messages) if m.role == "user"), "")
    found = _EVIDENCE.findall(joined)
    if found:
        label, body = found[0]
        sentence = re.split(r"(?<=[.!?])\s", body.strip())[0][:240]
        return f"[fixture] According to the evidence, {sentence} [{label}]."
    return f"[fixture] Echo: {question[:200]}"


def _instance(schema: dict[str, Any], root: dict[str, Any], hint: str) -> Any:
    if "$ref" in schema:
        return _instance(root["$defs"][schema["$ref"].split("/")[-1]], root, hint)
    if "anyOf" in schema:
        return _instance(next(s for s in schema["anyOf"] if s.get("type") != "null"), root, hint)
    if "default" in schema:
        return schema["default"]
    if "enum" in schema:
        return schema["enum"][0]
    t = schema.get("type")
    if t == "object":
        return {k: _instance(v, root, hint) for k, v in schema.get("properties", {}).items()}
    if t == "array":
        return [_instance(schema.get("items", {}), root, hint) for _ in range(max(1, schema.get("minItems", 1)))]
    if t == "string":
        return hint[:80] or "fixture"
    if t == "integer":
        return schema.get("minimum", 1)
    if t == "number":
        return 1.0
    if t == "boolean":
        return False
    return None


class FixtureProvider:
    name = "fixture"
    model = "fixture-deterministic"

    async def stream_chat(
        self, messages: list[ChatMessage], opts: GenOptions | None = None
    ) -> AsyncIterator[StreamChunk]:
        text = _fixture_answer(messages)
        for word in re.findall(r"\S+\s*", text):
            yield StreamChunk(delta=word)
        yield StreamChunk(done=True, usage=Usage(len(" ".join(m.content for m in messages)) // 4, len(text) // 4))

    async def chat(self, messages: list[ChatMessage], opts: GenOptions | None = None) -> LLMResult:
        text = _fixture_answer(messages)
        return LLMResult(text=text, usage=Usage(0, len(text) // 4), latency_ms=0, model=self.model)

    async def structured_raw(
        self, messages: list[ChatMessage], schema: dict[str, Any], opts: GenOptions | None = None
    ) -> str:
        import json

        handler = _HANDLERS.get(schema.get("title", ""))
        if handler:
            return json.dumps(handler(messages, schema))
        hint = next((m.content for m in reversed(messages) if m.role == "user"), "")
        return json.dumps(_instance(schema, schema, hint.splitlines()[0] if hint else ""))

    async def embed(self, texts: list[str], kind: Literal["document", "query"] = "document") -> list[list[float]]:
        return [hash_embedding(t) for t in texts]

    async def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "provider": self.name,
            "model": self.model,
            "fixture": True,
            "error": None,
            "installed_models": [],
            "loaded_models": [],
        }
