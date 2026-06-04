from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from llm_core._types import LLMResponse, Message, Role, ToolCall, ToolDefinition
from llm_core.providers._gemini import GeminiProvider


def _make_provider() -> GeminiProvider:
    provider = object.__new__(GeminiProvider)
    provider._model = "test-model"
    provider._temperature = 0.0
    provider._max_tokens = None
    provider._client = MagicMock()
    return provider


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
