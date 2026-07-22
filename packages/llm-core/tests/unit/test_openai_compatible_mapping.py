from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import omit
from pydantic import BaseModel

from llm_core._exceptions import ProviderError
from llm_core._types import (
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolDefinition,
)
from llm_core.providers._openai_compatible import OpenAiCompatibleProvider


def _make_provider() -> OpenAiCompatibleProvider:
    provider = object.__new__(OpenAiCompatibleProvider)
    provider._model = "test-model"
    provider._temperature = 0.0
    provider._max_tokens = None
    provider._client = MagicMock()
    return provider


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
    async def test_generate_wraps_sdk_errors(self) -> None:
        provider = _make_provider()
        provider._client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        with pytest.raises(ProviderError):
            await provider.generate([Message(role=Role.user, content="hi")])

    @pytest.mark.asyncio
    async def test_generate_returns_mapped_response(self) -> None:
        provider = _make_provider()
        message = MagicMock()
        message.content = "answer"
        message.tool_calls = None
        response = MagicMock()
        response.choices = [MagicMock(message=message)]
        provider._client.chat.completions.create = AsyncMock(return_value=response)

        result = await provider.generate([Message(role=Role.user, content="hi")])

        assert result.message.content == "answer"
        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "test-model"
        assert call_kwargs["tools"] is omit
        assert call_kwargs["response_format"] is omit

    @pytest.mark.asyncio
    async def test_generate_with_response_schema_sets_response_format(self) -> None:
        provider = _make_provider()
        message = MagicMock()
        message.content = '{"ranked_indices": [0, 1]}'
        message.tool_calls = None
        response = MagicMock()
        response.choices = [MagicMock(message=message)]
        provider._client.chat.completions.create = AsyncMock(return_value=response)

        await provider.generate(
            [Message(role=Role.user, content="hi")],
            response_schema=_RerankResult,
        )

        call_kwargs = provider._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"]["type"] == "json_schema"


class TestGenerateStream:
    @pytest.mark.asyncio
    async def test_generate_stream_yields_text_chunks(self) -> None:
        provider = _make_provider()

        async def _fake_stream():
            for text in ["Hel", "lo"]:
                chunk = MagicMock()
                chunk.choices = [MagicMock(delta=MagicMock(content=text))]
                yield chunk
            empty_chunk = MagicMock()
            empty_chunk.choices = [MagicMock(delta=MagicMock(content=None))]
            yield empty_chunk

        provider._client.chat.completions.create = AsyncMock(
            return_value=_fake_stream()
        )

        chunks = [
            chunk
            async for chunk in await provider.generate_stream(
                [Message(role=Role.user, content="hi")]
            )
        ]

        assert [c.text for c in chunks] == ["Hel", "lo"]
        assert all(isinstance(c, StreamChunk) for c in chunks)

    @pytest.mark.asyncio
    async def test_generate_stream_wraps_sdk_errors(self) -> None:
        provider = _make_provider()
        provider._client.chat.completions.create = AsyncMock(
            side_effect=RuntimeError("boom")
        )
        with pytest.raises(ProviderError):
            await provider.generate_stream([Message(role=Role.user, content="hi")])
