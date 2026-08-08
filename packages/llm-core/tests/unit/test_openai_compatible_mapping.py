from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import omit
from pydantic import BaseModel

from llm_core._config import ProviderKind
from llm_core._exceptions import ProviderError
from llm_core._types import (
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    Usage,
)
from llm_core.providers import _openai_compatible
from llm_core.providers._openai_compatible import (
    OpenAiCompatibleProvider,
    _usage_from_openai,
)


@pytest.fixture(autouse=True)
def sdk_client(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """The SDK client the provider will be handed for the running loop.

    Patched at the accessor rather than on the instance: the provider looks its
    client up per call, because a client outliving its event loop is what caused
    the ingest's near-100 % retry rate. See `llm_core._clients`.
    """
    client = MagicMock()
    monkeypatch.setattr(
        _openai_compatible, "get_async_openai", lambda **_kwargs: client
    )
    return client


def _make_provider(stream_usage: bool = True) -> OpenAiCompatibleProvider:
    provider = object.__new__(OpenAiCompatibleProvider)
    provider._model = "test-model"
    provider._temperature = 0.0
    provider._max_tokens = None
    provider._api_key = "test-key"
    provider._base_url = "https://example.invalid/v1"
    provider._provider_name = ProviderKind.OPENAI_COMPATIBLE
    provider._stream_usage = stream_usage
    return provider


def _make_usage(prompt: int | None, completion: int | None, total: int | None):
    """A usage block with only the SDK's real attributes.

    MagicMock would answer every getattr, so the mapper must be handed
    something that can actually be missing an attribute.
    """
    usage = SimpleNamespace()
    if prompt is not None:
        usage.prompt_tokens = prompt
    if completion is not None:
        usage.completion_tokens = completion
    if total is not None:
        usage.total_tokens = total
    return usage


class _RerankResult(BaseModel):
    ranked_indices: list[int]


class TestToOpenaiMessage:
    def test_system_message(self) -> None:
        provider = _make_provider()
        msg = Message(role=Role.system, content="You are helpful.")
        result = provider._to_openai_message(msg)
        assert result == {"role": "system", "content": "You are helpful."}

    def test_user_message(self) -> None:
        provider = _make_provider()
        msg = Message(role=Role.user, content="Hello")
        result = provider._to_openai_message(msg)
        assert result == {"role": "user", "content": "Hello"}

    def test_assistant_text_message(self) -> None:
        provider = _make_provider()
        msg = Message(role=Role.assistant, content="I can help")
        result = provider._to_openai_message(msg)
        assert result == {"role": "assistant", "content": "I can help"}

    def test_assistant_with_tool_calls(self) -> None:
        provider = _make_provider()
        tc = ToolCall(id="tc-1", name="search", arguments={"q": "test"})
        msg = Message(role=Role.assistant, content="", tool_calls=(tc,))
        result = provider._to_openai_message(msg)
        assert result["role"] == "assistant"
        assert result["tool_calls"] == [
            {
                "id": "tc-1",
                "type": "function",
                "function": {"name": "search", "arguments": json.dumps({"q": "test"})},
            }
        ]

    def test_tool_result_message(self) -> None:
        provider = _make_provider()
        msg = Message(
            role=Role.tool_result,
            content="search results",
            tool_call_id="tc-1",
            tool_name="search",
        )
        result = provider._to_openai_message(msg)
        assert result == {
            "role": "tool",
            "tool_call_id": "tc-1",
            "content": "search results",
        }

    def test_unsupported_role_raises(self) -> None:
        provider = _make_provider()
        msg = Message(role=Role.tool_call, content="x")
        with pytest.raises(ValueError, match="Cannot map role"):
            provider._to_openai_message(msg)


class TestToOpenaiTools:
    def test_single_tool(self) -> None:
        provider = _make_provider()
        td = ToolDefinition(
            name="search",
            description="Search the web",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}},
        )
        result = provider._to_openai_tools([td])
        assert result == [
            {
                "type": "function",
                "function": {
                    "name": "search",
                    "description": "Search the web",
                    "parameters": td.parameters,
                },
            }
        ]

    def test_multiple_tools(self) -> None:
        provider = _make_provider()
        tools = [
            ToolDefinition(name="search", description="Search", parameters={}),
            ToolDefinition(name="fetch", description="Fetch URL", parameters={}),
        ]
        result = provider._to_openai_tools(tools)
        names = {t["function"]["name"] for t in result}
        assert names == {"search", "fetch"}


