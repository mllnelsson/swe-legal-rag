"""Unit tests for BergetEmbeddingProvider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ai.embedding import EmbeddingConfig, EmbeddingProvider, create_embedding_provider
from ai.providers.berget_embeddings import BergetEmbeddingProvider


def _make_config(
    api_key: str | None = "test-key", base_url: str | None = None
) -> EmbeddingConfig:
    return EmbeddingConfig(
        EMBEDDING_MODEL="intfloat/multilingual-e5-large",
        EMBEDDING_PROVIDER="berget",
        BERGET_API_KEY=api_key,
        LLM_BASE_URL=base_url,
    )


def test_missing_api_key_raises() -> None:
    config = _make_config(api_key=None)
    with pytest.raises(ValueError, match="berget_api_key is required"):
        BergetEmbeddingProvider(config, default_base_url="https://api.berget.ai/v1")


def test_uses_default_base_url_when_unset() -> None:
    config = _make_config()
    with patch("openai.AsyncOpenAI") as mock_cls:
        BergetEmbeddingProvider(config, default_base_url="https://api.berget.ai/v1")
    mock_cls.assert_called_once_with(
        api_key="test-key", base_url="https://api.berget.ai/v1"
    )


def test_uses_configured_base_url_override() -> None:
    config = _make_config(base_url="https://example.test/v1")
    with patch("openai.AsyncOpenAI") as mock_cls:
        BergetEmbeddingProvider(config, default_base_url="https://api.berget.ai/v1")
    mock_cls.assert_called_once_with(
        api_key="test-key", base_url="https://example.test/v1"
    )


@pytest.mark.asyncio
async def test_embed_returns_vectors() -> None:
    config = _make_config()
    with patch("openai.AsyncOpenAI"):
        provider = BergetEmbeddingProvider(
            config, default_base_url="https://api.berget.ai/v1"
        )

    response = MagicMock()
    response.data = [MagicMock(embedding=[0.1, 0.2]), MagicMock(embedding=[0.3, 0.4])]
    provider._client.embeddings.create = AsyncMock(return_value=response)

    result = await provider.embed(["a", "b"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    provider._client.embeddings.create.assert_called_once_with(
        model="intfloat/multilingual-e5-large", input=["a", "b"]
    )


@pytest.mark.asyncio
async def test_empty_input_short_circuits() -> None:
    config = _make_config()
    with patch("openai.AsyncOpenAI"):
        provider = BergetEmbeddingProvider(
            config, default_base_url="https://api.berget.ai/v1"
        )
    provider._client.embeddings.create = AsyncMock()

    result = await provider.embed([])

    assert result == []
    provider._client.embeddings.create.assert_not_called()


def test_protocol_compliance() -> None:
    config = _make_config()
    with patch("openai.AsyncOpenAI"):
        provider = BergetEmbeddingProvider(
            config, default_base_url="https://api.berget.ai/v1"
        )
    assert isinstance(provider, EmbeddingProvider)


def test_create_embedding_provider_berget_dispatch() -> None:
    mock_instance = MagicMock()
    with patch(
        "ai.providers.berget_embeddings.BergetEmbeddingProvider",
        return_value=mock_instance,
    ) as mock_cls:
        config = _make_config()
        result = create_embedding_provider(config)
    mock_cls.assert_called_once_with(
        config, default_base_url="https://api.berget.ai/v1"
    )
    assert result is mock_instance


def test_create_embedding_provider_defaults_to_berget() -> None:
    mock_instance = MagicMock()
    with patch(
        "ai.providers.berget_embeddings.BergetEmbeddingProvider",
        return_value=mock_instance,
    ):
        result = create_embedding_provider(EmbeddingConfig(BERGET_API_KEY="test-key"))
    assert result is mock_instance
