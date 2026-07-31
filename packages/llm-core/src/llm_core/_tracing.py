"""Trace capture hook for every LLM call made through this package.

llm-core carries the *hook*, never a writer. It defines what a traced call
looks like and where a recorder plugs in; deciding where records go — a file,
an object store, a database — belongs to the application, which installs a
`TraceRecorder` at startup. That keeps this package free of any project
dependency, and keeps it fully functional with no recorder installed at all.

Correlating a record back to the work that caused it is the caller's job too.
`trace_context()` carries an arbitrary mapping alongside the call; its keys are
entirely opaque here and are attached to every record produced while it is
active.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from time import perf_counter
from typing import Any, Protocol, runtime_checkable

from llm_core._types import LLMResponse, Message, StreamChunk, ToolCall, Usage

logger = logging.getLogger(__name__)

_MILLISECONDS_PER_SECOND = 1000


class LLMOperation(StrEnum):
    generate = "generate"
    generate_structured = "generate_structured"
    generate_stream = "generate_stream"
    tool_loop = "tool_loop"
    embed = "embed"


@dataclass(frozen=True, slots=True)
class LLMCallRecord:
    """One provider round-trip, successful or not.

    A record is emitted per *billed API call*, so a tool loop produces one per
    iteration and a stream produces one when the stream ends — including when a
    consumer abandons it part-way, in which case `response_text` holds what had
    arrived so far.
    """

    operation: LLMOperation
    started_at: datetime
    latency_ms: int
    provider: str | None
    model: str | None
    messages: tuple[Message, ...]
    response_text: str | None
    response_tool_calls: tuple[ToolCall, ...]
    usage: Usage | None
    success: bool
    error_type: str | None
    error_message: str | None
    context: Mapping[str, Any]


@runtime_checkable
class TraceRecorder(Protocol):
    def record(self, record: LLMCallRecord) -> None:
        """Accept one record. Must not block and must not raise.

        Synchronous by design. A stream records from a `finally` block that may
        be running under `GeneratorExit`, where awaiting anything that suspends
        raises `RuntimeError`; and worker processes call `asyncio.run()` per
        message, which cancels pending tasks at teardown and would silently drop
        a fire-and-forget write. A recorder that needs I/O should hand off to
        its own thread.
        """
        ...


_recorder: TraceRecorder | None = None

_trace_context: ContextVar[Mapping[str, Any]] = ContextVar(
    "llm_trace_context", default={}
)


def set_trace_recorder(recorder: TraceRecorder | None) -> None:
    global _recorder
    _recorder = recorder


def get_trace_recorder() -> TraceRecorder | None:
    return _recorder


@contextmanager
def trace_context(**values: Any) -> Iterator[None]:
    """Attach `values` to every trace record produced inside this block.

    Values merge onto any enclosing context, so an inner block can add a
    `source` without discarding the `interaction_id` set further out. On a key
    collision the innermost value wins.
    """
    previous = _trace_context.get()
    token = _trace_context.set({**previous, **values})
    try:
        yield
    finally:
        try:
            _trace_context.reset(token)
        except ValueError:
            # The block is unwinding in a different Context than the one that
            # entered it, which happens when an async generator is closed from
            # outside the task that drove it. The token is meaningless there,
            # so restore the previous mapping by value.
            _trace_context.set(previous)


def current_trace_context() -> Mapping[str, Any]:
    return _trace_context.get()


@dataclass(slots=True)
class TraceBuilder:
    """Mutable accumulator for one in-flight call.

    Streams need somewhere to collect text and usage as chunks arrive, and the
    caller needs to record a failure without having a response at all.
    """

    operation: LLMOperation
    messages: tuple[Message, ...]
    started_at: datetime
    started_perf: float
    provider: str | None = None
    model: str | None = None
    usage: Usage | None = None
    text_parts: list[str] = field(default_factory=list)
    response_tool_calls: tuple[ToolCall, ...] = ()
    succeeded: bool = False
    error_type: str | None = None
    error_message: str | None = None
    has_response: bool = False


@contextmanager
def traced_call(
    operation: LLMOperation,
    messages: list[Message] | tuple[Message, ...] = (),
    *,
    model: str | None = None,
    provider: str | None = None,
) -> Iterator[TraceBuilder | None]:
    """Trace one provider round-trip for the duration of the block.

    The block owns the call; this owns the record. Leaving cleanly marks the
    call successful, leaving by exception records the failure, and either way
    the record is handed over exactly once. Callers only supply the payload the
    provider gave back — `trace_response`, `trace_chunk` or `trace_outcome`.

    `model` and `provider` seed attribution for callers that know it up front;
    anything the provider itself reports overrides them.

    The yielded builder is None when tracing is off, which every fold function
    treats as a no-op. That keeps the untraced path down to a single global
    read and lets streams skip accumulating text they will never record.
    """
    builder = _start(operation, messages, model=model, provider=provider)
    try:
        yield builder
    except BaseException as exc:
        # BaseException, not Exception: a consumer that abandons a stream closes
        # the generator, which arrives here as GeneratorExit. That case is worth
        # recording precisely because the answer was paid for and never
        # delivered.
        _record_failure(builder, exc)
        raise
    else:
        if builder is not None:
            builder.succeeded = True
    finally:
        # Synchronous by necessity: under GeneratorExit, awaiting anything that
        # suspends would raise RuntimeError instead.
        _finish(builder)


def _start(
    operation: LLMOperation,
    messages: list[Message] | tuple[Message, ...],
    *,
    model: str | None,
    provider: str | None,
) -> TraceBuilder | None:
    if _recorder is None:
        return None
    return TraceBuilder(
        operation=operation,
        messages=tuple(messages),
        started_at=datetime.now(UTC),
        started_perf=perf_counter(),
        model=model,
        provider=provider,
    )


def trace_response(builder: TraceBuilder | None, response: LLMResponse) -> None:
    """Fold a non-streaming response into the trace."""
    if builder is None:
        return
    builder.has_response = True
    builder.text_parts.append(response.message.content)
    builder.response_tool_calls = response.message.tool_calls
    trace_outcome(
        builder,
        usage=response.usage,
        model=response.model,
        provider=response.provider,
    )


def trace_chunk(builder: TraceBuilder | None, chunk: StreamChunk) -> None:
    """Fold one stream chunk into the trace.

    A chunk carrying only usage still counts as a response: the stream produced
    something, so `response_text` should be empty rather than absent.
    """
    if builder is None:
        return
    builder.has_response = True
    if chunk.text:
        builder.text_parts.append(chunk.text)
    trace_outcome(
        builder, usage=chunk.usage, model=chunk.model, provider=chunk.provider
    )


def trace_outcome(
    builder: TraceBuilder | None,
    *,
    usage: Usage | None = None,
    model: str | None = None,
    provider: str | None = None,
    response_text: str | None = None,
) -> None:
    """Report token counts and attribution for a call this package did not make.

    The extension point for callers that reach a provider directly — embeddings,
    for instance — and so have usage and attribution but no `LLMResponse`.

    None never overwrites a value already recorded. Usage arrives late and, on
    some providers, cumulatively, so the last report of each field wins.
    """
    if builder is None:
        return
    if usage is not None:
        builder.usage = usage
    if model is not None:
        builder.model = model
    if provider is not None:
        builder.provider = provider
    if response_text is not None:
        builder.has_response = True
        builder.text_parts.append(response_text)


def _record_failure(builder: TraceBuilder | None, error: BaseException) -> None:
    if builder is None:
        return
    builder.succeeded = False
    builder.error_type = type(error).__name__
    builder.error_message = str(error)


def _finish(builder: TraceBuilder | None) -> None:
    """Hand the finished record to the recorder. Never raises.

    Observability failing must never turn into an application failure, so every
    step from here on is inside the guard — including reading the trace context,
    which happens now because the recorder may write from another thread where
    the ContextVar is not set.
    """
    if builder is None:
        return
    try:
        recorder = _recorder
        if recorder is not None:
            recorder.record(_build_record(builder))
    except Exception:
        logger.warning("Failed to record LLM trace", exc_info=True)


def _build_record(builder: TraceBuilder) -> LLMCallRecord:
    elapsed = perf_counter() - builder.started_perf
    return LLMCallRecord(
        operation=builder.operation,
        started_at=builder.started_at,
        latency_ms=int(elapsed * _MILLISECONDS_PER_SECOND),
        provider=builder.provider,
        model=builder.model,
        messages=builder.messages,
        response_text="".join(builder.text_parts) if builder.has_response else None,
        response_tool_calls=builder.response_tool_calls,
        usage=builder.usage,
        success=builder.succeeded,
        error_type=builder.error_type,
        error_message=builder.error_message,
        context=dict(current_trace_context()),
    )
