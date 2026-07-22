"""Berget-hosted embedding provider (OpenAI-compatible embeddings endpoint)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai.embedding import EmbeddingConfig


class BergetEmbeddingProvider:
    def __init__(self, config: EmbeddingConfig, *, default_base_url: str) -> None:
        from openai import AsyncOpenAI

        if not config.berget_api_key:
            raise ValueError("berget_api_key is required for BergetEmbeddingProvider")

        self._client = AsyncOpenAI(
            api_key=config.berget_api_key,
            base_url=config.base_url or default_base_url,
        )
        self._model = config.model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        response = await self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in response.data]
