"""Domain errors for the ai package."""

from __future__ import annotations


class AiError(Exception):
    """Base class for all ai package errors."""


class EmbeddingDimensionMismatchError(AiError):
    """The embedding model's output width disagrees with EMBEDDING_DIMENSION.

    Raised at startup rather than at embed time. The dimension is defined in three
    uncoordinated places (`shared.config`, the Alembic migration, and implicitly the
    configured model); without this check a mismatch only surfaces after the pipeline
    has already done its expensive work, or as a failed user query on the API.
    """
