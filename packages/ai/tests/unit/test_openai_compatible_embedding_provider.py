"""Unit tests for OpenAiCompatibleEmbeddingProvider."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from llm_core import LLMOperation, Usage, set_trace_recorder

from ai.embedding import EmbeddingConfig, create_embedding_provider
from ai.errors import MissingApiKeyError
from ai.providers import openai_compatible_embeddings
from ai.providers.openai_compatible_embeddings import OpenAiCompatibleEmbeddingProvider

_BASE_URL = "https://api.berget.test/v1"


@pytest.fixture(autouse=True)
def sdk_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """The SDK client the provider will be handed for the running loop.

    Patched at the accessor rather than on the instance: the provider looks its
    client up per call, because a client outliving its event loop is what caused
    the ingest's near-100 % retry rate. See `llm_core._clients`.
    """
    client = MagicMock()
    monkeypatch.setattr(
        openai_compatible_embeddings, "get_async_openai", lambda **_kwargs: client
    )
    return client


def _make_config(
    api_key: str | None = "test-key", base_url: str | None = _BASE_URL
) -> EmbeddingConfig:
    return EmbeddingConfig(
        EMBEDDING_MODEL="intfloat/multilingual-e5-large",
        EMBEDDING_PROVIDER="openai_compatible",
        LLM_API_KEY=api_key,
        LLM_BASE_URL=base_url,
    )


def test_missing_api_key_raises() -> None:
    config = _make_config(api_key=None)
    with pytest.raises(MissingApiKeyError, match="An API key is required"):
        OpenAiCompatibleEmbeddingProvider(config)


async def test_uses_configured_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """There is no built-in default: the host comes from llm_config.yaml, so a
    provider pointed at nothing is a configuration error, not a silent fallback
    onto whichever host happened to be wired up first."""
    requested: list[dict[str, object]] = []
    client = MagicMock()
    client.embeddings.create = AsyncMock(
        return_value=SimpleNamespace(data=[SimpleNamespace(embedding=[0.1])])
    )

    def _record(**kwargs: object) -> MagicMock:
        requested.append(kwargs)
        return client

    monkeypatch.setattr(openai_compatible_embeddings, "get_async_openai", _record)
    provider = OpenAiCompatibleEmbeddingProvider(
        _make_config(base_url="https://example.test/v1")
    )

    await provider.embed(["a"])

    assert requested == [{"api_key": "test-key", "base_url": "https://example.test/v1"}]


@pytest.mark.asyncio
async def test_embed_returns_vectors(sdk_client: MagicMock) -> None:
    provider = OpenAiCompatibleEmbeddingProvider(_make_config())

    response = MagicMock()
    response.data = [MagicMock(embedding=[0.1, 0.2]), MagicMock(embedding=[0.3, 0.4])]
    sdk_client.embeddings.create = AsyncMock(return_value=response)

    result = await provider.embed(["a", "b"])

    assert result == [[0.1, 0.2], [0.3, 0.4]]
    sdk_client.embeddings.create.assert_called_once_with(
        model="intfloat/multilingual-e5-large", input=["a", "b"]
    )


@pytest.mark.asyncio
async def test_empty_input_short_circuits(sdk_client: MagicMock) -> None:
    provider = OpenAiCompatibleEmbeddingProvider(_make_config())
    sdk_client.embeddings.create = AsyncMock()

    result = await provider.embed([])

    assert result == []
    sdk_client.embeddings.create.assert_not_called()


def test_create_embedding_provider_openai_compatible_dispatch() -> None:
    mock_instance = MagicMock()
    with patch(
        "ai.providers.openai_compatible_embeddings.OpenAiCompatibleEmbeddingProvider",
        return_value=mock_instance,
    ) as mock_cls:
        config = _make_config()
        result = create_embedding_provider(config)
    mock_cls.assert_called_once_with(config)
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
        return OpenAiCompatibleEmbeddingProvider(_make_config())

    def _response(self, **attrs):
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2])],
            **attrs,
        )

    @pytest.mark.asyncio
    async def test_successful_embed_is_recorded(self, recorder, sdk_client) -> None:
        provider = self._provider()
        sdk_client.embeddings.create = AsyncMock(
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
        assert record.provider == "openai_compatible"

    @pytest.mark.asyncio
    async def test_record_counts_texts_without_storing_them(
        self, recorder, sdk_client
    ) -> None:
        """Chunk text is already in Postgres; copying it here buys nothing."""
        provider = self._provider()
        sdk_client.embeddings.create = AsyncMock(
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
    async def test_failed_embed_is_recorded_and_reraised(
        self, recorder, sdk_client
    ) -> None:
        provider = self._provider()
        sdk_client.embeddings.create = AsyncMock(
            side_effect=RuntimeError("upstream 503")
        )

        with pytest.raises(RuntimeError):
            await provider.embed(["abc"])

        (record,) = recorder.records
        assert record.success is False
        assert record.error_type == "RuntimeError"

    @pytest.mark.asyncio
    async def test_empty_input_records_nothing(self, recorder, sdk_client) -> None:
        provider = self._provider()
        sdk_client.embeddings.create = AsyncMock()

        await provider.embed([])

        assert recorder.records == []
