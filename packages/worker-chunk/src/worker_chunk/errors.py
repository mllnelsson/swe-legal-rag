"""Domain error types for the chunk worker."""

__all__ = ["ChunkError", "ChunkBudgetError"]


class ChunkError(Exception):
    """Base class for chunk-worker failures."""


class ChunkBudgetError(ChunkError):
    """The embedding window leaves no room for chunk text once overhead is taken.

    Raised while deriving the budget at startup, so a window that cannot fit the
    summary reserve and the prefixes is a refusal to start rather than a stream
    of empty chunks.
    """
