from __future__ import annotations

import asyncio

import pytest

from llm_core._tracing import (
    LLMCallRecord,
    LLMOperation,
    current_trace_context,
    get_trace_recorder,
    set_trace_recorder,
    trace_chunk,
    trace_context,
    trace_outcome,
    trace_response,
    traced_call,
)
from llm_core._types import LLMResponse, Message, Role, StreamChunk, ToolCall, Usage


class RecordingRecorder:
    def __init__(self) -> None:
        self.records: list[LLMCallRecord] = []

    def record(self, record: LLMCallRecord) -> None:
        self.records.append(record)


class ExplodingRecorder:
    def record(self, record: LLMCallRecord) -> None:
        raise RuntimeError("recorder is broken")


@pytest.fixture
def recorder():
    recorder = RecordingRecorder()
    set_trace_recorder(recorder)
    yield recorder
    set_trace_recorder(None)


def _user_messages() -> list[Message]:
    return [Message(role=Role.user, content="Vad gäller?")]


def test_no_recorder_yields_no_builder() -> None:
    set_trace_recorder(None)
    with traced_call(LLMOperation.generate, _user_messages()) as trace:
        assert trace is None


def test_fold_functions_tolerate_a_missing_builder() -> None:
    """The untraced path calls every fold with None; none may raise."""
    set_trace_recorder(None)
    with traced_call(LLMOperation.generate, _user_messages()) as trace:
        trace_response(trace, LLMResponse(message=Message(role=Role.assistant)))
        trace_chunk(trace, StreamChunk(text="hej"))
        trace_outcome(trace, usage=Usage(input_tokens=1))


def test_set_and_get_recorder(recorder) -> None:
    assert get_trace_recorder() is recorder


def test_successful_response_is_recorded(recorder) -> None:
    response = LLMResponse(
        message=Message(role=Role.assistant, content="Svar"),
        usage=Usage(input_tokens=10, output_tokens=3, total_tokens=13),
        model="mistralai/Mistral-Small-3.2-24B-Instruct-2506",
        provider="berget",
    )

    with traced_call(LLMOperation.generate, _user_messages()) as trace:
        trace_response(trace, response)

    (record,) = recorder.records
    assert record.operation == LLMOperation.generate
    assert record.success is True
    assert record.response_text == "Svar"
    assert record.usage == Usage(input_tokens=10, output_tokens=3, total_tokens=13)
    assert record.model == "mistralai/Mistral-Small-3.2-24B-Instruct-2506"
    assert record.provider == "berget"
    assert record.messages == tuple(_user_messages())
    assert record.error_type is None
    assert record.latency_ms >= 0


def test_response_tool_calls_are_recorded(recorder) -> None:
    tool_call = ToolCall(id="1", name="search", arguments={"q": "kyrka"})
    response = LLMResponse(
        message=Message(role=Role.assistant, content="", tool_calls=(tool_call,))
    )

    with traced_call(LLMOperation.tool_loop, _user_messages()) as trace:
        trace_response(trace, response)

    assert recorder.records[0].response_tool_calls == (tool_call,)


def test_failure_is_recorded_with_type_and_message(recorder) -> None:
    with pytest.raises(ValueError):
        with traced_call(LLMOperation.generate, _user_messages()):
            raise ValueError("upstream refused")

    (record,) = recorder.records
    assert record.success is False
    assert record.error_type == "ValueError"
    assert record.error_message == "upstream refused"
    assert record.response_text is None


def test_seeded_attribution_survives_a_failure(recorder) -> None:
    """A call that never returns still names the model it was billed against."""
    with pytest.raises(TimeoutError):
        with traced_call(
            LLMOperation.embed,
            model="intfloat/multilingual-e5-large",
            provider="berget",
        ):
            raise TimeoutError("gateway timeout")

    (record,) = recorder.records
    assert record.model == "intfloat/multilingual-e5-large"
    assert record.provider == "berget"


