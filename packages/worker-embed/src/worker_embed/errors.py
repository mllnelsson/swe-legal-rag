"""Domain error types for the embedding worker."""

__all__ = [
    "EmbeddingError",
    "NoChunksError",
    "EmbeddingCountMismatchError",
    "EmbeddingDimensionError",
]


class EmbeddingError(Exception):
    """Base class for embedding-worker failures."""


class NoChunksError(EmbeddingError):
    """The document has no chunks to embed — the chunk worker must run first."""


class EmbeddingCountMismatchError(EmbeddingError):
    """The provider returned a different number of vectors than chunks given."""


class EmbeddingDimensionError(EmbeddingError):
    """A returned embedding vector has the wrong dimensionality."""
