"""Embedding provider abstraction for the ai package.

Model, dimension and retrieval prefixes are configured in `llm_config.yaml`
under `embedding` — see `ai.llm_config` for the resolution rules.

The model and its dimension must always change together, and the
`chunks.embedding` column must be recreated at the new width by a migration.
`verify_embedding_dimension` enforces the first half of that at startup.

`model` is passed verbatim to the provider, so for the local provider it must be
a resolvable HuggingFace model id — not a friendly alias.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from llm_core import BERGET_BASE_URL

from ai.errors import EmbeddingDimensionMismatchError
from ai.llm_config import (
    EmbeddingBackend,
    EmbeddingConfig,
    resolve_embedding_config,
)
from shared.config import EMBEDDING_DIMENSION

# Short throwaway input used only to observe the model's output width.
_DIMENSION_PROBE_TEXT = "dimensionskontroll"

__all__ = [
    "EmbeddingConfig",
    "EmbeddingProvider",
    "create_embedding_provider",
    "verify_embedding_dimension",
]


@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...


def create_embedding_provider(
    config: EmbeddingConfig | None = None,
) -> EmbeddingProvider:
    if config is None:
        config = resolve_embedding_config()

    match config.provider:
        case EmbeddingBackend.LOCAL:
            from ai.providers.local_embeddings import LocalEmbeddingProvider

            return LocalEmbeddingProvider(config)
        case EmbeddingBackend.OPENAI_COMPATIBLE | EmbeddingBackend.BERGET:
            from ai.providers.berget_embeddings import BergetEmbeddingProvider

            return BergetEmbeddingProvider(config, default_base_url=BERGET_BASE_URL)
        case _:
            raise ValueError(f"Unknown embedding provider: {config.provider!r}")


async def verify_embedding_dimension(
    provider: EmbeddingProvider, config: EmbeddingConfig | None = None
) -> int:
    """Check that every declaration of the embedding width agrees.

    Call once at process startup. Embeds a single throwaway string, so for the
    local provider this also forces the model to load eagerly rather than on
    first use.

    The width is declared in three uncoordinated places — `llm_config.yaml`,
    `shared.config.EMBEDDING_DIMENSION` (which the workers validate against), and
    the `chunks.embedding` column baked into the migration. Nothing links them,
    so this compares all three reachable values against what the model actually
    produces. Without it a mismatch only surfaces after the pipeline has done its
    expensive work, or as a failed user query on the API.

    Returns the observed dimension.
    """
    if config is None:
        config = resolve_embedding_config()

    if config.dimension != EMBEDDING_DIMENSION:
        raise EmbeddingDimensionMismatchError(
            f"Configured embedding dimension disagrees with itself: "
            f"llm_config.yaml says {config.dimension}, EMBEDDING_DIMENSION is "
            f"{EMBEDDING_DIMENSION}. These must match, and the chunks.embedding "
            f"column must be recreated at that width."
        )

    vectors = await provider.embed([_DIMENSION_PROBE_TEXT])
    if not vectors:
        raise EmbeddingDimensionMismatchError(
            "Embedding provider returned no vectors for the dimension probe"
        )

    actual_dimension = len(vectors[0])
    if actual_dimension != config.dimension:
        raise EmbeddingDimensionMismatchError(
            f"Embedding model {config.model!r} produces {actual_dimension}-dim "
            f"vectors but the configured dimension is {config.dimension}. The "
            f"model and the dimension must change together, and the "
            f"chunks.embedding column must be recreated at the new width."
        )
    return actual_dimension