class TestToResponseFormat:
    def test_response_format_shape(self) -> None:
        provider = _make_provider()
        result = provider._to_response_format(_RerankResult)
        assert result["type"] == "json_schema"
        assert result["json_schema"]["name"] == "_RerankResult"
        assert result["json_schema"]["strict"] is True
        assert result["json_schema"]["schema"] == _RerankResult.model_json_schema()


class TestFromOpenaiMessage:
    def _make_message(
        self, content: str | None, tool_calls: list | None = None
    ) -> MagicMock:
        message = MagicMock()
        message.content = content
        message.tool_calls = tool_calls
        return message

    def test_text_response(self) -> None:
        provider = _make_provider()
        message = self._make_message("Hello there")
        result = provider._from_openai_message(message, raw="raw-response")
        assert isinstance(result, LLMResponse)
        assert result.message.role == Role.assistant
        assert result.message.content == "Hello there"
        assert result.message.tool_calls == ()
        assert result.raw == "raw-response"

    def test_tool_call_response(self) -> None:
        provider = _make_provider()
        tc = MagicMock()
        tc.id = "tc-123"
        tc.function.name = "search"
        tc.function.arguments = json.dumps({"q": "test"})
        message = self._make_message(None, tool_calls=[tc])
        result = provider._from_openai_message(message, raw=None)
        assert result.message.content == ""
        assert len(result.message.tool_calls) == 1
        mapped = result.message.tool_calls[0]
        assert mapped.id == "tc-123"
        assert mapped.name == "search"
        assert mapped.arguments == {"q": "test"}

    def test_tool_call_with_null_id_generates_uuid(self) -> None:
        provider = _make_provider()
        tc = MagicMock()
        tc.id = None
        tc.function.name = "search"
        tc.function.arguments = "{}"
        message = self._make_message(None, tool_calls=[tc])
        result = provider._from_openai_message(message, raw=None)
        mapped = result.message.tool_calls[0]
        assert mapped.id is not None
        assert len(mapped.id) > 0

    def test_no_tool_calls(self) -> None:
        provider = _make_provider()
        message = self._make_message("plain text", tool_calls=None)
        result = provider._from_openai_message(message, raw=None)
        assert result.message.tool_calls == ()


class TestGenerate:
    @pytest.mark.asyncio
    async def test_generate_wraps_sdk_errors(self, sdk_client: MagicMock) -> None:
        provider = _make_provider()
        sdk_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(ProviderError):
            await provider.generate([Message(role=Role.user, content="hi")])

    @pytest.mark.asyncio
    async def test_generate_returns_mapped_response(
        self, sdk_client: MagicMock
    ) -> None:
        provider = _make_provider()
        message = MagicMock()
        message.content = "answer"
        message.tool_calls = None
        response = MagicMock()
        response.choices = [MagicMock(message=message)]
        sdk_client.chat.completions.create = AsyncMock(return_value=response)

        result = await provider.generate([Message(role=Role.user, content="hi")])

        assert result.message.content == "answer"
        call_kwargs = sdk_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["tools"] is omit
        assert call_kwargs["response_format"] is omit

    @pytest.mark.asyncio
    async def test_generate_with_response_schema_sets_response_format(
        self, sdk_client: MagicMock
    ) -> None:
        provider = _make_provider()
        message = MagicMock()
        message.content = '{"ranked_indices": [0, 1]}'
        message.tool_calls = None
        response = MagicMock()
        response.choices = [MagicMock(message=message)]
        sdk_client.chat.completions.create = AsyncMock(return_value=response)

        await provider.generate(
            [Message(role=Role.user, content="hi")],
            response_schema=_RerankResult,
        )

        call_kwargs = sdk_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"]["type"] == "json_schema"


class TestGenerateStream:
    @pytest.mark.asyncio
    async def test_generate_stream_yields_text_chunks(
        self, sdk_client: MagicMock
    ) -> None:
        provider = _make_provider()

        async def _fake_stream():
            for text in ["Hel", "lo"]:
                chunk = MagicMock()
                chunk.choices = [MagicMock(delta=MagicMock(content=text))]
                yield chunk
            empty_chunk = MagicMock()
            empty_chunk.choices = [MagicMock(delta=MagicMock(content=None))]
            yield empty_chunk

        sdk_client.chat.completions.create = AsyncMock(return_value=_fake_stream())

        chunks = [
            chunk
            async for chunk in await provider.generate_stream(
                [Message(role=Role.user, content="hi")]
            )
        ]

        assert [c.text for c in chunks] == ["Hel", "lo"]
        assert all(isinstance(c, StreamChunk) for c in chunks)

    @pytest.mark.asyncio
    async def test_generate_stream_wraps_sdk_errors(
        self, sdk_client: MagicMock
    ) -> None:
        provider = _make_provider()
        sdk_client.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
        with pytest.raises(ProviderError):
            await provider.generate_stream([Message(role=Role.user, content="hi")])