def test_provider_reported_attribution_overrides_the_seed(recorder) -> None:
    with traced_call(LLMOperation.embed, model="e5-large", provider="berget") as trace:
        trace_outcome(trace, model="intfloat/multilingual-e5-large-001")

    assert recorder.records[0].model == "intfloat/multilingual-e5-large-001"
    assert recorder.records[0].provider == "berget"


def test_stream_chunks_accumulate_text_and_last_usage(recorder) -> None:
    with traced_call(LLMOperation.generate_stream, _user_messages()) as trace:
        trace_chunk(trace, StreamChunk(text="Hej ", model="glm", provider="berget"))
        trace_chunk(trace, StreamChunk(text="där"))
        trace_chunk(trace, StreamChunk(text="", usage=Usage(input_tokens=5)))
        trace_chunk(
            trace, StreamChunk(text="", usage=Usage(input_tokens=5, total_tokens=9))
        )

    (record,) = recorder.records
    assert record.response_text == "Hej där"
    assert record.usage == Usage(input_tokens=5, total_tokens=9)
    assert record.model == "glm"
    assert record.success is True


def test_abandoned_stream_records_partial_text(recorder) -> None:
    """GeneratorExit is a BaseException; the trace must still close on it."""
    with pytest.raises(GeneratorExit):
        with traced_call(LLMOperation.generate_stream, _user_messages()) as trace:
            trace_chunk(trace, StreamChunk(text="halvt "))
            raise GeneratorExit

    (record,) = recorder.records
    assert record.success is False
    assert record.error_type == "GeneratorExit"
    assert record.response_text == "halvt "


def test_recorder_exception_is_swallowed() -> None:
    set_trace_recorder(ExplodingRecorder())
    try:
        with traced_call(LLMOperation.generate, _user_messages()) as trace:
            trace_response(trace, LLMResponse(message=Message(role=Role.assistant)))
    finally:
        set_trace_recorder(None)


def test_trace_context_defaults_to_empty() -> None:
    assert current_trace_context() == {}


def test_trace_context_is_attached_to_the_record(recorder) -> None:
    with trace_context(interaction_id="abc", source="api.chat"):
        with traced_call(LLMOperation.generate, _user_messages()) as trace:
            trace_response(trace, LLMResponse(message=Message(role=Role.assistant)))

    assert recorder.records[0].context == {
        "interaction_id": "abc",
        "source": "api.chat",
    }


def test_nested_trace_context_merges_and_inner_wins(recorder) -> None:
    with trace_context(interaction_id="abc", source="api.chat"):
        with trace_context(source="api.retriever.rerank"):
            with traced_call(LLMOperation.generate, _user_messages()) as trace:
                trace_response(trace, LLMResponse(message=Message(role=Role.assistant)))

    assert recorder.records[0].context == {
        "interaction_id": "abc",
        "source": "api.retriever.rerank",
    }


def test_trace_context_restores_on_exit() -> None:
    with trace_context(outer="1"):
        with trace_context(inner="2"):
            assert current_trace_context() == {"outer": "1", "inner": "2"}
        assert current_trace_context() == {"outer": "1"}
    assert current_trace_context() == {}


def test_trace_context_restores_after_an_exception() -> None:
    with pytest.raises(RuntimeError):
        with trace_context(outer="1"):
            raise RuntimeError("boom")
    assert current_trace_context() == {}


async def test_trace_context_survives_generator_closed_from_another_context(
    recorder,
) -> None:
    """Closing an async generator unwinds it in a different Context.

    Starlette drives an SSE response this way, so `trace_context` must restore
    by value rather than by token or the close would raise.
    """

    async def streaming() -> None:
        with trace_context(interaction_id="abc"):
            try:
                while True:
                    await asyncio.sleep(0)
            finally:
                with traced_call(LLMOperation.generate_stream, _user_messages()):
                    pass

    task = asyncio.create_task(streaming())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert recorder.records[0].context == {"interaction_id": "abc"}
