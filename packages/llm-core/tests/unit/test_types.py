from __future__ import annotations

import dataclasses

import pytest

from llm_core._types import (
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolDefinition,
)


def test_role_values() -> None:
    assert Role.system == "system"
    assert Role.user == "user"
    assert Role.assistant == "assistant"
    assert Role.tool_call == "tool_call"
    assert Role.tool_result == "tool_result"


def test_tool_call_construction() -> None:
    tc = ToolCall(id="tc-1", name="my_tool", arguments={"key": "value"})
    assert tc.id == "tc-1"
    assert tc.name == "my_tool"
    assert tc.arguments == {"key": "value"}


def test_message_defaults() -> None:
    msg = Message(role=Role.user, content="Hello")
    assert msg.role == Role.user
    assert msg.content == "Hello"
    assert msg.tool_calls == ()
    assert msg.tool_call_id is None
    assert msg.tool_name is None


def test_message_with_tool_calls() -> None:
    tc = ToolCall(id="1", name="search", arguments={"q": "test"})
    msg = Message(role=Role.assistant, content="", tool_calls=(tc,))
    assert len(msg.tool_calls) == 1
    assert msg.tool_calls[0] is tc


def test_message_tool_result() -> None:
    msg = Message(
        role=Role.tool_result,
        content="result data",
        tool_call_id="tc-1",
        tool_name="search",
    )
    assert msg.tool_call_id == "tc-1"
    assert msg.tool_name == "search"


def test_message_frozen() -> None:
    msg = Message(role=Role.user, content="Hello")
    with pytest.raises(dataclasses.FrozenInstanceError):
        msg.content = "changed"  # type: ignore[misc]


def test_tool_call_frozen() -> None:
    tc = ToolCall(id="1", name="tool", arguments={})
    with pytest.raises(dataclasses.FrozenInstanceError):
        tc.name = "other"  # type: ignore[misc]


def test_tool_definition_construction() -> None:
    td = ToolDefinition(
        name="search",
        description="Searches the web",
        parameters={"type": "object", "properties": {}},
    )
    assert td.name == "search"
    assert td.description == "Searches the web"
    assert td.parameters["type"] == "object"


def test_llm_response_construction() -> None:
    msg = Message(role=Role.assistant, content="Hi")
    resp = LLMResponse(message=msg)
    assert resp.message is msg
    assert resp.raw is None


def test_llm_response_with_raw() -> None:
    msg = Message(role=Role.assistant, content="Hi")
    raw = object()
    resp = LLMResponse(message=msg, raw=raw)
    assert resp.raw is raw


def test_stream_chunk_construction() -> None:
    chunk = StreamChunk(text="Hello")
    assert chunk.text == "Hello"
    assert chunk.raw is None


def test_stream_chunk_with_raw() -> None:
    raw = object()
    chunk = StreamChunk(text="Hello", raw=raw)
    assert chunk.raw is raw
