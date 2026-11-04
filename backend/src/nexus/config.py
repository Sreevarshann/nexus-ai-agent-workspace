"""Application settings, loaded from environment variables prefixed with ``NEXUS_``."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEXUS_",
        env_file=(str(_REPO_ROOT / ".env"), ".env"),
        extra="ignore",
    )

    env: Literal["development", "production", "test"] = "development"
    secret_key: str = "dev-insecure-secret"  # noqa: S105 - rejected in production
    database_url: str = "postgresql+asyncpg://nexus:nexus@localhost:5433/nexus"
    redis_url: str = "redis://localhost:6380/0"
    data_dir: Path = Path("./data")
    cors_origins: list[str] = ["http://localhost:3000"]

    # LLM
    llm_provider: Literal["ollama", "openai_compat", "fixture"] = "ollama"
    ollama_url: str = "http://localhost:11434"
    chat_model: str = "qwen3:4b-instruct"
    embed_model: str = "nomic-embed-text"
    embed_dim: int = 768
    openai_base_url: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    llm_timeout_s: float = 180.0
    temperature: float = 0.3
    num_ctx: int = 16384

    # Web research
    search_provider: Literal["searxng", "none", "fixture"] = "searxng"
    searxng_url: str = "http://localhost:8888"
    fetch_timeout_s: float = 15.0
    fetch_max_bytes: int = 5 * 1024 * 1024
    user_agent: str = "NEXUS-AI-Research/0.1 (+local research assistant)"

    # Limits
    max_upload_bytes: int = 25 * 1024 * 1024
    max_dataset_rows: int = 2_000_000
    query_timeout_s: float = 10.0
    mission_max_steps: int = 24
    mission_max_tool_calls: int = 40

    # Test-only escape hatch so tests can exercise the SSRF guard against a local stub server.
    allow_private_fetch: bool = Field(default=False)

    @model_validator(mode="after")
    def _guard_fixture_provider(self) -> Settings:
        # The deterministic fixture provider exists for automated tests only.
        if self.llm_provider == "fixture" and self.env != "test":
            raise ValueError("NEXUS_LLM_PROVIDER=fixture is only allowed when NEXUS_ENV=test")
        if self.env == "production" and self.secret_key == "dev-insecure-secret":  # noqa: S105
            raise ValueError("Set NEXUS_SECRET_KEY in production")
        return self

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def dataset_dir(self) -> Path:
        return self.data_dir / "datasets"

    @property
    def artifact_dir(self) -> Path:
        return self.data_dir / "artifacts"

    @property
    def psycopg_url(self) -> str:
        """Plain libpq URL used by the LangGraph Postgres checkpointer."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for d in (s.upload_dir, s.dataset_dir, s.artifact_dir):
        d.mkdir(parents=True, exist_ok=True)
    return s
