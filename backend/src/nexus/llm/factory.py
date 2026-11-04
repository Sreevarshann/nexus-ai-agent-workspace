"""Provider selection."""

from __future__ import annotations

from functools import lru_cache

from nexus.config import get_settings
from nexus.llm.base import GenOptions, LLMProvider
from nexus.llm.fixture import FixtureProvider
from nexus.llm.ollama import OllamaProvider
from nexus.llm.openai_compat import OpenAICompatProvider

_override: LLMProvider | None = None


@lru_cache
def _build() -> LLMProvider:
    s = get_settings()
    defaults = GenOptions(temperature=s.temperature, num_ctx=s.num_ctx)
    if s.llm_provider == "fixture":
        return FixtureProvider()
    ollama = OllamaProvider(s.ollama_url, s.chat_model, s.embed_model, s.llm_timeout_s, defaults)
    if s.llm_provider == "openai_compat":
        return OpenAICompatProvider(
            s.openai_base_url, s.openai_api_key, s.openai_model, s.llm_timeout_s, defaults, ollama
        )
    return ollama


def get_llm() -> LLMProvider:
    return _override or _build()


def set_llm(provider: LLMProvider | None) -> None:
    global _override
    _override = provider
