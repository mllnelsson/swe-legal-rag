from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel, ValidationError

from llm_core._exceptions import MaxIterationsError, ProviderError, ToolExecutionError
from llm_core._service import (
    ToolCallFinished,
    ToolCallStarted,
    ToolLoopFinished,
    generate,
    generate_stream,
    generate_structured,
    run_tool_loop,
    tool_loop,
)
from llm_core._tracing import LLMCallRecord, LLMOperation, set_trace_recorder
from llm_core._types import (
    LLMResponse,
    Message,
    Role,
    StreamChunk,
    ToolCall,
    ToolDefinition,
    Usage,
)


class RecordingRecorder:
    def __init__(self) -> None:
        self.records: list[LLMCallRecord] = []

    def record(self, record: LLMCallRecord) -> None:
        self.records.append(record)


class _Answer(BaseModel):
    answer: str


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

    result = await run_tool_loop(
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

    result = await run_tool_loop(
        messages, tools, {"step1": noop, "step2": noop}, provider=mock_provider
    )

    assert result.message.content == "All done"
    assert result.iterations == 3


async def test_tool_loop_terminal_tool_ends_the_run() -> None:
    tc_search = ToolCall(id="tc-1", name="search", arguments={"q": "test"})
    tc_answer = ToolCall(id="tc-2", name="answer", arguments={"picks": [1, 2]})
    # A third turn is scripted to prove the loop never asks for one.
    unreachable = _make_response("should never be requested")

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(
        side_effect=[
            _make_response("", tool_calls=(tc_search,)),
            _make_response("", tool_calls=(tc_answer,)),
            unreachable,
        ]
    )

    async def search(q: str) -> str:
        return f"results for {q}"

    async def answer(picks: list[int]) -> str:
        return "recorded"

    tools = [
        ToolDefinition(name="search", description="Search", parameters={}),
        ToolDefinition(name="answer", description="Finish", parameters={}),
    ]

    result = await run_tool_loop(
        [Message(role=Role.user, content="Go")],
        tools,
        {"search": search, "answer": answer},
        provider=mock_provider,
        terminal_tools={"answer"},
    )

    assert mock_provider.generate.await_count == 2
    assert result.iterations == 2
    # The assistant message carrying the terminal call is what comes back, so
    # the caller can read the arguments it was made for.
    assert result.message.tool_calls == (tc_answer,)
    assert result.history[-1].tool_name == "answer"


async def test_tool_loop_terminal_tool_executes_before_returning() -> None:
    tc = ToolCall(id="tc-1", name="answer", arguments={"picks": [7]})
    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(
        return_value=_make_response("", tool_calls=(tc,))
    )

    recorded: list[list[int]] = []

    async def answer(picks: list[int]) -> str:
        recorded.append(picks)
        return "recorded"

    tools = [ToolDefinition(name="answer", description="Finish", parameters={})]

    result = await run_tool_loop(
        [Message(role=Role.user, content="Go")],
        tools,
        {"answer": answer},
        provider=mock_provider,
        terminal_tools={"answer"},
    )

    assert recorded == [[7]]
    assert result.iterations == 1


async def test_tool_loop_without_terminal_tools_is_unchanged() -> None:
    tc = ToolCall(id="tc-1", name="answer", arguments={})
    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(
        side_effect=[_make_response("", tool_calls=(tc,)), _make_response("Done")]
    )

    async def answer() -> str:
        return "ok"

    tools = [ToolDefinition(name="answer", description="Finish", parameters={})]

    result = await run_tool_loop(
        [Message(role=Role.user, content="Go")],
        tools,
        {"answer": answer},
        provider=mock_provider,
    )

    assert result.message.content == "Done"
    assert result.iterations == 2


async def test_tool_loop_max_iterations_raises() -> None:
    tc = ToolCall(id="tc-1", name="loop", arguments={})
    looping_response = _make_response("", tool_calls=(tc,))

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value=looping_response)

    async def executor() -> str:
        return "ok"

    tools = [ToolDefinition(name="loop", description="Loop", parameters={})]

    with pytest.raises(MaxIterationsError):
        await run_tool_loop(
            [Message(role=Role.user, content="Go")],
            tools,
            {"loop": executor},
            provider=mock_provider,
            max_iterations=3,
        )

    assert mock_provider.generate.await_count == 3


