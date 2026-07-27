from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from llm_core._types import (
    LLMResponse,
    Message,
    Role,
    ToolCall,
    ToolDefinition,
    Usage,
)
from llm_core.providers._gemini import GeminiProvider, _usage_from_gemini


def _make_provider() -> GeminiProvider:
    provider = object.__new__(GeminiProvider)
    provider._model = "test-model"
    provider._temperature = 0.0
    provider._max_tokens = None
    provider._client = MagicMock()
    provider._provider_name = "gemini"
    return provider


def _make_usage_metadata(**counts: int):
    """Usage metadata carrying only the attributes named.

    MagicMock would answer every getattr, so an attribute that is genuinely
    absent has to be genuinely absent here.
    """
    return SimpleNamespace(**counts)


class TestSplitSystem:
    def test_no_system_message(self) -> None:
        provider = _make_provider()
        msgs = [Message(role=Role.user, content="Hello")]
        system, remaining = provider._split_system(msgs)
        assert system is None
        assert remaining == msgs

    def test_with_system_message(self) -> None:
        provider = _make_provider()
        system_msg = Message(role=Role.system, content="You are a helpful assistant.")
        user_msg = Message(role=Role.user, content="Hello")
        msgs = [system_msg, user_msg]

        system, remaining = provider._split_system(msgs)

        assert system == "You are a helpful assistant."
        assert remaining == [user_msg]

    def test_empty_messages(self) -> None:
        provider = _make_provider()
        system, remaining = provider._split_system([])
        assert system is None
        assert remaining == []

    def test_system_only(self) -> None:
        provider = _make_provider()
        msgs = [Message(role=Role.system, content="System only")]
        system, remaining = provider._split_system(msgs)
        assert system == "System only"
        assert remaining == []


class TestToGeminiContent:
    def test_user_message(self) -> None:
        from google.genai import types

        provider = _make_provider()
        msg = Message(role=Role.user, content="Hello")
        content = provider._to_gemini_content(msg)
        assert isinstance(content, types.Content)
        assert content.role == "user"
        assert len(content.parts) == 1
        assert content.parts[0].text == "Hello"

    def test_assistant_text_message(self) -> None:
        from google.genai import types

        provider = _make_provider()
        msg = Message(role=Role.assistant, content="I can help")
        content = provider._to_gemini_content(msg)
        assert isinstance(content, types.Content)
        assert content.role == "model"
        assert len(content.parts) == 1
        assert content.parts[0].text == "I can help"

    def test_assistant_with_tool_calls(self) -> None:
        from google.genai import types

        provider = _make_provider()
        tc = ToolCall(id="tc-1", name="search", arguments={"q": "test"})
        msg = Message(role=Role.assistant, content="", tool_calls=(tc,))
        content = provider._to_gemini_content(msg)
        assert isinstance(content, types.Content)
        assert content.role == "model"
        assert len(content.parts) == 1
        fc = content.parts[0].function_call
        assert fc is not None
        assert fc.name == "search"

    def test_tool_result_message(self) -> None:
        from google.genai import types

        provider = _make_provider()
        msg = Message(
            role=Role.tool_result,
            content="search results",
            tool_call_id="tc-1",
            tool_name="search",
        )
        content = provider._to_gemini_content(msg)
        assert isinstance(content, types.Content)
        assert content.role == "user"
        assert len(content.parts) == 1
        fr = content.parts[0].function_response
        assert fr is not None
        assert fr.name == "search"

    def test_unsupported_role_raises(self) -> None:
        provider = _make_provider()
        msg = Message(role=Role.system, content="system")
        with pytest.raises(ValueError, match="Cannot map role"):
            provider._to_gemini_content(msg)


class TestToGeminiTools:
    def test_single_tool(self) -> None:
        from google.genai import types

        provider = _make_provider()
        td = ToolDefinition(
            name="search",
            description="Search the web",
            parameters={"type": "object", "properties": {"q": {"type": "string"}}},
        )
        tool = provider._to_gemini_tools([td])
        assert isinstance(tool, types.Tool)
        assert len(tool.function_declarations) == 1
        assert tool.function_declarations[0].name == "search"
        assert tool.function_declarations[0].description == "Search the web"

    def test_multiple_tools(self) -> None:
        from google.genai import types

        provider = _make_provider()
        tools = [
            ToolDefinition(name="search", description="Search", parameters={}),
            ToolDefinition(name="fetch", description="Fetch URL", parameters={}),
        ]
        result = provider._to_gemini_tools(tools)
        assert isinstance(result, types.Tool)
        assert len(result.function_declarations) == 2
        names = {fd.name for fd in result.function_declarations}
        assert names == {"search", "fetch"}


