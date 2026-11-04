"""Provider-neutral LLM interface."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ValidationError


class LLMError(RuntimeError):
    """Raised when a provider is unreachable, times out or returns an unusable response."""


@dataclass
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str

    def as_dict(self) -> dict[str, str]:
        return {"role": self.role, "content": self.content}


@dataclass
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


@dataclass
class StreamChunk:
    delta: str = ""
    done: bool = False
    usage: Usage = field(default_factory=Usage)


@dataclass
class LLMResult:
    text: str
    usage: Usage
    latency_ms: int
    model: str


@dataclass
class GenOptions:
    temperature: float | None = None
    max_tokens: int | None = None
    num_ctx: int | None = None


class LLMProvider(Protocol):
    name: str
    model: str

    def stream_chat(
        self, messages: list[ChatMessage], opts: GenOptions | None = None
    ) -> AsyncIterator[StreamChunk]: ...

    async def chat(self, messages: list[ChatMessage], opts: GenOptions | None = None) -> LLMResult: ...

    async def structured_raw(
        self, messages: list[ChatMessage], schema: dict[str, Any], opts: GenOptions | None = None
    ) -> str: ...

    async def embed(self, texts: list[str], kind: Literal["document", "query"] = "document") -> list[list[float]]: ...

    async def health(self) -> dict[str, Any]: ...


_THINK = re.compile(r"<think>.*?</think>\s*", re.S)


def strip_thinking(text: str) -> str:
    return _THINK.sub("", text)


def extract_json(text: str) -> Any:
    """Parse JSON from a model reply, tolerating code fences or leading prose."""
    text = strip_thinking(text).strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min((i for i in (text.find("{"), text.find("[")) if i >= 0), default=-1)
        if start < 0:
            raise
        return json.loads(text[start : max(text.rfind("}"), text.rfind("]")) + 1])


async def structured[T: BaseModel](
    provider: LLMProvider,
    messages: list[ChatMessage],
    model_cls: type[T],
    opts: GenOptions | None = None,
    retries: int = 1,
) -> T:
    """Request schema-constrained JSON and validate it; retry once with the validation error."""
    schema = model_cls.model_json_schema()
    attempt_msgs = list(messages)
    last_err: Exception | None = None
    for _ in range(retries + 1):
        raw = await provider.structured_raw(attempt_msgs, schema, opts)
        try:
            return model_cls.model_validate(extract_json(raw))
        except (ValidationError, json.JSONDecodeError, ValueError) as e:
            last_err = e
            attempt_msgs = [
                *messages,
                ChatMessage("assistant", raw[:4000]),
                ChatMessage(
                    "user", f"That output was invalid: {str(e)[:800]}. Reply with JSON matching the schema only."
                ),
            ]
    raise LLMError(f"Model did not return valid {model_cls.__name__}: {last_err}")