async def test_tool_loop_unknown_tool_raises_tool_execution_error() -> None:
    tc = ToolCall(id="tc-1", name="missing_tool", arguments={})
    response = _make_response("", tool_calls=(tc,))

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(return_value=response)

    tools = [ToolDefinition(name="missing_tool", description="Missing", parameters={})]

    with pytest.raises(ToolExecutionError, match="missing_tool"):
        await run_tool_loop(
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
        await run_tool_loop(
            [Message(role=Role.user, content="Go")],
            tools,
            {"bad_tool": failing_executor},
            provider=mock_provider,
        )

    assert exc_info.value.tool_name == "bad_tool"
    assert isinstance(exc_info.value.__cause__, RuntimeError)


async def test_tool_loop_yields_a_call_and_its_result_in_order() -> None:
    """The progress a caller forwards, and the order it may rely on.

    `ToolCallStarted` before the executor runs and `ToolCallFinished` after it
    is what lets an SSE caller show a step opening and then closing; a single
    event carrying both would only ever arrive once the work was already done.
    """
    tc = ToolCall(id="tc-1", name="search", arguments={"q": "test"})
    first_response = _make_response("", tool_calls=(tc,))
    final_response = _make_response("Done")

    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(side_effect=[first_response, final_response])

    async def executor(q: str) -> str:
        return "found it"

    tools = [ToolDefinition(name="search", description="Search", parameters={})]

    events = [
        event
        async for event in tool_loop(
            [Message(role=Role.user, content="Search")],
            tools,
            {"search": executor},
            provider=mock_provider,
        )
    ]

    assert [type(event) for event in events] == [
        ToolCallStarted,
        ToolCallFinished,
        ToolLoopFinished,
    ]

    started, finished, done = events
    assert isinstance(started, ToolCallStarted)
    assert isinstance(finished, ToolCallFinished)
    assert isinstance(done, ToolLoopFinished)

    assert started.call is tc
    assert finished.call is tc
    # The executor's own return value, not the JSON the loop puts in `history`:
    # a caller reading a dict off a tool result should not have to parse it back.
    assert finished.result == "found it"
    assert done.result.message.content == "Done"


async def test_tool_loop_finished_is_always_last() -> None:
    """The result arrives as an event, so it has to be the terminal one."""
    tc = ToolCall(id="tc-1", name="answer", arguments={"x": 1})
    mock_provider = AsyncMock()
    mock_provider.generate = AsyncMock(
        return_value=_make_response("", tool_calls=(tc,))
    )

    async def answer(x: int) -> str:
        return "ok"

    events = [
        event
        async for event in tool_loop(
            [Message(role=Role.user, content="Go")],
            [ToolDefinition(name="answer", description="", parameters={})],
            {"answer": answer},
            provider=mock_provider,
            terminal_tools={"answer"},
        )
    ]

    assert isinstance(events[-1], ToolLoopFinished)
    assert not any(isinstance(event, ToolLoopFinished) for event in events[:-1])


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

    result = await run_tool_loop(
        messages, tools, {"get_data": executor}, provider=mock_provider
    )

    tool_result_msg = result.history[2]
    assert tool_result_msg.role == Role.tool_result
    assert '"key": "value"' in tool_result_msg.content


class TestTracing:
    """Every provider round-trip through the service layer leaves a record."""

    @pytest.fixture
    def recorder(self):
        recorder = RecordingRecorder()
        set_trace_recorder(recorder)
        yield recorder
        set_trace_recorder(None)

    async def test_generate_records_success(self, recorder) -> None:
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=_make_response("Hej"))

        await generate([Message(role=Role.user, content="Hi")], provider=mock_provider)

        (record,) = recorder.records
        assert record.operation == LLMOperation.generate
        assert record.success is True
        assert record.response_text == "Hej"

    async def test_generate_records_failure_and_reraises(self, recorder) -> None:
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(side_effect=ProviderError("upstream 503"))

        with pytest.raises(ProviderError):
            await generate(
                [Message(role=Role.user, content="Hi")], provider=mock_provider
            )

        (record,) = recorder.records
        assert record.success is False
        assert record.error_type == "ProviderError"

    async def test_generate_structured_records_before_validation(
        self, recorder
    ) -> None:
        """A schema violation is a caller-side failure, not a provider one.

        The call was still made and billed, so the record stands as successful
        and carries the text that would not parse.
        """
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=_make_response("not json"))

        with pytest.raises(ValidationError):
            await generate_structured(
                [Message(role=Role.user, content="Hi")],
                _Answer,
                provider=mock_provider,
            )

        (record,) = recorder.records
        assert record.operation == LLMOperation.generate_structured
        assert record.success is True
        assert record.response_text == "not json"

    async def test_stream_records_once_when_fully_consumed(self, recorder) -> None:
        mock_provider = AsyncMock()
        mock_provider.generate_stream = AsyncMock(
            return_value=_async_iter(
                StreamChunk(text="Hej "),
                StreamChunk(text="där"),
                StreamChunk(text="", usage=Usage(input_tokens=7, total_tokens=11)),
            )
        )

        chunks = [
            chunk
            async for chunk in generate_stream(
                [Message(role=Role.user, content="Hi")], provider=mock_provider
            )
        ]

        assert chunks == ["Hej ", "där"]
        (record,) = recorder.records
        assert record.success is True
        assert record.response_text == "Hej där"
        assert record.usage == Usage(input_tokens=7, total_tokens=11)

    async def test_abandoned_stream_records_partial_answer(self, recorder) -> None:
        mock_provider = AsyncMock()
        mock_provider.generate_stream = AsyncMock(
            return_value=_async_iter(
                StreamChunk(text="Hej "),
                StreamChunk(text="där"),
            )
        )

        stream = generate_stream(
            [Message(role=Role.user, content="Hi")], provider=mock_provider
        )
        assert await anext(stream) == "Hej "
        await stream.aclose()

        (record,) = recorder.records
        assert record.success is False
        assert record.error_type == "GeneratorExit"
        assert record.response_text == "Hej "

    async def test_tool_loop_records_every_iteration(self, recorder) -> None:
        tc = ToolCall(id="1", name="search", arguments={"q": "x"})
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(
            side_effect=[
                _make_response(tool_calls=(tc,)),
                _make_response(tool_calls=(tc,)),
                _make_response("done"),
            ]
        )

        result = await run_tool_loop(
            [Message(role=Role.user, content="Hi")],
            [ToolDefinition(name="search", description="", parameters={})],
            {"search": AsyncMock(return_value="hit")},
            provider=mock_provider,
        )

        assert result.iterations == 3
        assert len(recorder.records) == 3
        assert {r.operation for r in recorder.records} == {LLMOperation.tool_loop}
        assert [r.context["tool_loop_iteration"] for r in recorder.records] == [1, 2, 3]

    async def test_no_recorder_leaves_behaviour_unchanged(self) -> None:
        set_trace_recorder(None)
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value=_make_response("Hej"))

        result = await generate(
            [Message(role=Role.user, content="Hi")], provider=mock_provider
        )

        assert result.message.content == "Hej"