class TestFromGeminiResponse:
    def _make_text_response(self, text: str) -> MagicMock:
        part = MagicMock()
        part.text = text
        part.function_call = None
        content = MagicMock()
        content.parts = [part]
        candidate = MagicMock()
        candidate.content = content
        response = MagicMock()
        response.candidates = [candidate]
        return response

    def _make_tool_call_response(
        self, name: str, args: dict, call_id: str | None
    ) -> MagicMock:
        fc = MagicMock()
        fc.id = call_id
        fc.name = name
        fc.args = args
        part = MagicMock()
        part.text = None
        part.function_call = fc
        content = MagicMock()
        content.parts = [part]
        candidate = MagicMock()
        candidate.content = content
        response = MagicMock()
        response.candidates = [candidate]
        return response

    def test_text_response(self) -> None:
        provider = _make_provider()
        raw = self._make_text_response("Hello there")
        result = provider._from_gemini_response(raw)
        assert isinstance(result, LLMResponse)
        assert result.message.role == Role.assistant
        assert result.message.content == "Hello there"
        assert result.message.tool_calls == ()
        assert result.raw is raw

    def test_tool_call_response(self) -> None:
        provider = _make_provider()
        raw = self._make_tool_call_response("search", {"q": "test"}, "fc-123")
        result = provider._from_gemini_response(raw)
        assert result.message.role == Role.assistant
        assert len(result.message.tool_calls) == 1
        tc = result.message.tool_calls[0]
        assert tc.id == "fc-123"
        assert tc.name == "search"
        assert tc.arguments == {"q": "test"}

    def test_tool_call_with_null_id_generates_uuid(self) -> None:
        provider = _make_provider()
        raw = self._make_tool_call_response("search", {}, None)
        result = provider._from_gemini_response(raw)
        tc = result.message.tool_calls[0]
        assert tc.id is not None
        assert len(tc.id) > 0

    def test_empty_candidates(self) -> None:
        provider = _make_provider()
        response = MagicMock()
        response.candidates = []
        result = provider._from_gemini_response(response)
        assert result.message.content == ""
        assert result.message.tool_calls == ()

    def test_none_candidates(self) -> None:
        provider = _make_provider()
        response = MagicMock()
        response.candidates = None
        result = provider._from_gemini_response(response)
        assert result.message.content == ""
        assert result.message.tool_calls == ()


class TestUsageMapping:
    def test_maps_all_token_counts(self) -> None:
        usage = _usage_from_gemini(
            _make_usage_metadata(
                prompt_token_count=120,
                candidates_token_count=30,
                total_token_count=150,
            )
        )
        assert usage == Usage(input_tokens=120, output_tokens=30, total_tokens=150)

    def test_missing_metadata_maps_to_none(self) -> None:
        assert _usage_from_gemini(None) is None

    def test_thinking_tokens_count_as_output(self) -> None:
        """Thinking bills at the output rate but is excluded from candidates."""
        usage = _usage_from_gemini(
            _make_usage_metadata(
                prompt_token_count=120,
                candidates_token_count=30,
                thoughts_token_count=200,
                total_token_count=350,
            )
        )
        assert usage == Usage(input_tokens=120, output_tokens=230, total_tokens=350)

    def test_thinking_tokens_alone_still_count_as_output(self) -> None:
        usage = _usage_from_gemini(_make_usage_metadata(thoughts_token_count=200))
        assert usage == Usage(input_tokens=None, output_tokens=200, total_tokens=None)

    def test_absent_output_counters_stay_none_not_zero(self) -> None:
        usage = _usage_from_gemini(_make_usage_metadata(prompt_token_count=120))
        assert usage == Usage(input_tokens=120, output_tokens=None, total_tokens=None)


class TestResponseAttribution:
    def test_response_carries_usage_model_and_provider(self) -> None:
        provider = _make_provider()
        response = SimpleNamespace(
            candidates=[],
            usage_metadata=_make_usage_metadata(
                prompt_token_count=10,
                candidates_token_count=4,
                total_token_count=14,
            ),
            model_version="gemini-2.5-flash-001",
        )

        result = provider._from_gemini_response(response)

        assert result.usage == Usage(input_tokens=10, output_tokens=4, total_tokens=14)
        assert result.model == "gemini-2.5-flash-001"
        assert result.provider == "gemini"

    def test_model_falls_back_to_the_configured_name(self) -> None:
        provider = _make_provider()
        response = SimpleNamespace(candidates=[])

        result = provider._from_gemini_response(response)

        assert result.model == "test-model"
        assert result.usage is None


class TestStreamUsage:
    async def _collect(self, provider):
        return [
            chunk
            async for chunk in await provider.generate_stream(
                [Message(role=Role.user, content="hi")]
            )
        ]

    @pytest.mark.asyncio
    async def test_textless_usage_chunk_is_yielded(self) -> None:
        provider = _make_provider()

        async def _fake_stream():
            yield SimpleNamespace(text="Hej", usage_metadata=None)
            yield SimpleNamespace(
                text=None,
                usage_metadata=_make_usage_metadata(
                    prompt_token_count=50,
                    candidates_token_count=12,
                    total_token_count=62,
                ),
                model_version="gemini-2.5-flash-001",
            )

        provider._client.aio.models.generate_content_stream = AsyncMock(
            return_value=_fake_stream()
        )

        chunks = await self._collect(provider)

        assert [c.text for c in chunks] == ["Hej", ""]
        assert chunks[-1].usage == Usage(
            input_tokens=50, output_tokens=12, total_tokens=62
        )

    @pytest.mark.asyncio
    async def test_chunk_with_neither_text_nor_usage_is_skipped(self) -> None:
        provider = _make_provider()

        async def _fake_stream():
            yield SimpleNamespace(text=None, usage_metadata=None)
            yield SimpleNamespace(text="Hej", usage_metadata=None)

        provider._client.aio.models.generate_content_stream = AsyncMock(
            return_value=_fake_stream()
        )

        assert [c.text for c in await self._collect(provider)] == ["Hej"]
