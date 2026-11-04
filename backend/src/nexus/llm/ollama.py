"""Ollama provider (local inference)."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any, Literal

import httpx

from nexus.llm.base import ChatMessage, GenOptions, LLMError, LLMResult, StreamChunk, Usage, strip_thinking


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str, model: str, embed_model: str, timeout_s: float, defaults: GenOptions):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embed_model = embed_model
        self.timeout = httpx.Timeout(timeout_s, connect=5.0)
        self.defaults = defaults

    def _options(self, opts: GenOptions | None) -> dict[str, Any]:
        o = opts or GenOptions()
        out: dict[str, Any] = {
            "temperature": o.temperature if o.temperature is not None else self.defaults.temperature,
            "num_ctx": o.num_ctx or self.defaults.num_ctx,
        }
        if o.max_tokens:
            out["num_predict"] = o.max_tokens
        return out

    def _payload(self, messages: list[ChatMessage], opts: GenOptions | None, stream: bool) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [m.as_dict() for m in messages],
            "stream": stream,
            "options": self._options(opts),
            "keep_alive": "30m",
        }

    async def stream_chat(
        self, messages: list[ChatMessage], opts: GenOptions | None = None
    ) -> AsyncIterator[StreamChunk]:
        try:
            async with (
                httpx.AsyncClient(timeout=self.timeout) as client,
                client.stream("POST", f"{self.base_url}/api/chat", json=self._payload(messages, opts, True)) as resp,
            ):
                if resp.status_code != 200:
                    body = (await resp.aread()).decode(errors="replace")[:300]
                    raise LLMError(f"Ollama returned HTTP {resp.status_code}: {body}")
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if "error" in data:
                        raise LLMError(f"Ollama error: {data['error']}")
                    delta = data.get("message", {}).get("content", "")
                    if data.get("done"):
                        yield StreamChunk(
                            delta=delta, done=True, usage=Usage(data.get("prompt_eval_count"), data.get("eval_count"))
                        )
                        return
                    if delta:
                        yield StreamChunk(delta=delta)
        except httpx.ConnectError as e:
            raise LLMError(f"Cannot reach Ollama at {self.base_url}. Is `ollama serve` running?") from e
        except httpx.TimeoutException as e:
            raise LLMError("Ollama request timed out") from e

    async def chat(self, messages: list[ChatMessage], opts: GenOptions | None = None) -> LLMResult:
        started = time.perf_counter()
        data = await self._post("/api/chat", self._payload(messages, opts, False))
        return LLMResult(
            text=strip_thinking(data.get("message", {}).get("content", "")),
            usage=Usage(data.get("prompt_eval_count"), data.get("eval_count")),
            latency_ms=int((time.perf_counter() - started) * 1000),
            model=self.model,
        )

    async def structured_raw(
        self, messages: list[ChatMessage], schema: dict[str, Any], opts: GenOptions | None = None
    ) -> str:
        payload = self._payload(messages, opts or GenOptions(temperature=0.1), False)
        payload["format"] = schema  # Ollama constrains decoding to this JSON schema
        data = await self._post("/api/chat", payload)
        return str(data.get("message", {}).get("content", ""))

    async def embed(self, texts: list[str], kind: Literal["document", "query"] = "document") -> list[list[float]]:
        # nomic-embed-text is trained with task prefixes; they materially improve retrieval.
        prefix = (
            ("search_document: " if kind == "document" else "search_query: ") if "nomic" in self.embed_model else ""
        )
        out: list[list[float]] = []
        for i in range(0, len(texts), 32):
            data = await self._post(
                "/api/embed", {"model": self.embed_model, "input": [prefix + t for t in texts[i : i + 32]]}
            )
            out.extend(data["embeddings"])
        return out

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}{path}", json=payload)
        except httpx.ConnectError as e:
            raise LLMError(f"Cannot reach Ollama at {self.base_url}. Is `ollama serve` running?") from e
        except httpx.TimeoutException as e:
            raise LLMError("Ollama request timed out") from e
        if resp.status_code != 200:
            raise LLMError(f"Ollama returned HTTP {resp.status_code}: {resp.text[:300]}")
        data: dict[str, Any] = resp.json()
        return data

    async def health(self) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
                tags = (await client.get(f"{self.base_url}/api/tags")).json()
                ps = (await client.get(f"{self.base_url}/api/ps")).json()
        except (httpx.HTTPError, ValueError) as e:
            return {
                "ok": False,
                "provider": self.name,
                "model": self.model,
                "error": f"Ollama unreachable at {self.base_url}: {type(e).__name__}",
            }
        installed = [m["name"] for m in tags.get("models", [])]

        def has(name: str) -> bool:
            return any(n == name or n == f"{name}:latest" for n in installed)

        missing = [m for m in (self.model, self.embed_model) if not has(m)]
        return {
            "ok": not missing,
            "provider": self.name,
            "model": self.model,
            "embed_model": self.embed_model,
            "installed_models": installed,
            "loaded_models": [m["name"] for m in ps.get("models", [])],
            "error": f"Model(s) not installed: {', '.join(missing)}. Run `make models`." if missing else None,
        }
