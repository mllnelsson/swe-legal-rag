"""Local embedding provider using sentence-transformers."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ai.embedding import EmbeddingConfig

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer


class LocalEmbeddingProvider:
    def __init__(self, config: EmbeddingConfig) -> None:
        self._model_name = config.model
        self._model: SentenceTransformer | None = None

    def _get_model(self) -> SentenceTransformer:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._get_model()
        loop = asyncio.get_running_loop()
        embeddings = await loop.run_in_executor(None, model.encode, texts)
        return embeddings.tolist()
