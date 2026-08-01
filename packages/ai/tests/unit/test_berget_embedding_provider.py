"""Unit tests for BergetEmbeddingProvider."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llm_core import LLMOperation, Usage, set_trace_recorder

from ai.embedding import EmbeddingConfig, create_embedding_provider
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
    with pytest.raises(ValueError, match="An API key is required"):
        BergetEmbeddingProvider(config, default_base_url="https://api.berget.ai/v1")


def test_resolved_api_key_is_accepted() -> None:
    """The config loader resolves the key from the variable a provider names,
    so it arrives in the host-agnostic field rather than the Berget-named one."""
    config = EmbeddingConfig(
        EMBEDDING_MODEL="intfloat/multilingual-e5-large",
        EMBEDDING_PROVIDER="openai_compatible",
        LLM_API_KEY="resolved-key",
    )

    provider = BergetEmbeddingProvider(
        config, default_base_url="https://api.berget.ai/v1"
    )

    assert provider._client.api_key == "resolved-key"


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


class TestEmbedTracing:
    """Embedding runs once per chunk, so its token spend has to be visible."""

    @pytest.fixture
    def recorder(self):
        class Recording:
            def __init__(self):
                self.records = []

            def record(self, record):
                self.records.append(record)

        recorder = Recording()
        set_trace_recorder(recorder)
        yield recorder
        set_trace_recorder(None)

    def _provider(self):
        with patch("openai.AsyncOpenAI"):
            return BergetEmbeddingProvider(
                _make_config(), default_base_url="https://api.berget.ai/v1"
            )

    def _response(self, **attrs):
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2])],
            **attrs,
        )

    @pytest.mark.asyncio
    async def test_successful_embed_is_recorded(self, recorder) -> None:
        provider = self._provider()
        provider._client.embeddings.create = AsyncMock(
            return_value=self._response(
                usage=SimpleNamespace(prompt_tokens=812, total_tokens=812),
                model="intfloat/multilingual-e5-large",
            )
        )

        await provider.embed(["kyrkomötet beslutade", "stiftet överklagade"])

        (record,) = recorder.records
        assert record.operation == LLMOperation.embed
        assert record.success is True
        assert record.usage == Usage(input_tokens=812, total_tokens=812)
        assert record.model == "intfloat/multilingual-e5-large"
        assert record.provider == "berget"

    @pytest.mark.asyncio
    async def test_record_counts_texts_without_storing_them(self, recorder) -> None:
        """Chunk text is already in Postgres; copying it here buys nothing."""
        provider = self._provider()
        provider._client.embeddings.create = AsyncMock(
            return_value=self._response(usage=None, model=None)
        )

        await provider.embed(["abc", "de"])

        (record,) = recorder.records
        assert record.context["source"] == "ai.embed"
        assert record.context["texts_count"] == 2
        assert record.context["input_chars"] == 5
        assert record.messages == ()
        assert record.response_text is None

    @pytest.mark.asyncio
    async def test_failed_embed_is_recorded_and_reraised(self, recorder) -> None:
        provider = self._provider()
        provider._client.embeddings.create = AsyncMock(
            side_effect=RuntimeError("upstream 503")
        )

        with pytest.raises(RuntimeError):
            await provider.embed(["abc"])

        (record,) = recorder.records
        assert record.success is False
        assert record.error_type == "RuntimeError"

    @pytest.mark.asyncio
    async def test_empty_input_records_nothing(self, recorder) -> None:
        provider = self._provider()
        provider._client.embeddings.create = AsyncMock()

        await provider.embed([])

        assert recorder.records == []
