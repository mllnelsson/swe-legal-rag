"""Embedding provider abstraction for the ai package.

Default model is `intfloat/multilingual-e5-base` (768 dims) — this must stay
in sync with `shared.config.EMBEDDING_DIMENSION` (default 768) and the
`chunks.embedding` column size baked into the existing migrations.
To switch models, update EMBEDDING_MODEL **and** EMBEDDING_DIMENSION together
and provide a new database migration.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingConfig(BaseSettings):
    model_config = SettingsConfigDict(populate_by_name=True)

    provider: str = Field(default="local", alias="EMBEDDING_PROVIDER")
    model: str = Field(default="intfloat/multilingual-e5-base", alias="EMBEDDING_MODEL")


def create_embedding_provider(config: EmbeddingConfig | None = None) -> EmbeddingProvider:
    if config is None:
        config = EmbeddingConfig()

    match config.provider:
        case "local":
            from ai._local_embedding import LocalEmbeddingProvider

            return LocalEmbeddingProvider(model=config.model)
        case _:
            raise ValueError(f"Unknown embedding provider: {config.provider!r}")
