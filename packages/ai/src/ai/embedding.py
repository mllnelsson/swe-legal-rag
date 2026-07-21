"""Embedding provider abstraction for the ai package.

Default model is `intfloat/multilingual-e5-large` (1024 dims) — this must stay
in sync with `shared.config.EMBEDDING_DIMENSION` (default 1024) and the
`chunks.embedding` column size baked into the existing migrations.
To switch models, update EMBEDDING_MODEL **and** EMBEDDING_DIMENSION together
and provide a new database migration.

`EMBEDDING_MODEL` is passed verbatim to `SentenceTransformer(...)`, so it must
be a resolvable HuggingFace model id — not a friendly alias.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from ai.errors import EmbeddingDimensionMismatchError
from shared.config import EMBEDDING_DIMENSION

# Selected for Swedish retrieval quality (Scandinavian Embedding Benchmark);
# see ARCHITECTURE.md §7. Produces 1024-dim vectors.
DEFAULT_EMBEDDING_MODEL = "intfloat/multilingual-e5-large"

# Short throwaway input used only to observe the model's output width.
_DIMENSION_PROBE_TEXT = "dimensionskontroll"


@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class EmbeddingConfig(BaseSettings):
    model_config = SettingsConfigDict(populate_by_name=True)

    provider: str = Field(default="local", alias="EMBEDDING_PROVIDER")
    model: str = Field(default=DEFAULT_EMBEDDING_MODEL, alias="EMBEDDING_MODEL")


def create_embedding_provider(
    config: EmbeddingConfig | None = None,
) -> EmbeddingProvider:
    if config is None:
        config = EmbeddingConfig()

    match config.provider:
        case "local":
            from ai.providers.local_embeddings import LocalEmbeddingProvider

            return LocalEmbeddingProvider(config)
        case _:
            raise ValueError(f"Unknown embedding provider: {config.provider!r}")


async def verify_embedding_dimension(provider: EmbeddingProvider) -> int:
    """Check the provider's actual output width against `EMBEDDING_DIMENSION`.

    Call once at process startup. Embeds a single throwaway string, so for the local
    provider this also forces the model to load eagerly rather than on first use.

    Returns the observed dimension. Raises `EmbeddingDimensionMismatchError` if it
    disagrees with the configured value — which would otherwise corrupt or reject
    every write to `chunks.embedding`.
    """
    vectors = await provider.embed([_DIMENSION_PROBE_TEXT])
    if not vectors:
        raise EmbeddingDimensionMismatchError(
            "Embedding provider returned no vectors for the dimension probe"
        )

    actual_dimension = len(vectors[0])
    if actual_dimension != EMBEDDING_DIMENSION:
        raise EmbeddingDimensionMismatchError(
            f"Embedding model produces {actual_dimension}-dim vectors but "
            f"EMBEDDING_DIMENSION is {EMBEDDING_DIMENSION}. EMBEDDING_MODEL and "
            f"EMBEDDING_DIMENSION must change together, and the chunks.embedding "
            f"column must be recreated at the new width."
        )
    return actual_dimension
