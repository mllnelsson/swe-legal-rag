"""Unit tests for the startup embedding-dimension check."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from ai.embedding import verify_embedding_dimension
from ai.errors import EmbeddingDimensionMismatchError
from shared.config import EMBEDDING_DIMENSION


def _provider_returning(vectors: list[list[float]]) -> MagicMock:
    provider = MagicMock()
    provider.embed = AsyncMock(return_value=vectors)
    return provider


@pytest.mark.asyncio
async def test_returns_dimension_when_model_matches_config() -> None:
    provider = _provider_returning([[0.0] * EMBEDDING_DIMENSION])

    assert await verify_embedding_dimension(provider) == EMBEDDING_DIMENSION


@pytest.mark.asyncio
async def test_raises_when_model_is_narrower_than_config() -> None:
    provider = _provider_returning([[0.0] * (EMBEDDING_DIMENSION - 256)])

    with pytest.raises(EmbeddingDimensionMismatchError, match="must change together"):
        await verify_embedding_dimension(provider)


@pytest.mark.asyncio
async def test_raises_when_model_is_wider_than_config() -> None:
    provider = _provider_returning([[0.0] * (EMBEDDING_DIMENSION + 256)])

    with pytest.raises(EmbeddingDimensionMismatchError):
        await verify_embedding_dimension(provider)


@pytest.mark.asyncio
async def test_raises_when_provider_returns_nothing() -> None:
    provider = _provider_returning([])

    with pytest.raises(EmbeddingDimensionMismatchError, match="no vectors"):
        await verify_embedding_dimension(provider)


@pytest.mark.asyncio
async def test_probes_with_exactly_one_string() -> None:
    provider = _provider_returning([[0.0] * EMBEDDING_DIMENSION])

    await verify_embedding_dimension(provider)

    (texts,) = provider.embed.call_args.args
    assert len(texts) == 1
