"""Local (CPU/GPU) embedding provider using sentence-transformers."""

from __future__ import annotations

from sentence_transformers import SentenceTransformer


class LocalEmbeddingProvider:
    def __init__(self, model: str) -> None:
        self._model = SentenceTransformer(model)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, convert_to_numpy=True)
        return [v.tolist() for v in vectors]
