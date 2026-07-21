"""Unit tests for LocalEmbeddingProvider."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from ai.embedding import EmbeddingConfig, EmbeddingProvider
from ai.providers.local_embeddings import LocalEmbeddingProvider


def _make_provider(
    model: str = "intfloat/multilingual-e5-large",
) -> LocalEmbeddingProvider:
    config = EmbeddingConfig(EMBEDDING_MODEL=model, EMBEDDING_PROVIDER="local")
    return LocalEmbeddingProvider(config)


@pytest.mark.asyncio
async def test_embed_single_text() -> None:
    provider = _make_provider()
    mock_model = MagicMock()
    mock_model.encode.return_value = np.zeros((1, 768), dtype=np.float32)

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
        result = await provider.embed(["hello"])

    assert len(result) == 1
    assert len(result[0]) == 768
    assert isinstance(result[0][0], float)


@pytest.mark.asyncio
async def test_embed_batch() -> None:
    provider = _make_provider()
    mock_model = MagicMock()
    mock_model.encode.return_value = np.zeros((3, 768), dtype=np.float32)

    with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
        result = await provider.embed(["a", "b", "c"])

    assert len(result) == 3
    assert all(len(v) == 768 for v in result)


@pytest.mark.asyncio
async def test_lazy_loading() -> None:
    provider = _make_provider()
    assert provider._model is None

    mock_model = MagicMock()
    mock_model.encode.return_value = np.zeros((1, 768), dtype=np.float32)

    with patch(
        "sentence_transformers.SentenceTransformer", return_value=mock_model
    ) as mock_cls:
        await provider.embed(["text"])
        assert mock_cls.call_count == 1

        await provider.embed(["text again"])
        assert mock_cls.call_count == 1  # not reloaded


@pytest.mark.asyncio
async def test_empty_input() -> None:
    provider = _make_provider()

    with patch("sentence_transformers.SentenceTransformer") as mock_cls:
        result = await provider.embed([])

    assert result == []
    mock_cls.assert_not_called()


def test_protocol_compliance() -> None:
    config = EmbeddingConfig(
        EMBEDDING_MODEL="intfloat/multilingual-e5-large", EMBEDDING_PROVIDER="local"
    )
    provider = LocalEmbeddingProvider(config)
    assert isinstance(provider, EmbeddingProvider)