class TestUsageMapping:
    def test_maps_all_token_counts(self) -> None:
        usage = _usage_from_openai(_make_usage(120, 30, 150))
        assert usage == Usage(input_tokens=120, output_tokens=30, total_tokens=150)

    def test_missing_usage_maps_to_none(self) -> None:
        assert _usage_from_openai(None) is None

    def test_absent_counters_stay_none_not_zero(self) -> None:
        usage = _usage_from_openai(_make_usage(120, None, None))
        assert usage == Usage(input_tokens=120, output_tokens=None, total_tokens=None)


class TestResponseAttribution:
    @pytest.mark.asyncio
    async def test_generate_attaches_usage_model_and_provider(
        self, sdk_client: MagicMock
    ) -> None:
        provider = _make_provider()
        message = SimpleNamespace(content="answer", tool_calls=None)
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=message)],
            usage=_make_usage(10, 4, 14),
            model="test-model-2026-07-01",
        )
        sdk_client.chat.completions.create = AsyncMock(return_value=response)

        result = await provider.generate([Message(role=Role.user, content="hi")])

        assert result.usage == Usage(input_tokens=10, output_tokens=4, total_tokens=14)
        assert result.model == "test-model-2026-07-01"
        assert result.provider == ProviderKind.OPENAI_COMPATIBLE

    @pytest.mark.asyncio
    async def test_model_falls_back_to_the_configured_name(
        self, sdk_client: MagicMock
    ) -> None:
        provider = _make_provider()
        message = SimpleNamespace(content="answer", tool_calls=None)
        response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
        sdk_client.chat.completions.create = AsyncMock(return_value=response)

        result = await provider.generate([Message(role=Role.user, content="hi")])

        assert result.model == "test-model"
        assert result.usage is None


class TestStreamUsage:
    def _text_chunk(self, text: str):
        return SimpleNamespace(
            choices=[SimpleNamespace(delta=SimpleNamespace(content=text))]
        )

    def _usage_chunk(self):
        return SimpleNamespace(
            choices=[], usage=_make_usage(50, 12, 62), model="served"
        )

    async def _collect(self, provider):
        return [
            chunk
            async for chunk in await provider.generate_stream(
                [Message(role=Role.user, content="hi")]
            )
        ]

    @pytest.mark.asyncio
    async def test_final_usage_chunk_is_not_dropped(
        self, sdk_client: MagicMock
    ) -> None:
        provider = _make_provider()

        async def _fake_stream():
            yield self._text_chunk("Hej")
            yield self._usage_chunk()

        sdk_client.chat.completions.create = AsyncMock(return_value=_fake_stream())

        chunks = await self._collect(provider)

        assert [c.text for c in chunks] == ["Hej", ""]
        assert chunks[-1].usage == Usage(
            input_tokens=50, output_tokens=12, total_tokens=62
        )
        assert chunks[-1].model == "served"

    @pytest.mark.asyncio
    async def test_choiceless_chunk_without_usage_is_still_skipped(
        self, sdk_client: MagicMock
    ) -> None:
        provider = _make_provider()

        async def _fake_stream():
            yield SimpleNamespace(choices=[])
            yield self._text_chunk("Hej")

        sdk_client.chat.completions.create = AsyncMock(return_value=_fake_stream())

        assert [c.text for c in await self._collect(provider)] == ["Hej"]

    @pytest.mark.asyncio
    async def test_stream_options_requested_when_enabled(
        self, sdk_client: MagicMock
    ) -> None:
        provider = _make_provider(stream_usage=True)

        async def _fake_stream():
            yield self._text_chunk("Hej")

        sdk_client.chat.completions.create = AsyncMock(return_value=_fake_stream())
        await provider.generate_stream([Message(role=Role.user, content="hi")])

        kwargs = sdk_client.chat.completions.create.call_args.kwargs
        assert kwargs["stream_options"] == {"include_usage": True}

    @pytest.mark.asyncio
    async def test_stream_options_omitted_when_disabled(
        self, sdk_client: MagicMock
    ) -> None:
        provider = _make_provider(stream_usage=False)

        async def _fake_stream():
            yield self._text_chunk("Hej")

        sdk_client.chat.completions.create = AsyncMock(return_value=_fake_stream())
        await provider.generate_stream([Message(role=Role.user, content="hi")])

        kwargs = sdk_client.chat.completions.create.call_args.kwargs
        assert kwargs["stream_options"] is omit
