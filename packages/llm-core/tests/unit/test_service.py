from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

from llm_core._exceptions import MaxIterationsError, ToolExecutionError
from llm_core._service import generate, generate_stream, generate_structured, tool_loop
from llm_core._types import (
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolDefinition,
)


def _make_response(
    content: str = "", tool_calls: tuple[ToolCall, ...] = ()
) -> LLMResponse:
    msg = Message(role=Role.assistant, content=content, tool_calls=tool_calls)
    return LLMResponse(message=msg)


async def _async_iter(*chunks: StreamChunk):
    for chunk in chunks:
        yield chunk


async def test_generate_passthrough() -> None:
    expected = _make_response("Hello")
    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value=expected)

    result = await generate(
        [Message(role=Role.user, content="Hi")], provider=mock_provider
    )

    assert result is expected
    mock_provider.generate.assert_awaited_once()


async def test_generate_structured_parses_model() -> None:
    class MyModel(BaseModel):
        name: str
        value: int

    response = _make_response('{"name": "test", "value": 42}')
    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value=response)

    result = await generate_structured(
        [Message(role=Role.user, content="Give me data")],
        MyModel,
        provider=mock_provider,
    )

    assert isinstance(result, MyModel)
    assert result.name == "test"
    assert result.value == 42


async def test_generate_stream_yields_text() -> None:
    chunks = [StreamChunk(text="Hello"), StreamChunk(text=" world")]
    mock_provider = AsyncMock()
    mock_provider.generate_stream = AsyncMock(return_value=_async_iter(*chunks))

    collected: list[str] = []
    async for text in generate_stream(
        [Message(role=Role.user, content="Hi")], provider=mock_provider
    ):
        collected.append(text)

    assert collected == ["Hello", " world"]


async def test_tool_loop_single_iteration() -> None:
    tc = ToolCall(id="tc-1", name="search", arguments={"q": "test"})
    first_response = _make_response("", tool_calls=(tc,))
    final_response = _make_response("Done!")

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(side_effect=[first_response, final_response])

    async def executor(q: str) -> str:
        return f"results for {q}"

    tools = [ToolDefinition(name="search", description="Search", parameters={})]
    messages = [Message(role=Role.user, content="Search for test")]

    result = await tool_loop(
        messages, tools, {"search": executor}, provider=mock_provider
    )

    assert result.message.content == "Done!"
    assert result.iterations == 2
    assert (
        len(result.history) == 4
    )  # user, assistant (tool call), tool_result, assistant (final)


async def test_tool_loop_multi_iteration() -> None:
    tc1 = ToolCall(id="tc-1", name="step1", arguments={})
    tc2 = ToolCall(id="tc-2", name="step2", arguments={})
    response1 = _make_response("", tool_calls=(tc1,))
    response2 = _make_response("", tool_calls=(tc2,))
    final = _make_response("All done")

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(side_effect=[response1, response2, final])

    async def noop() -> str:
        return "ok"

    tools = [
        ToolDefinition(name="step1", description="Step 1", parameters={}),
        ToolDefinition(name="step2", description="Step 2", parameters={}),
    ]
    messages = [Message(role=Role.user, content="Go")]

    result = await tool_loop(
        messages, tools, {"step1": noop, "step2": noop}, provider=mock_provider
    )

    assert result.message.content == "All done"
    assert result.iterations == 3


async def test_tool_loop_max_iterations_raises() -> None:
    tc = ToolCall(id="tc-1", name="loop", arguments={})
    looping_response = _make_response("", tool_calls=(tc,))

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value=looping_response)

    async def executor() -> str:
        return "ok"

    tools = [ToolDefinition(name="loop", description="Loop", parameters={})]

    with pytest.raises(MaxIterationsError):
        await tool_loop(
            [Message(role=Role.user, content="Go")],
            tools,
            {"loop": executor},
            provider=mock_provider,
            max_iterations=3,
        )

    assert mock_provider.generate.await_count == 3


async def test_tool_loop_unknown_tool_raises_key_error() -> None:
    tc = ToolCall(id="tc-1", name="missing_tool", arguments={})
    response = _make_response("", tool_calls=(tc,))

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value=response)

    tools = [ToolDefinition(name="missing_tool", description="Missing", parameters={})]

    with pytest.raises(KeyError, match="missing_tool"):
        await tool_loop(
            [Message(role=Role.user, content="Go")],
            tools,
            {},
            provider=mock_provider,
        )


async def test_tool_loop_executor_error_raises_tool_execution_error() -> None:
    tc = ToolCall(id="tc-1", name="bad_tool", arguments={})
    response = _make_response("", tool_calls=(tc,))

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value=response)

    async def failing_executor() -> Any:
        raise RuntimeError("Executor exploded")

    tools = [ToolDefinition(name="bad_tool", description="Bad", parameters={})]

    with pytest.raises(ToolExecutionError) as exc_info:
        await tool_loop(
            [Message(role=Role.user, content="Go")],
            tools,
            {"bad_tool": failing_executor},
            provider=mock_provider,
        )

    assert exc_info.value.tool_name == "bad_tool"
    assert isinstance(exc_info.value.__cause__, RuntimeError)


async def test_tool_loop_callbacks_invoked() -> None:
    tc = ToolCall(id="tc-1", name="search", arguments={"q": "test"})
    first_response = _make_response("", tool_calls=(tc,))
    final_response = _make_response("Done")

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(side_effect=[first_response, final_response])

    on_tool_call = AsyncMock()
    on_tool_result = AsyncMock()

    async def executor(q: str) -> str:
        return "found it"

    tools = [ToolDefinition(name="search", description="Search", parameters={})]

    await tool_loop(
        [Message(role=Role.user, content="Search")],
        tools,
        {"search": executor},
        provider=mock_provider,
        on_tool_call=on_tool_call,
        on_tool_result=on_tool_result,
    )

    on_tool_call.assert_awaited_once()
    call_args = on_tool_call.call_args
    assert call_args[0][0] is tc

    on_tool_result.assert_awaited_once()
    result_args = on_tool_result.call_args
    assert result_args[0][0] is tc
    assert result_args[0][1] == "found it"


async def test_tool_loop_result_serialized_as_json() -> None:
    tc = ToolCall(id="tc-1", name="get_data", arguments={})
    first_response = _make_response("", tool_calls=(tc,))
    final_response = _make_response("Got it")

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(side_effect=[first_response, final_response])

    async def executor() -> dict[str, Any]:
        return {"key": "value", "num": 42}

    tools = [ToolDefinition(name="get_data", description="Get data", parameters={})]
    messages = [Message(role=Role.user, content="Get")]

    result = await tool_loop(
        messages, tools, {"get_data": executor}, provider=mock_provider
    )

    tool_result_msg = result.history[2]
    assert tool_result_msg.role == Role.tool_result
    assert '"key": "value"' in tool_result_msg.content
