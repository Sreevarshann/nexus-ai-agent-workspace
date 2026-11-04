"""Optional OpenAI-compatible chat provider (vLLM, LM Studio, llama.cpp server, hosted APIs).

Never the default. Embeddings stay on the local Ollama model so documents are not sent out for indexing.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx

from nexus.llm.base import ChatMessage, GenOptions, LLMError, LLMResult, StreamChunk, Usage, strip_thinking
from nexus.llm.ollama import OllamaProvider


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(
        self, base_url: str, api_key: str, model: str, timeout_s: float, defaults: GenOptions, embedder: OllamaProvider
    ):
        if not base_url or not model:
            raise LLMError("NEXUS_OPENAI_BASE_URL and NEXUS_OPENAI_MODEL are required for openai_compat")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.timeout = httpx.Timeout(timeout_s, connect=5.0)
        self.defaults = defaults
        self.embedder = embedder

    def _payload(self, messages: list[ChatMessage], opts: GenOptions | None, stream: bool) -> dict[str, Any]:
        o = opts or GenOptions()
        p: dict[str, Any] = {
            "model": self.model,
            "messages": [m.as_dict() for m in messages],
            "stream": stream,
            "temperature": o.temperature if o.temperature is not None else self.defaults.temperature,
        }
        if o.max_tokens:
            p["max_tokens"] = o.max_tokens
        if stream:
            p["stream_options"] = {"include_usage": True}
        return p

    async def stream_chat(
        self, messages: list[ChatMessage], opts: GenOptions | None = None
    ) -> AsyncIterator[StreamChunk]:
        usage = Usage()
        try:
            async with (
                httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client,
                client.stream(
                    "POST", f"{self.base_url}/chat/completions", json=self._payload(messages, opts, True)
                ) as resp,
            ):
                if resp.status_code != 200:
                    raise LLMError(f"Provider returned HTTP {resp.status_code}")
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    obj = json.loads(data)
                    if obj.get("usage"):
                        usage = Usage(obj["usage"].get("prompt_tokens"), obj["usage"].get("completion_tokens"))
                    for choice in obj.get("choices", []):
                        delta = choice.get("delta", {}).get("content")
                        if delta:
                            yield StreamChunk(delta=delta)
        except httpx.HTTPError as e:
            raise LLMError(f"OpenAI-compatible provider error: {type(e).__name__}") from e
        yield StreamChunk(done=True, usage=usage)

    async def chat(self, messages: list[ChatMessage], opts: GenOptions | None = None) -> LLMResult:
        started = time.perf_counter()
        data = await self._post(self._payload(messages, opts, False))
        u = data.get("usage") or {}
        return LLMResult(
            text=strip_thinking(data["choices"][0]["message"]["content"] or ""),
            usage=Usage(u.get("prompt_tokens"), u.get("completion_tokens")),
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=self.model,
        )

    async def structured_raw(
        self, messages: list[ChatMessage], schema: dict[str, Any], opts: GenOptions | None = None
    ) -> str:
        payload = self._payload(messages, opts or GenOptions(temperature=0.1), False)
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema.get("title", "output"), "schema": schema},
        }
        data = await self._post(payload)
        return str(data["choices"][0]["message"]["content"] or "")

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=self.headers) as client:
                resp = await client.post(f"{self.base_url}/chat/completions", json=payload)
        except httpx.HTTPError as e:
            raise LLMError(f"OpenAI-compatible provider error: {type(e).__name__}") from e
        if resp.status_code != 200:
            raise LLMError(f"Provider returned HTTP {resp.status_code}: {resp.text[:200]}")
        out: dict[str, Any] = resp.json()
        return out

    async def embed(self, texts: list[str], kind: Literal["document", "query"] = "document") -> list[list[float]]:
        return await self.embedder.embed(texts, kind)

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0), headers=self.headers) as client:
                resp = await client.get(f"{self.base_url}/models")
            ok = resp.status_code == 200
        except httpx.HTTPError as e:
            return {"ok": False, "provider": self.name, "model": self.model, "error": type(e).__name__}
        return {
            "ok": ok,
            "provider": self.name,
            "model": self.model,
            "error": None if ok else f"HTTP {resp.status_code}",
            "external": True,
        }
